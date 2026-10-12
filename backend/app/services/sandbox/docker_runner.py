"""Ephemeral Docker sandbox for generated Python.

Per execution:
  1. static pre-flight check (app.services.sandbox.static_check)
  2. a fresh volume + container: no network, read-only rootfs, non-root user (65534), all Linux
     capabilities dropped, no-new-privileges, CPU / memory / PID limits, small noexec /tmp
  3. inputs are copied in (tar) owned by root with mode 0444, so the sandbox user can read but not modify
     them. Nothing from the host is bind-mounted: no source tree, no secrets, no Docker socket
  4. wall-clock timeout enforced from the host (container is killed)
  5. result.json + charts are copied out, then container and volume are destroyed

The container receives an empty environment, so application secrets never reach generated code.
"""

from __future__ import annotations

import io
import json
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import SANDBOX_RUNS
from app.services.sandbox.static_check import StaticCheckResult, check_code

log = get_logger(__name__)
SANDBOX_UID = 65534
_MAX_LOG_BYTES = 20_000
_MAX_ARTIFACT_BYTES = 3_000_000


@dataclass
class SandboxResult:
    status: str  # success | error | timeout | blocked | unavailable | oom
    result: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    line: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # {"file", "title", "data": bytes}
    duration_ms: int = 0
    exit_code: int | None = None
    static_check: StaticCheckResult | None = None
    limits: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "success"


