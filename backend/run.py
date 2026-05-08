"""Start the API server. Sets PYTHONPATH so `import src` works in uvicorn --reload subprocesses."""

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
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(_BACKEND_ROOT / "src")],
    )
