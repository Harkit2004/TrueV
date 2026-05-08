from __future__ import annotations

import asyncio
from pathlib import Path


def inference_script_path(repo: Path) -> Path:
    return repo / "inference" / "scripts" / "inference_psd.py"


def expected_psd_path(save_dir: Path, image_stem: str) -> Path:
    return save_dir / f"{image_stem}.psd"


async def run_inference_psd(
    *,
    repo: Path,
    python_exe: str,
    src_image: Path,
    save_dir: Path,
    timeout_sec: float,
    group_offload: bool,
) -> None:
    script = inference_script_path(repo)
    if not script.is_file():
        raise FileNotFoundError(f"Missing See-through script: {script}")

    cmd: list[str] = [
        python_exe,
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

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo),
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
