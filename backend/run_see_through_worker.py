"""GPU-side See-through HTTP worker. Bind 127.0.0.1 and reach it from your laptop via SSH -L."""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_pp = str(_BACKEND_ROOT)
if os.environ.get("PYTHONPATH"):
    os.environ["PYTHONPATH"] = _pp + os.pathsep + os.environ["PYTHONPATH"]
else:
    os.environ["PYTHONPATH"] = _pp

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("SEE_THROUGH_WORKER_HOST", "127.0.0.1")
    port = int(os.environ.get("SEE_THROUGH_WORKER_PORT", "9105"))
    uvicorn.run(
        "src.see_through_service_app:app",
        host=host,
        port=port,
        reload=False,
    )