def _tar_inputs(code: str, tables: dict[str, Path], max_rows: int) -> bytes:
    buffer = io.BytesIO()
    manifest = {"tables": {name: f"data/{name}.parquet" for name in tables}, "max_rows": max_rows}

    def add_dir(tar: tarfile.TarFile, name: str, uid: int, mode: int) -> None:
        info = tarfile.TarInfo(name)
        info.type, info.mode, info.uid, info.gid, info.mtime = tarfile.DIRTYPE, mode, uid, uid, int(time.time())
        tar.addfile(info)

    def add_file(tar: tarfile.TarFile, name: str, data: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mode, info.uid, info.gid, info.mtime = len(data), 0o444, 0, 0, int(time.time())
        tar.addfile(info, io.BytesIO(data))

    with tarfile.open(fileobj=buffer, mode="w") as tar:
        add_dir(tar, "input", 0, 0o755)
        add_dir(tar, "input/data", 0, 0o755)
        add_dir(tar, "out", SANDBOX_UID, 0o700)
        add_file(tar, "input/code.py", code.encode())
        add_file(tar, "input/manifest.json", json.dumps(manifest).encode())
        for name, path in tables.items():
            add_file(tar, f"input/data/{name}.parquet", Path(path).read_bytes())
    return buffer.getvalue()


class DockerSandbox:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any = None

    def _docker(self) -> Any:
        if self._client is None:
            import docker

            self._client = docker.from_env(timeout=self.settings.sandbox_timeout_seconds + 30)
        return self._client

    def available(self) -> tuple[bool, str]:
        if not self.settings.sandbox_enabled:
            return False, "The Python sandbox is disabled (SANDBOX_ENABLED=false)"
        try:
            client = self._docker()
            client.ping()
            client.images.get(self.settings.sandbox_image)
        except Exception as exc:
            return False, f"The Python sandbox is unavailable: {exc.__class__.__name__}"
        return True, "ok"

    def run(self, code: str, tables: dict[str, Path], *, max_rows: int = 5000) -> SandboxResult:
        settings = self.settings
        limits = {
            "cpus": settings.sandbox_cpus, "memory_mb": settings.sandbox_memory_mb,
            "timeout_seconds": settings.sandbox_timeout_seconds, "network": "none", "pids": settings.sandbox_pids_limit,
            "read_only_rootfs": True, "user": SANDBOX_UID,
        }
        check = check_code(code)
        if not check.ok:
            SANDBOX_RUNS.labels(status="blocked").inc()
            return SandboxResult(status="blocked", error_type="StaticCheckFailed",
                                 error_message="; ".join(check.violations), static_check=check, limits=limits)
        return self.execute_unchecked(code, tables, max_rows=max_rows, check=check)

    def execute_unchecked(self, code: str, tables: dict[str, Path], *, max_rows: int = 5000,
                          check: StaticCheckResult | None = None) -> SandboxResult:
        """Run code in the container WITHOUT the static pre-check.

        Only `run()` and the isolation test-suite call this; the tests use it to prove the container
        boundary holds on its own for code that a static check would have rejected.
        """
        settings = self.settings
        limits = {
            "cpus": settings.sandbox_cpus, "memory_mb": settings.sandbox_memory_mb,
            "timeout_seconds": settings.sandbox_timeout_seconds, "network": "none", "pids": settings.sandbox_pids_limit,
            "read_only_rootfs": True, "user": SANDBOX_UID,
        }
        ok, reason = self.available()
        if not ok:
            SANDBOX_RUNS.labels(status="unavailable").inc()
            return SandboxResult(status="unavailable", error_type="SandboxUnavailable", error_message=reason,
                                 static_check=check, limits=limits)

        client = self._docker()
        started = time.perf_counter()
        volume = client.volumes.create(labels={"app": "analystos-sandbox"})
        container = None
        try:
            container = client.containers.create(
                settings.sandbox_image,
                user=f"{SANDBOX_UID}:{SANDBOX_UID}",
                network_mode="none",
                mem_limit=f"{settings.sandbox_memory_mb}m",
                memswap_limit=f"{settings.sandbox_memory_mb}m",
                nano_cpus=int(settings.sandbox_cpus * 1e9),
                pids_limit=settings.sandbox_pids_limit,
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                volumes={volume.name: {"bind": "/work", "mode": "rw"}},
                environment={},
                ipc_mode="private",
                labels={"app": "analystos-sandbox"},
                detach=True,
            )
            container.put_archive("/work", _tar_inputs(code, tables, max_rows))
            container.start()
            timed_out = False
            try:
                outcome = container.wait(timeout=settings.sandbox_timeout_seconds)
                exit_code = int(outcome.get("StatusCode", -1))
            except Exception:
                timed_out = True
                exit_code = -1
                try:
                    container.kill()
                except Exception:  # noqa: S110 - already exited
                    pass
            duration = int((time.perf_counter() - started) * 1000)
            stdout = container.logs(stdout=True, stderr=False)[-_MAX_LOG_BYTES:].decode(errors="replace")
            stderr = container.logs(stdout=False, stderr=True)[-_MAX_LOG_BYTES:].decode(errors="replace")
            container.reload()
            oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
            if timed_out:
                SANDBOX_RUNS.labels(status="timeout").inc()
                return SandboxResult(
                    status="timeout", error_type="Timeout",
                    error_message=f"Execution exceeded the {settings.sandbox_timeout_seconds}s limit and was stopped",
                    stdout=stdout, stderr=stderr, duration_ms=duration, exit_code=exit_code, static_check=check,
                    limits=limits,
                )
            if oom or exit_code == 137:
                SANDBOX_RUNS.labels(status="oom").inc()
                return SandboxResult(
                    status="oom", error_type="MemoryError",
                    error_message=f"Execution exceeded the {settings.sandbox_memory_mb} MB memory limit",
                    stdout=stdout, stderr=stderr, duration_ms=duration, exit_code=exit_code, static_check=check,
                    limits=limits,
                )
            payload, artifacts = self._collect(container)
            if payload is None:
                SANDBOX_RUNS.labels(status="error").inc()
                return SandboxResult(
                    status="error", error_type="NoResult",
                    error_message=(stderr.strip().splitlines() or ["The sandbox produced no result"])[-1][:500],
                    stdout=stdout, stderr=stderr, duration_ms=duration, exit_code=exit_code, static_check=check,
                    limits=limits,
                )
            status = "success" if payload.get("status") == "success" else "error"
            SANDBOX_RUNS.labels(status=status).inc()
            titles = {a.get("file"): a.get("title") for a in payload.get("artifacts", [])}
            for artifact in artifacts:
                artifact["title"] = titles.get(artifact["file"], artifact["file"])
            return SandboxResult(
                status=status, result=payload.get("result"), error_type=payload.get("error_type"),
                error_message=payload.get("error_message"), line=payload.get("line"), stdout=stdout, stderr=stderr,
                artifacts=artifacts, duration_ms=duration, exit_code=exit_code, static_check=check, limits=limits,
            )
        except Exception as exc:
            log.exception("sandbox_failure")
            SANDBOX_RUNS.labels(status="failure").inc()
            return SandboxResult(status="error", error_type="SandboxFailure",
                                 error_message=f"Sandbox infrastructure error: {exc.__class__.__name__}",
                                 duration_ms=int((time.perf_counter() - started) * 1000), static_check=check,
                                 limits=limits)
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    log.warning("sandbox_container_cleanup_failed")
            try:
                volume.remove(force=True)
            except Exception:
                log.warning("sandbox_volume_cleanup_failed")

    @staticmethod
    def _collect(container: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        try:
            stream, _ = container.get_archive("/work/out")
        except Exception:
            return None, []
        raw = b"".join(stream)
        payload: dict[str, Any] | None = None
        artifacts: list[dict[str, Any]] = []
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.split("/")[-1]
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                if name == "result.json" and member.size < 50_000_000:
                    try:
                        payload = json.loads(handle.read())
                    except json.JSONDecodeError:
                        payload = None
                elif name.endswith(".png") and member.size <= _MAX_ARTIFACT_BYTES:
                    artifacts.append({"file": name, "data": handle.read()})
        return payload, artifacts
