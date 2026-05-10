from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path


def inference_script_path(repo: Path) -> Path:
    return repo / "inference" / "scripts" / "inference_psd.py"


def expected_psd_path(save_dir: Path, image_stem: str) -> Path:
    return save_dir / f"{image_stem}.psd"


def parse_inference_extra_args(raw: str | None) -> list[str]:
    """Split SEE_THROUGH_INFERENCE_EXTRA_ARGS for subprocess (POSIX shlex rules)."""
    s = (raw or "").strip()
    if not s:
        return []
    return shlex.split(s)


def resolve_python_executable(python_exe: str) -> str:
    """
    SEE_THROUGH_PYTHON must exist on the worker host. Bare names are resolved via PATH.
    Misconfiguration otherwise yields subprocess errno 2 with an opaque message.
    """
    raw = (python_exe or "").strip() or "python"
    p = Path(raw).expanduser()
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(raw)
    if found:
        return found
    raise FileNotFoundError(
        f"See-through Python interpreter not found: {python_exe!r}. "
        "On the GPU worker set SEE_THROUGH_PYTHON to the conda env python "
        "(e.g. $HOME/miniconda3/envs/see_through/bin/python)."
    )


async def run_inference_psd(
    *,
    repo: Path,
    python_exe: str,
    src_image: Path,
    save_dir: Path,
    timeout_sec: float,
    group_offload: bool,
    inference_extra_args: list[str] | None = None,
) -> None:
    repo_root = repo.expanduser().resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(
            f"SEE_THROUGH_REPO is not a directory: {repo_root}. "
            "On the worker, point it at the cloned https://github.com/shitagaki-lab/see-through tree."
        )

    script = inference_script_path(repo_root)
    if not script.is_file():
        raise FileNotFoundError(f"Missing See-through script: {script}")

    resolved_py = resolve_python_executable(python_exe)

    cmd: list[str] = [
        resolved_py,
        str(script),
        "--srcp",
        str(src_image),
        "--save_to_psd",
        "--save_dir",
        str(save_dir),
        "--disable_progressbar",
    ]
    if group_offload:
        cmd.append("--group_offload")
    extra = inference_extra_args or []
    if extra:
        cmd.extend(extra)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(
            f"See-through inference exceeded {timeout_sec}s (killed subprocess)."
        ) from None

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        out = (stdout or b"").decode("utf-8", errors="replace").strip()
        detail = err or out or f"exit code {proc.returncode}"
        raise RuntimeError(f"See-through inference failed: {detail}")
