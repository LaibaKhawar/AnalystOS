"""Deterministic claim verification.

Every number in the drafted answer must be traceable to a Finding (a tool-computed value):
  * direct match: the number equals a finding value within the precision the writer used
    ("1.2M" matches 1,234,567; "17.3%" matches -17.31 when phrased as a decline),
  * derived match: a percentage that recomputes exactly from two values of the cited findings
    (percent change or share); the formula is recorded as evidence.
A finding only supports a sentence if the sentence names one of the finding's entities (segment values,
filters) and does not contradict its periods (quarters / months).
Unsupported sentences are removed (kept in the audit trail), causal wording in facts is moved into
interpretations and marked as a hypothesis, and the LLM never gets to "fill in" missing values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.db.models import Finding

_NUMBER = re.compile(
    r"(?P<cur>[$€£¥])?\s?(?P<sign>[-+\u2212])?(?P<cur2>[$€£¥])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<suffix>k|K|m|M|bn|B|thousand|million|billion)\b)?\s?(?P<pct>%|percent\b|pp\b|percentage points?)?"
)
_DATE_LIKE = re.compile(
    r"\b\d{4}-\d{2}(?:-\d{2})?\b|\b(?:Q[1-4]|H[12])\s?\d{4}\b|\b\d{4}\s?-?\s?(?:Q[1-4]|H[12])\b|"
    r"\bQ[1-4]\b|\bH[12]\b|\bF\d+\b"
)
_MULTIPLIER = re.compile(r"[*\u00d7]\s?100\s?%?|(?:multiplied|times)\s+(?:by\s+)?100\b", re.IGNORECASE)
_BARE_CITATION = re.compile(r"[\s\[\](),.;]*(?:F\d+[\s\[\](),.;]*)+")
_CAUSAL = re.compile(
    r"\b(caused|causes|causing|because of|due to|led to|leads to|resulted in|results in|drove|"
    r"driven by|was driven|is driven|attributable to|thanks to)\b",
    re.IGNORECASE,
)
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_MONTH_ABBR = {m[:3]: i for m, i in _MONTHS.items()}
_SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "b": 1e9, "billion": 1e9}


@dataclass
class NumberToken:
    raw: str
    value: float
    is_pct: bool
    decimals: int
    scale: float
    start: int
    end: int


@dataclass
class Match:
    token: str
    finding_label: str
    finding_id: str
    value_key: str | None
    value: float
    derived_formula: str | None = None


@dataclass
class ClaimCheck:
    text: str
    status: str  # verified | removed | qualified | no_numbers
    section: str
    kind: str
    citations: list[str]
    numbers: list[str] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    original_text: str | None = None


def extract_numbers(text: str, exempt_phrases: list[str] | None = None) -> list[NumberToken]:
    masked = _MULTIPLIER.sub(lambda m: " " * len(m.group(0)), text)
    for match in _DATE_LIKE.finditer(masked):
        masked = masked[: match.start()] + " " * (match.end() - match.start()) + masked[match.end() :]
    for phrase in exempt_phrases or []:
        if phrase and any(ch.isdigit() for ch in phrase):
            for found in re.finditer(re.escape(phrase), masked, re.IGNORECASE):
                masked = masked[: found.start()] + " " * (found.end() - found.start()) + masked[found.end() :]
    tokens: list[NumberToken] = []
    for m in _NUMBER.finditer(masked):
        num = m.group("num")
        # Skip digits that are part of identifiers like "col_2026" or "store12".
        if m.start("num") > 0 and (masked[m.start("num") - 1].isalpha() or masked[m.start("num") - 1] == "_"):
            continue
        suffix = (m.group("suffix") or "").lower()
        is_pct = bool(m.group("pct"))
        has_currency = bool(m.group("cur") or m.group("cur2"))
        value = float(num.replace(",", ""))
        decimals = len(num.split(".")[1]) if "." in num else 0
        if m.group("sign") in {"-", "\u2212"}:
            value = -value
        plain_int = not is_pct and not suffix and not has_currency and decimals == 0 and "," not in num
        if plain_int and (1900 <= abs(value) <= 2100 or abs(value) <= 12):
            continue  # years, small counts/ordinals ("top 3", "4 regions")
        scale = _SCALES.get(suffix, 1.0)
        tokens.append(
            NumberToken(
                raw=m.group(0).strip(),
                value=value * scale,
                is_pct=is_pct,
                decimals=decimals,
                scale=scale,
                start=m.start(),
                end=m.end(),
            )
        )
    return tokens


def _numeric_values(finding: Finding) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in (finding.values or {}).items():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float) and not (
            isinstance(value, float) and (math.isnan(value) or math.isinf(value))
        ):
            out[key] = float(value)
    return out


def _close(token: NumberToken, value: float) -> bool:
    target = token.value
    half_unit = 0.5 * (10**-token.decimals) * token.scale
    for candidate in (value, abs(value)):
        for t in (target, abs(target)):
            if abs(t - candidate) <= half_unit * 1.001 + 1e-9:
                return True
            if candidate and abs(t - candidate) / abs(candidate) <= 0.005 and token.decimals == 0 and token.scale > 1:
                return True
    if token.is_pct and abs(value) <= 1.0:  # shares stored as fractions
        return abs(abs(target) / 100 - abs(value)) <= half_unit / 100 * 1.001 + 1e-12
    return False


def _mentions(text: str, entity: str) -> bool:
    return bool(re.search(rf"(?<![\w]){re.escape(entity.lower())}(?![\w])", text))


def _entity_ok(sentence: str, finding: Finding, known_entities: set[str]) -> bool:
    """A finding supports a sentence unless the sentence is about a different known entity.

    Sentences that name none of the known entities ("The revenue change was ...") may use a finding scoped to a
    filter; sentences naming another segment ("Karachi fell 17.3%") cannot borrow a Lahore number.
    """
    entities = [str(e).lower() for e in (finding.payload or {}).get("entities", []) if e]
    if not entities:
        return True
    lowered = sentence.lower()
    if any(_mentions(lowered, e) for e in entities):
        return True
    return not any(_mentions(lowered, other) for other in known_entities if other not in entities)


def _periods_ok(sentence: str, finding: Finding) -> bool:
    periods = [str(p) for p in (finding.payload or {}).get("periods", []) if p]
    if not periods:
        return True
    quarters = set(re.findall(r"\bQ([1-4])\b", sentence, re.IGNORECASE))
    if quarters:
        finding_quarters = {p[-1] for p in periods if re.search(r"Q[1-4]$", p)}
        month_quarters = {str((int(p[5:7]) - 1) // 3 + 1) for p in periods if re.match(r"\d{4}-\d{2}", p)}
        known = finding_quarters | month_quarters
        if known and not quarters & known:
            return False
    months = {i for name, i in {**_MONTHS, **_MONTH_ABBR}.items() if re.search(rf"\b{name}\b", sentence, re.I)}
    if months:
        finding_months = {int(p[5:7]) for p in periods if re.match(r"\d{4}-\d{2}", p)}
        if finding_months and not months & finding_months:
            # Quarter-level findings can still back a month name only if the month lies in the quarter.
            return False
    return True


def _derived(token: NumberToken, findings: list[Finding]) -> Match | None:
    if not token.is_pct:
        return None
    values: list[tuple[Finding, str, float]] = [
        (f, k, v)
        for f in findings
        for k, v in _numeric_values(f).items()
        if not any(s in k for s in ("pct", "share", "contribution", "p_value", "coefficient", "rank", "score"))
    ]
    for i, (fa, ka, a) in enumerate(values):
        for fb, kb, b in values[i + 1 :] + values[:i]:
            if a == 0 or (fa is fb and ka == kb):
                continue
            change = (b - a) / abs(a) * 100
            share = b / a * 100
            for computed, formula in ((change, f"({b:g} - {a:g}) / {abs(a):g} * 100"), (share, f"{b:g} / {a:g} * 100")):
                probe = NumberToken(token.raw, token.value, True, token.decimals, 1.0, 0, 0)
                if _close(probe, computed):
                    return Match(
                        token.raw,
                        fa.label if fa is fb else f"{fa.label}+{fb.label}",
                        fa.id,
                        None,
                        round(computed, 4),
                        derived_formula=formula,
                    )
    return None


def verify_sentence(
    text: str,
    citations: list[str],
    findings: dict[str, Finding],
    *,
    section: str,
    kind: str,
    exempt_phrases: list[str],
    known_entities: set[str] | None = None,
) -> ClaimCheck:
    if known_entities is None:
        known_entities = entities_of(findings.values())
    valid_citations = [c.upper().strip() for c in citations if c and c.upper().strip() in findings]
    check = ClaimCheck(text=text.strip(), status="no_numbers", section=section, kind=kind, citations=valid_citations)
    tokens = extract_numbers(text, exempt_phrases)
    check.numbers = [t.raw for t in tokens]
    cited = [findings[c] for c in valid_citations]
    pool = cited + [f for label, f in findings.items() if label not in valid_citations]
    for token in tokens:
        match = None
        for scope in (cited, pool):
            candidates = [f for f in scope if _entity_ok(text, f, known_entities) and _periods_ok(text, f)]
            for finding in candidates:
                for key, value in _numeric_values(finding).items():
                    if _close(token, value):
                        match = Match(token.raw, finding.label, finding.id, key, value)
                        break
                if match:
                    break
            if not match:
                match = _derived(token, candidates)
            if match:
                if scope is pool and match.finding_label not in check.citations:
                    check.notes.append(f"{token.raw} matched uncited finding {match.finding_label}")
                    check.citations.append(match.finding_label.split("+")[0])
                break
        if match:
            check.matches.append(match)
        else:
            check.unsupported.append(token.raw)
    if tokens:
        check.status = "verified" if not check.unsupported else "removed"
    if check.status != "removed" and kind in {"fact", "interpretation"} and _CAUSAL.search(text):
        check.original_text = check.text
        check.text = f"Hypothesis (not causally verified): {check.text}"
        check.status = "qualified"
        if kind == "fact":
            check.kind = "interpretation"
            check.notes.append("causal wording moved from facts to interpretations")
        else:
            check.notes.append("causal interpretation labelled as a hypothesis")
    return check


@dataclass
class VerificationReport:
    claims: list[ClaimCheck]
    headline: str
    caveats: list[str]
    follow_ups: list[str]
    draft_numeric: int = 0
    draft_removed: int = 0
    repaired: int = 0

    @property
    def numeric_claims(self) -> list[ClaimCheck]:
        return [c for c in self.claims if c.numbers]

    def stats(self) -> dict[str, Any]:
        numeric = self.numeric_claims
        removed = [c for c in numeric if c.status == "removed"]
        draft_numeric = self.draft_numeric or len(numeric)
        draft_removed = self.draft_removed if self.draft_numeric else len(removed)
        kept_numeric = [c for c in numeric if c.status != "removed"]
        return {
            "claims_total": len(self.claims),
            "numeric_claims": len(numeric),
            "verified": sum(1 for c in self.claims if c.status == "verified"),
            "qualified": sum(1 for c in self.claims if c.status == "qualified"),
            "removed": len(removed),
            "repaired": self.repaired,
            # Share of the model's first-draft numeric sentences that had unsupported numbers.
            "draft_unsupported_rate": round(draft_removed / draft_numeric, 4) if draft_numeric else 0.0,
            # Share of numeric sentences shown to the user without matching evidence (by construction 0).
            "final_unsupported_rate": round(sum(1 for c in kept_numeric if not c.matches) / len(kept_numeric), 4)
            if kept_numeric
            else 0.0,
        }


def entities_of(findings: Any) -> set[str]:
    return {str(e).lower() for f in findings for e in (f.payload or {}).get("entities", []) if e and len(str(e)) >= 3}


def verify_answer(
    draft: dict[str, Any],
    findings: list[Finding],
    *,
    exempt_phrases: list[str],
    known_entities: set[str] | None = None,
) -> VerificationReport:
    """Verify a drafted answer. known_entities: category values of the dataset (plus finding entities)."""
    by_label = {f.label.upper(): f for f in findings}
    known = {e.lower() for e in (known_entities or set()) if len(e) >= 3} | entities_of(findings)
    claims: list[ClaimCheck] = []

    def handle(items: list[Any], section: str, kind: str) -> None:
        for item in items or []:
            if isinstance(item, str):
                text, cites, sec = item, [], section
            else:
                text, cites, sec = (
                    str(item.get("text", "")),
                    list(item.get("citations") or []),
                    item.get("section") or section,
                )
            for sentence in _split_sentences(text):
                if _BARE_CITATION.fullmatch(sentence):
                    continue  # a sentence that is only "F1" or "[F2, F3]" carries no claim
                claims.append(
                    verify_sentence(
                        sentence,
                        cites,
                        by_label,
                        section=sec,
                        kind=kind,
                        exempt_phrases=exempt_phrases,
                        known_entities=known,
                    )
                )

    handle(draft.get("summary", []), "summary", "fact")
    handle(draft.get("facts", []), "finding", "fact")
    handle(draft.get("interpretations", []), "interpretation", "interpretation")
    handle(draft.get("recommendations", []), "recommendation", "recommendation")

    headline = str(draft.get("headline") or "").strip()
    head_check = (
        verify_sentence(
            headline, [], by_label, section="headline", kind="fact", exempt_phrases=exempt_phrases, known_entities=known
        )
        if headline
        else None
    )
    if head_check is not None:
        head_check.section = "headline"
        claims.insert(0, head_check)  # stored with evidence so the headline itself is auditable
    if head_check is None or head_check.status == "removed":
        fallback = next(
            (c.text for c in claims if c.section == "summary" and c.status in {"verified", "no_numbers"}), None
        )
        headline = fallback or "Analysis complete"
    caveats = []
    for caveat in draft.get("caveats", []) or []:
        check = verify_sentence(
            str(caveat),
            [],
            by_label,
            section="caveat",
            kind="caveat",
            exempt_phrases=exempt_phrases,
            known_entities=known,
        )
        if check.status != "removed":
            caveats.append(check.text)
    follow_ups = [str(q) for q in (draft.get("follow_up_questions") or []) if isinstance(q, str)][:5]
    return VerificationReport(claims=claims, headline=headline, caveats=caveats, follow_ups=follow_ups)


def _split_sentences(text: str) -> list[str]:
    protected = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text.strip())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]
