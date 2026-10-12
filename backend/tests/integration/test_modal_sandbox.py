"""Real Modal sandboxes (skipped unless Modal credentials are configured on this machine)."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import get_settings


def _modal_ready() -> bool:
    try:
        import modal

        modal.App.lookup(get_settings().modal_sandbox_app, create_if_missing=True)
        return True
    except Exception:
        return False


pytestmark = [pytest.mark.modal, pytest.mark.skipif(not _modal_ready(), reason="Modal credentials not configured")]


@pytest.fixture
def table(tmp_path: Path) -> dict[str, Path]:
    path = tmp_path / "sales.parquet"
    pd.DataFrame({"region": ["N", "S", "N"], "revenue": [1.0, 2.0, 3.5]}).to_parquet(path)
    return {"sales": path}


def test_modal_runs_pandas_and_reports_key_errors(table: dict[str, Path]) -> None:
    from app.services.sandbox.modal_runner import ModalSandbox

    sandbox = ModalSandbox()
    ok = sandbox.run("result = df.groupby('region')['revenue'].sum()", table)
    assert ok.ok, ok.error_message
    assert sorted(ok.result["rows"]) == [["N", 4.5], ["S", 2.0]]
    bad = sandbox.run("result = df.groupby('regions')['revenue'].sum()", table)
    assert bad.status == "error" and bad.error_type == "KeyError"
    blocked = sandbox.run("import os\nresult = os.environ", table)
    assert blocked.status == "blocked"


def test_modal_isolation_and_timeout(table: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.sandbox.modal_runner import ModalSandbox

    os.environ["ANALYSTOS_CANARY_SECRET"] = "canary-modal-91"
    sandbox = ModalSandbox()
    code = (
        "import os, socket\n"
        "out = {'canary': 'canary-modal-91' in str(dict(os.environ)),\n"
        "       'db': any('DATABASE_URL' in k or 'SECRET_KEY' in k for k in os.environ)}\n"
        "try:\n    socket.create_connection(('1.1.1.1', 80), timeout=2); out['network'] = 'open'\n"
        "except OSError:\n    out['network'] = 'blocked'\n"
        "result = out\n"
    )
    isolated = sandbox.execute_unchecked(code, table)
    assert isolated.ok, isolated.error_message
    assert isolated.result["value"] == {"canary": False, "db": False, "network": "blocked"}
    monkeypatch.setattr(sandbox.settings, "sandbox_timeout_seconds", 5)
    slow = sandbox.execute_unchecked("while True:\n    pass", table)
    assert slow.status == "timeout"
