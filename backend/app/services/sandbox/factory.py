"""Select the sandbox backend from configuration."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def get_sandbox() -> Any:
    """DockerSandbox (default) or ModalSandbox; both expose available(), run() and execute_unchecked()."""
    if get_settings().sandbox_backend == "modal":
        from app.services.sandbox.modal_runner import ModalSandbox

        return ModalSandbox()
    from app.services.sandbox.docker_runner import DockerSandbox

    return DockerSandbox()
