from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from app.services.sandbox.docker_runner import DockerSandbox
from app.services.sandbox.static_check import check_code
from tests.conftest import docker_available

STATIC_BLOCKED = [
    "import os\nresult = os.environ",
    "import subprocess\nresult = subprocess.run(['ls'])",
    "result = __import__('os').system('id')",
    "result = eval('1+1')",
    "result = open('/etc/passwd').read()",
    "result = pd.read_csv('http://169.254.169.254/')",
    "result = df.to_csv('/tmp/x.csv')",
    "result = ().__class__.__bases__[0].__subclasses__()",
    "result = getattr(pd, 'read_csv')",
    "import socket\nresult = 1",
    "from os import path\nresult = 1",
    "x = 1",  # no result assignment
]


@pytest.mark.parametrize("code", STATIC_BLOCKED)
def test_static_check_blocks(code: str) -> None:
    assert not check_code(code).ok


def test_static_check_allows_analysis_code() -> None:
    code = ("import numpy as np\nfrom scipy import stats\nfrom sklearn.linear_model import LinearRegression\n"
            "g = df.groupby('region')['revenue'].agg(['sum', 'mean']).reset_index()\nresult = g")
    assert check_code(code).ok


pytestmark_docker = pytest.mark.skipif(not docker_available(), reason="Docker sandbox image not available")


@pytest.fixture
def table(tmp_path: Path) -> dict[str, Path]:
    path = tmp_path / "sales.parquet"
    pd.DataFrame({"region": ["N", "S", "N"], "revenue": [1.0, 2.0, 3.5]}).to_parquet(path)
    return {"sales": path}


@pytestmark_docker
@pytest.mark.docker
def test_sandbox_runs_pandas(table: dict[str, Path]) -> None:
    result = DockerSandbox().run("result = df.groupby('region')['revenue'].sum()", table)
    assert result.ok, result.error_message
    assert result.result["type"] == "table"
    assert sorted(result.result["rows"]) == [["N", 4.5], ["S", 2.0]]


@pytestmark_docker
@pytest.mark.docker
def test_sandbox_reports_key_error_for_retry(table: dict[str, Path]) -> None:
    result = DockerSandbox().run("result = df.groupby('regions')['revenue'].sum()", table)
    assert result.status == "error" and result.error_type == "KeyError" and "regions" in result.error_message


@pytestmark_docker
@pytest.mark.docker
def test_container_isolation_without_static_check(table: dict[str, Path]) -> None:
    """The container must hold even for code the static checker would reject."""
    os.environ["ANALYSTOS_CANARY_SECRET"] = "canary-7f3a"
    sandbox = DockerSandbox()
    code = (
        "import os, socket\n"
        "out = {'env_has_canary': 'canary-7f3a' in str(dict(os.environ)), 'uid': os.getuid(),\n"
        "       'docker_sock': os.path.exists('/var/run/docker.sock'), 'host_users': os.path.exists('/Users')}\n"
        "try:\n    s = socket.create_connection(('1.1.1.1', 80), timeout=2); out['network'] = 'open'\n"
        "except OSError:\n    out['network'] = 'blocked'\n"
        "try:\n    open('/work/input/code.py', 'w'); out['input_writable'] = True\n"
        "except OSError:\n    out['input_writable'] = False\n"
        "try:\n    open('/usr/x', 'w'); out['rootfs_writable'] = True\n"
        "except OSError:\n    out['rootfs_writable'] = False\n"
        "result = out\n"
    )
    result = sandbox.execute_unchecked(code, table)
    assert result.ok, result.error_message
    value = result.result["value"]
    assert value == {"env_has_canary": False, "uid": 65534, "docker_sock": False, "host_users": False,
                     "network": "blocked", "input_writable": False, "rootfs_writable": False}


@pytestmark_docker
@pytest.mark.docker
def test_timeout_and_memory_limits(table: dict[str, Path]) -> None:
    sandbox = DockerSandbox()
    timeout = sandbox.execute_unchecked("while True:\n    pass", table)
    assert timeout.status == "timeout"
    oom = sandbox.execute_unchecked("import numpy as np\nx = np.ones(200_000_000)\nresult = 1", table)
    assert oom.status == "oom"


@pytestmark_docker
@pytest.mark.docker
def test_no_leftover_containers() -> None:
    import docker

    client = docker.from_env()
    assert client.containers.list(all=True, filters={"label": "app=analystos-sandbox"}) == []
    assert client.volumes.list(filters={"label": "app=analystos-sandbox"}) == []
