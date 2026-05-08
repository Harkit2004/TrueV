"""GPU-side See-through HTTP worker. Bind 127.0.0.1 and reach it from your laptop via SSH -L."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_pp = str(_BACKEND_ROOT)
if os.environ.get("PYTHONPATH"):
    os.environ["PYTHONPATH"] = _pp + os.pathsep + os.environ["PYTHONPATH"]
else:
    os.environ["PYTHONPATH"] = _pp

import uvicorn

if __name__ == "__main__":
    os.chdir(_BACKEND_ROOT)
    host = os.environ.get("SEE_THROUGH_WORKER_HOST", "127.0.0.1")
    port = int(os.environ.get("SEE_THROUGH_WORKER_PORT", "9105"))
    base = f"http://{host}:{port}"
    msg = (
        f"\nSee-through worker starting - open another terminal to test:\n"
        f"  curl -s {base}/health\n"
        f"Uvicorn will log requests below. Leave this process running (Ctrl+C to stop).\n"
    )
    print(msg, file=sys.stderr, flush=True)
    uvicorn.run(
        "src.see_through_service_app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )
