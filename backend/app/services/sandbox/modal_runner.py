"""Python sandbox on Modal (SANDBOX_BACKEND=modal).

For hosts without a Docker daemon (Render, Fly, Railway, Kubernetes without privileged pods). Each execution gets a
fresh Modal Sandbox (gVisor-isolated by Modal) with networking blocked, CPU/memory limits and a wall-clock
timeout. It runs the same runner script and the same static pre-check as the Docker backend, and receives no
application secrets: inputs are written into the sandbox filesystem, results are read back, and the sandbox is
terminated. Requires `pip install modal` and Modal credentials (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import SANDBOX_RUNS
from app.core.tracing import span
from app.services.sandbox.docker_runner import SandboxResult
from app.services.sandbox.static_check import StaticCheckResult, check_code

log = get_logger(__name__)
RUNNER = Path(__file__).with_name("runner.py")
PACKAGES = [
    "pandas==2.2.3",
    "numpy==2.1.3",
    "scipy==1.14.1",
    "scikit-learn==1.5.2",
    "matplotlib==3.9.2",
    "pyarrow==18.0.0",
    "statsmodels==0.14.4",
]
_MAX_ARTIFACT_BYTES = 3_000_000


class ModalSandbox:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._image: Any = None
        self._app: Any = None

    def _modal(self) -> Any:
        import modal

        if self._app is None:
            self._app = modal.App.lookup(self.settings.modal_sandbox_app, create_if_missing=True)
            self._image = (
                modal.Image.debian_slim(python_version="3.11")
                .pip_install(*PACKAGES)
                .env({"MPLBACKEND": "Agg", "MPLCONFIGDIR": "/tmp/mpl", "OMP_NUM_THREADS": "1"})  # noqa: S108 - in sandbox
                .add_local_file(str(RUNNER), "/opt/runner/runner.py")
            )
        return modal

    def _limits(self) -> dict[str, Any]:
        s = self.settings
        return {
            "backend": "modal",
            "cpus": s.sandbox_cpus,
            "memory_mb": s.sandbox_memory_mb,
            "timeout_seconds": s.sandbox_timeout_seconds,
            "network": "blocked",
        }

    def available(self) -> tuple[bool, str]:
        if not self.settings.sandbox_enabled:
            return False, "The Python sandbox is disabled (SANDBOX_ENABLED=false)"
        try:
            self._modal()
        except Exception as exc:
            return False, f"Modal sandbox unavailable: {exc.__class__.__name__}"
        return True, "ok (modal)"

    def run(self, code: str, tables: dict[str, Path], *, max_rows: int = 5000) -> SandboxResult:
        with span("sandbox.run", **{"sandbox.backend": "modal"}) as current:
            check = check_code(code)
            if not check.ok:
                SANDBOX_RUNS.labels(status="blocked").inc()
                result = SandboxResult(
                    status="blocked",
                    error_type="StaticCheckFailed",
                    error_message="; ".join(check.violations),
                    static_check=check,
                    limits=self._limits(),
                )
            else:
                result = self.execute_unchecked(code, tables, max_rows=max_rows, check=check)
            current.set_attribute("sandbox.status", result.status)
            return result

    def execute_unchecked(
        self, code: str, tables: dict[str, Path], *, max_rows: int = 5000, check: StaticCheckResult | None = None
    ) -> SandboxResult:
        settings = self.settings
        started = time.perf_counter()
        try:
            modal = self._modal()
        except Exception as exc:
            SANDBOX_RUNS.labels(status="unavailable").inc()
            return SandboxResult(
                status="unavailable",
                error_type="SandboxUnavailable",
                error_message=f"Modal sandbox unavailable: {exc.__class__.__name__}",
                static_check=check,
                limits=self._limits(),
            )
        sandbox = None
        try:
            sandbox = modal.Sandbox.create(
                app=self._app,
                image=self._image,
                block_network=True,
                cpu=settings.sandbox_cpus,
                memory=settings.sandbox_memory_mb,
                timeout=settings.sandbox_timeout_seconds + 60,
                workdir="/work",
            )
            fs = sandbox.filesystem
            fs.make_directory("/work/input/data")
            fs.make_directory("/work/out")
            manifest = {"tables": {name: f"data/{name}.parquet" for name in tables}, "max_rows": max_rows}
            fs.write_text(json.dumps(manifest), "/work/input/manifest.json")
            fs.write_text(code, "/work/input/code.py")
            for name, path in tables.items():
                fs.write_bytes(Path(path).read_bytes(), f"/work/input/data/{name}.parquet")
            exec_started = time.perf_counter()  # the limit applies to the code, not to sandbox start-up
            process = sandbox.exec("python", "-I", "/opt/runner/runner.py", timeout=settings.sandbox_timeout_seconds)
            exit_code = process.wait()
            exec_seconds = time.perf_counter() - exec_started
            stdout, stderr = process.stdout.read()[-20_000:], process.stderr.read()[-20_000:]
            duration = int((time.perf_counter() - started) * 1000)
            if exit_code in (-1, None) or exec_seconds > settings.sandbox_timeout_seconds + 2:
                SANDBOX_RUNS.labels(status="timeout").inc()
                return SandboxResult(
                    status="timeout",
                    error_type="Timeout",
                    error_message=f"Execution exceeded the {settings.sandbox_timeout_seconds}s limit",
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration,
                    exit_code=exit_code,
                    static_check=check,
                    limits=self._limits(),
                )
            if exit_code == 137:
                SANDBOX_RUNS.labels(status="oom").inc()
                return SandboxResult(
                    status="oom",
                    error_type="MemoryError",
                    error_message=f"Execution exceeded the {settings.sandbox_memory_mb} MB memory limit",
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration,
                    exit_code=exit_code,
                    static_check=check,
                    limits=self._limits(),
                )
            try:
                payload = json.loads(fs.read_text("/work/out/result.json"))
            except Exception:
                payload = None
            artifacts = []
            for entry in fs.list_files("/work/out"):
                name = str(getattr(entry, "path", entry)).split("/")[-1]
                if name.endswith(".png"):
                    data = fs.read_bytes(f"/work/out/{name}")
                    if len(data) <= _MAX_ARTIFACT_BYTES:
                        artifacts.append({"file": name, "data": data})
            if payload is None:
                SANDBOX_RUNS.labels(status="error").inc()
                return SandboxResult(
                    status="error",
                    error_type="NoResult",
                    error_message=(stderr.strip().splitlines() or ["No result"])[-1][:500],
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration,
                    exit_code=exit_code,
                    static_check=check,
                    limits=self._limits(),
                )
            titles = {a.get("file"): a.get("title") for a in payload.get("artifacts", [])}
            for artifact in artifacts:
                artifact["title"] = titles.get(artifact["file"], artifact["file"])
            status = "success" if payload.get("status") == "success" else "error"
            SANDBOX_RUNS.labels(status=status).inc()
            return SandboxResult(
                status=status,
                result=payload.get("result"),
                error_type=payload.get("error_type"),
                error_message=payload.get("error_message"),
                line=payload.get("line"),
                stdout=stdout,
                stderr=stderr,
                artifacts=artifacts,
                duration_ms=duration,
                exit_code=exit_code,
                static_check=check,
                limits=self._limits(),
            )
        except Exception as exc:
            log.exception("modal_sandbox_failure")
            SANDBOX_RUNS.labels(status="failure").inc()
            return SandboxResult(
                status="error",
                error_type="SandboxFailure",
                error_message=f"Sandbox infrastructure error: {exc.__class__.__name__}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                static_check=check,
                limits=self._limits(),
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.terminate()
                except Exception:
                    log.warning("modal_sandbox_terminate_failed")
