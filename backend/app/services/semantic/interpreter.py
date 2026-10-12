"""Semantic schema interpretation.

Maps physical columns to business meaning ("revenue", "region", "signup date") with a confidence score.
Scores combine name evidence (token matches) with value evidence (type, unit, ranges, cardinality).
Low-confidence guesses are labelled as such and surfaced to the agent as uncertain, never as facts.
Users can override any column's semantic type from the dataset explorer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.profiling.profiler import ColumnProfile, TableProfile

UNCERTAIN_BELOW = 0.6


@dataclass(frozen=True)
class Rule:
    semantic_type: str
    concept: str
    tokens: tuple[str, ...]
    roles: tuple[str, ...]


RULES: tuple[Rule, ...] = (
    Rule("currency_metric", "revenue", ("revenue", "sales", "turnover", "gmv", "income", "bookings"), ("metric",)),
    Rule("currency_metric", "recurring_revenue", ("mrr", "arr", "recurring"), ("metric",)),
    Rule("currency_metric", "profit", ("profit", "earnings", "ebitda", "net_income", "gross_profit"), ("metric",)),
    Rule("currency_metric", "cost", ("cost", "cogs", "expense", "expenses", "spend", "budget", "fee", "fees"),
         ("metric",)),
    Rule("currency_metric", "price", ("price", "unit_price", "aov", "arpu", "asp"), ("metric",)),
    Rule("currency_metric", "amount", ("amount", "value", "payment", "total", "ltv", "usd", "eur", "gbp"),
         ("metric",)),
    Rule("quantity_metric", "quantity", ("units", "qty", "quantity", "volume", "items"), ("metric",)),
    Rule("quantity_metric", "count", ("count", "orders", "transactions", "visits", "sessions", "clicks",
                                      "impressions", "signups", "leads", "conversions", "tickets",
                                      "support_tickets", "seats", "users", "installs"), ("metric",)),
    Rule("quantity_metric", "usage", ("usage", "events", "logins", "api_calls", "minutes_used"), ("metric",)),
    Rule("percentage_metric", "rate", ("pct", "percent", "percentage", "rate", "ratio", "share", "ctr",
                                       "conversion_rate", "churn_rate", "margin", "growth"), ("metric",)),
    Rule("score_metric", "score", ("score", "rating", "nps", "csat", "satisfaction"), ("metric",)),
    Rule("duration_metric", "duration", ("duration", "days", "hours", "minutes", "tenure", "lead_time",
                                         "age_days"), ("metric",)),
    Rule("geographical_category", "location", ("region", "country", "city", "state", "province", "territory",
                                               "location", "geo", "market", "zip", "postcode", "area"),
         ("dimension", "text")),
    Rule("store_category", "store", ("store", "branch", "outlet", "shop", "warehouse", "site"),
         ("dimension", "text", "identifier")),
    Rule("product_category", "product", ("product", "sku", "item", "model", "brand"),
         ("dimension", "text", "identifier")),
    Rule("plan_category", "plan", ("plan", "tier", "package", "subscription", "edition"), ("dimension",)),
    Rule("customer_dimension", "customer", ("customer", "client", "account", "company", "buyer", "tenant"),
         ("dimension", "text", "identifier")),
    Rule("segment_category", "segment", ("segment", "cohort", "persona", "customer_segment", "industry",
                                         "vertical", "size"), ("dimension",)),
    Rule("channel_category", "channel", ("channel", "source", "medium", "campaign", "utm", "platform",
                                         "referrer"), ("dimension",)),
    Rule("category", "category", ("category", "type", "class", "group", "department", "line", "family"),
         ("dimension",)),
    Rule("status_category", "status", ("status", "stage", "outcome", "result", "churned", "active",
                                       "is_active", "flag"), ("dimension",)),
    Rule("employee_dimension", "employee", ("rep", "agent", "employee", "owner", "manager", "salesperson"),
         ("dimension", "text")),
)

_PII_NAME = re.compile(
    r"(e_?mail|phone|mobile|first_name|last_name|full_name|contact_name|person_name|address|street|ssn|"
    r"social_security|passport|national_id|date_of_birth|dob|birth_?date|ip_address|credit_card|iban)",
    re.I,
)
_TIME_CONCEPTS = (
    ("signup_date", ("signup", "sign_up", "created", "registered", "start", "joined", "onboard")),
    ("churn_date", ("churn", "cancel", "end", "terminated", "closed")),
    ("order_date", ("order", "purchase", "transaction", "invoice", "sale")),
)


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", name.lower()) if t]


def _name_score(name: str, rule: Rule) -> float:
    lowered = name.lower()
    tokens = _tokens(name)
    best = 0.0
    for keyword in rule.tokens:
        if lowered == keyword:
            best = max(best, 0.95)
        elif "_" in keyword and keyword in lowered:
            best = max(best, 0.9)
        elif keyword in tokens:
            best = max(best, 0.85 if tokens[-1] == keyword else 0.78)
        elif len(keyword) >= 4 and keyword in lowered:
            best = max(best, 0.6)
    return best


def _value_adjustment(column: ColumnProfile, rule: Rule) -> float:
    stats = column.stats
    unit = stats.get("unit")
    adj = 0.0
    if rule.semantic_type == "currency_metric":
        if unit == "currency":
            adj += 0.05
        if unit == "percent":
            adj -= 0.4
        if column.inferred_type == "float":
            adj += 0.02
    elif rule.semantic_type == "percentage_metric":
        mn, mx = stats.get("min"), stats.get("max")
        if unit == "percent":
            adj += 0.08
        elif mn is not None and mx is not None and float(mn) >= 0 and float(mx) <= 1:
            adj += 0.06
        elif mx is not None and float(mx) > 100:
            adj -= 0.3
    elif rule.semantic_type == "quantity_metric":
        if column.inferred_type == "integer":
            adj += 0.04
        if stats.get("negatives"):
            adj -= 0.1
    elif rule.semantic_type == "status_category" and column.inferred_type == "boolean":
        adj += 0.05
    return adj


def interpret_column(column: ColumnProfile) -> dict[str, Any]:
    name = column.name
    is_pii = bool(_PII_NAME.search(name)) or any(f.startswith("pii_") for f in column.flags)
    result: dict[str, Any] = {
        "column": name,
        "role": column.role,
        "semantic_type": None,
        "concept": None,
        "confidence": 0.0,
        "is_pii": is_pii,
        "alternatives": [],
    }
    if column.role == "time":
        concept = "date"
        for candidate, keys in _TIME_CONCEPTS:
            if any(k in name.lower() for k in keys):
                concept = candidate
                break
        result.update(semantic_type="date" if column.inferred_type == "date" else "datetime"
                      if column.inferred_type == "datetime" else "time_period", concept=concept,
                      confidence=0.95 if column.inferred_type in {"date", "datetime"} else 0.75)
        return result
    if column.role == "identifier":
        concept = "identifier"
        for rule in RULES:
            if "identifier" in rule.roles and _name_score(name, rule) >= 0.6:
                concept = f"{rule.concept}_id"
                break
        result.update(semantic_type="identifier", concept=concept, confidence=0.9 if "_id" in name or
                      name.lower() == "id" else 0.7)
        return result

    scored: list[tuple[float, Rule]] = []
    for rule in RULES:
        if column.role not in rule.roles:
            continue
        base = _name_score(name, rule)
        if base == 0:
            continue
        scored.append((min(0.99, max(0.0, base + _value_adjustment(column, rule))), rule))
    scored.sort(key=lambda item: -item[0])

    if scored:
        confidence, rule = scored[0]
        result.update(semantic_type=rule.semantic_type, concept=rule.concept, confidence=round(confidence, 2))
        result["alternatives"] = [
            {"semantic_type": r.semantic_type, "concept": r.concept, "confidence": round(s, 2)}
            for s, r in scored[1:3]
        ]
    else:
        fallback = {
            "metric": ("numeric_metric", "measure", 0.5),
            "dimension": ("categorical_dimension", "category", 0.5),
            "text": ("free_text", "text", 0.6),
        }.get(column.role, ("unknown", "unknown", 0.2))
        unit = column.stats.get("unit")
        if column.role == "metric" and unit == "currency":
            fallback = ("currency_metric", "amount", 0.7)
        elif column.role == "metric" and unit == "percent":
            fallback = ("percentage_metric", "rate", 0.7)
        result.update(semantic_type=fallback[0], concept=fallback[1], confidence=fallback[2])
    if is_pii:
        result["semantic_type"] = "pii"
        result["confidence"] = max(result["confidence"], 0.85)
    return result


def interpret_table(profile: TableProfile) -> dict[str, Any]:
    columns = [interpret_column(c) for c in profile.columns]
    by_role: dict[str, list[dict[str, Any]]] = {"metric": [], "dimension": [], "time": [], "identifier": [], "text": []}
    for item in columns:
        entry = {k: item[k] for k in ("column", "semantic_type", "concept", "confidence")}
        by_role.setdefault(item["role"], []).append(entry)
    uncertain = [c["column"] for c in columns if c["confidence"] < UNCERTAIN_BELOW]
    return {
        "table": profile.name,
        "metrics": by_role.get("metric", []),
        "dimensions": by_role.get("dimension", []),
        "time": by_role.get("time", []),
        "identifiers": by_role.get("identifier", []),
        "text": by_role.get("text", []),
        "pii_columns": [c["column"] for c in columns if c["is_pii"]],
        "uncertain_columns": uncertain,
        "columns": columns,
    }
