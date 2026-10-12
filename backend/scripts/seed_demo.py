"""Create the demo account and load the sample datasets (idempotent).

Usage: python scripts/seed_demo.py [--email demo@analystos.dev] [--password analystos-demo-2026] [--role admin]

Use --role analyst on a public demo: the password is published, and admins can see every source and change roles.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.security import hash_password
from app.db.models import Dataset, User
from app.db.session import get_session_factory
from app.services.ingestion.service import ingest_upload

DATA = Path(__file__).resolve().parents[1] / "evals" / "data"
FILES = {
    "sales.csv": "Sales 2025-2026",
    "sales_2026.xlsx": "Sales workbook 2026",
    "saas_subscriptions.csv": "SaaS subscriptions",
    "marketing_performance.csv": "Marketing performance",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="demo@analystos.dev")
    parser.add_argument("--password", default="analystos-demo-2026")
    parser.add_argument("--role", choices=["admin", "analyst", "viewer"], default="admin")
    args = parser.parse_args()
    db = get_session_factory()()
    user = db.query(User).filter(User.email == args.email).first()
    if user is None:
        user = User(
            email=args.email,
            name="Demo Analyst",
            password_hash=hash_password(args.password),
            is_admin=args.role == "admin",
            role=args.role,
        )
        db.add(user)
        db.commit()
    for filename, name in FILES.items():
        if db.query(Dataset).filter(Dataset.user_id == user.id, Dataset.original_filename == filename).first():
            continue
        with (DATA / filename).open("rb") as handle:
            ingest_upload(db, user_id=user.id, stream=handle, filename=filename, name=name)
        print(f"loaded {filename}")
    print(f"demo user ready: {args.email}")
    db.close()


if __name__ == "__main__":
    main()
