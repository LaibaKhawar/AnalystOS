"""Sandbox entrypoint. Loads input tables, executes the analysis code, writes a JSON result.

Contract (all paths inside the container):
  /work/input/code.py        analysis code (read-only, root-owned)
  /work/input/manifest.json  {"tables": {"name": "data/<file>.parquet"}, "max_rows": 5000}
  /work/input/data/*.parquet input tables (read-only)
  /work/out/result.json      written by this runner
  /work/out/*.png            charts saved through save_chart()

The analysis code sees: pd, np, dfs (dict of DataFrames), df (when exactly one table), save_chart(fig, title).
It must assign its answer to a variable named `result`.
"""

import json
import math
import os
import sys
import traceback

OUT = "/work/out"
MAX_ARTIFACTS = 6


def _jsonable(value):
    import numpy as np
    import pandas as pd

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (pd.Timestamp,)):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (pd.Timedelta,)):
        return value.total_seconds()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is pd.NaT:
        return None
    if isinstance(value, (pd.Period,)):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _serialise(result, max_rows):
    import numpy as np
    import pandas as pd

    if isinstance(result, pd.Series):
        result = result.reset_index()
    if isinstance(result, pd.DataFrame):
        frame = result
        if not isinstance(frame.index, pd.RangeIndex):
            frame = frame.reset_index()
        frame.columns = [str(c) if not isinstance(c, tuple) else "_".join(map(str, c)) for c in frame.columns]
        rows = [[_jsonable(v) for v in row] for row in frame.head(max_rows).itertuples(index=False, name=None)]
        return {
            "type": "table",
            "columns": [{"name": c, "type": str(t)} for c, t in zip(frame.columns, frame.dtypes)],
            "rows": rows,
            "row_count": int(len(frame)),
            "truncated": len(frame) > max_rows,
        }
    if isinstance(result, dict):
        return {"type": "dict", "value": {str(k): _serialise_scalar(v, max_rows) for k, v in list(result.items())[:500]}}
    if isinstance(result, (list, tuple, np.ndarray)):
        return {"type": "list", "value": [_serialise_scalar(v, max_rows) for v in list(result)[:max_rows]]}
    return {"type": "value", "value": _jsonable(result)}


def _serialise_scalar(value, max_rows):
    import pandas as pd

    if isinstance(value, (pd.DataFrame, pd.Series, dict, list, tuple)):
        return _serialise(value, max_rows)
    return _jsonable(value)


def _write(payload):
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, default=str)


def main():
    with open("/work/input/manifest.json", encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open("/work/input/code.py", encoding="utf-8") as handle:
        code = handle.read()
    max_rows = int(manifest.get("max_rows", 5000))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    dfs = {name: pd.read_parquet(os.path.join("/work/input", path)) for name, path in manifest["tables"].items()}
    artifacts = []

    def save_chart(fig=None, title="chart"):
        if len(artifacts) >= MAX_ARTIFACTS:
            raise RuntimeError("Too many charts in one execution")
        fig = fig or plt.gcf()
        name = f"chart_{len(artifacts) + 1}.png"
        fig.savefig(os.path.join(OUT, name), dpi=110, bbox_inches="tight")
        plt.close(fig)
        artifacts.append({"file": name, "title": str(title)[:200]})
        return name

    namespace = {"pd": pd, "np": np, "plt": plt, "dfs": dfs, "save_chart": save_chart, "__name__": "__analysis__"}
    if len(dfs) == 1:
        namespace["df"] = next(iter(dfs.values()))

    try:
        compiled = compile(code, "<analysis>", "exec")
        exec(compiled, namespace)  # noqa: S102 - this IS the sandbox
    except BaseException as exc:  # noqa: BLE001
        tb = traceback.extract_tb(exc.__traceback__)
        user_frames = [f for f in tb if f.filename == "<analysis>"]
        line = user_frames[-1].lineno if user_frames else None
        _write({
            "status": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
            "line": line,
            "artifacts": artifacts,
        })
        print(f"{type(exc).__name__}: {str(exc)[:500]}", file=sys.stderr)
        return 1

    if "result" not in namespace:
        _write({"status": "error", "error_type": "MissingResult",
                "error_message": "The code must assign its final answer to a variable named `result`",
                "artifacts": artifacts})
        return 1
    try:
        payload = {"status": "success", "result": _serialise(namespace["result"], max_rows), "artifacts": artifacts}
        _write(payload)
    except Exception as exc:  # noqa: BLE001
        _write({"status": "error", "error_type": "SerializationError", "error_message": str(exc)[:500],
                "artifacts": artifacts})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
