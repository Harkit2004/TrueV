from __future__ import annotations

import asyncio
import copy
import json
import uuid
from typing import Any

import httpx


def prepare_workflow_for_api(workflow: dict[str, Any]) -> dict[str, Any]:
    """Match ComfyUI API expectations: no _meta, strip preview-only nodes."""
    out = copy.deepcopy(workflow)
    strip_preview_ids: list[str] = []
    for node_id, node in out.items():
        if not isinstance(node, dict):
            continue
        node.pop("_meta", None)
        class_type = node.get("class_type")
        if class_type == "PreviewImage":
            strip_preview_ids.append(str(node_id))
    for pid in strip_preview_ids:
        out.pop(pid, None)
    return out


def format_comfy_prompt_error(data: dict[str, Any]) -> str:
    parts: list[str] = []
    err = data.get("error")
    if isinstance(err, dict):
        parts.append(json.dumps(err, indent=2))
    elif err is not None:
        parts.append(str(err))
    ne = data.get("node_errors")
    if ne:
        parts.append("node_errors:\n" + json.dumps(ne, indent=2, default=str))
    return "\n".join(parts) if parts else json.dumps(data, indent=2, default=str)


async def queue_prompt(client: httpx.AsyncClient, workflow: dict[str, Any]) -> str:
    wf = copy.deepcopy(workflow)
    payload = {"prompt": wf, "client_id": str(uuid.uuid4())}
    payload = json.loads(json.dumps(payload))
    r = await client.post("/prompt", json=payload)
    try:
        data = r.json()
    except Exception:
        r.raise_for_status()
        raise RuntimeError(f"ComfyUI /prompt non-JSON: {r.text[:500]}") from None
    if isinstance(data, dict) and data.get("error") is not None:
        raise RuntimeError(format_comfy_prompt_error(data))
    if r.status_code >= 400:
        detail = format_comfy_prompt_error(data) if isinstance(data, dict) else str(data)
        raise RuntimeError(detail or r.text)
    if isinstance(data, dict) and data.get("node_errors"):
        raise RuntimeError(format_comfy_prompt_error(data))
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"Missing prompt_id in ComfyUI response: {data}")
    return str(prompt_id)


async def wait_for_outputs(
    client: httpx.AsyncClient,
    prompt_id: str,
    *,
    poll_interval: float,
    timeout_sec: float,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    last_entry: dict[str, Any] | None = None
    while loop.time() < deadline:
        r = await client.get(f"/history/{prompt_id}")
        if r.status_code != 200:
            await asyncio.sleep(poll_interval)
            continue
        data = r.json()
        entry = data.get(prompt_id)
        if not entry:
            await asyncio.sleep(poll_interval)
            continue
        last_entry = entry
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            msgs = status.get("messages") or []
            raise RuntimeError(f"ComfyUI workflow error: {msgs}")
        outputs = entry.get("outputs")
        if outputs:
            return outputs
        await asyncio.sleep(poll_interval)
    detail = f" after {timeout_sec}s"
    if last_entry is not None:
        detail += f"; last keys: {list(last_entry.keys())}"
    raise TimeoutError(f"Timed out waiting for outputs for {prompt_id}{detail}")


def collect_output_entries(outputs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for node_id, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue
        for key in ("images", "gifs", "audio", "video", "videos"):
            items = node_out.get(key)
            if not items:
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    found.append((str(node_id), item))
    return found


def pick_first_from_node(
    outputs: dict[str, Any],
    node_id: str,
    *,
    extensions: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    for nid, item in collect_output_entries(outputs):
        if nid != node_id:
            continue
        name = str(item.get("filename", ""))
        if extensions is None or any(name.lower().endswith(ext) for ext in extensions):
            return item
    raise KeyError(f"No matching output on node {node_id}")


async def fetch_view_bytes(
    client: httpx.AsyncClient,
    *,
    filename: str,
    subfolder: str = "",
    file_type: str = "output",
) -> bytes:
    params: dict[str, str] = {"filename": filename, "type": file_type}
    if subfolder:
        params["subfolder"] = subfolder
    r = await client.get("/view", params=params)
    r.raise_for_status()
    return r.content
