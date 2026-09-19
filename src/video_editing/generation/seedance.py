"""Seedance 2.5 素材生成：提交任务、轮询、下载成片。

凭据只从进程环境读取（Infisical 注入），不写入仓库或方案文件。
生成的素材属于外购/合成素材，归档时要标记来源，不能混入原素材目录。
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "doubao-seedance-2-5-260628"
TERMINAL_STATUS = ("succeeded", "failed", "expired", "cancelled")


def _request(method: str, path: str, payload: dict | None = None, *, timeout: float = 120) -> dict:
    base = os.environ["ARK_BASE_URL"].rstrip("/")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + os.environ["ARK_API_KEY"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"方舟接口返回 {exc.code}：{detail}") from None


def build_payload(prompt: str, *, duration: int, ratio: str, resolution: str, audio: bool,
                  model: str = MODEL) -> dict:
    if not 4 <= duration <= 30:
        raise ValueError("Seedance 2.5 时长取值范围为 4-30 秒")
    if resolution not in ("480p", "720p", "1080p"):
        raise ValueError("分辨率只支持 480p/720p/1080p")
    return {
        "model": model,
        "content": [{"type": "text", "text": prompt}],
        "ratio": ratio,
        "duration": duration,
        "resolution": resolution,
        "generate_audio": audio,
    }


def create_task(payload: dict) -> str:
    created = _request("POST", "/contents/generations/tasks", payload)
    task_id = created.get("id")
    if not task_id:
        raise RuntimeError(f"未返回任务 ID：{json.dumps(created, ensure_ascii=False)[:300]}")
    return task_id


def wait_task(task_id: str, *, interval: float = 15, timeout: float = 1800,
              on_status=None) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        result = _request("GET", f"/contents/generations/tasks/{task_id}")
        status = result.get("status")
        if on_status:
            on_status(status)
        if status in TERMINAL_STATUS:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等待超时；任务 {task_id} 状态仍为 {status}，可稍后查询")
        time.sleep(interval)


def download(video_url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(video_url, timeout=300) as response:
        output.write_bytes(response.read())
    return output


def generate(prompt: str, output: Path, *, duration: int = 10, ratio: str = "9:16",
             resolution: str = "720p", audio: bool = False, model: str = MODEL,
             interval: float = 15, timeout: float = 1800, on_status=None) -> dict:
    payload = build_payload(prompt, duration=duration, ratio=ratio, resolution=resolution,
                            audio=audio, model=model)
    task_id = create_task(payload)
    result = wait_task(task_id, interval=interval, timeout=timeout, on_status=on_status)
    if result.get("status") != "succeeded":
        raise RuntimeError(f"生成未成功：{json.dumps(result, ensure_ascii=False)[:500]}")
    video_url = result.get("content", {}).get("video_url")
    if not video_url:
        raise RuntimeError("生成成功但未返回视频地址")
    download(video_url, output)
    return {"task_id": task_id, "status": result.get("status"), "output": str(output),
            "usage": result.get("usage"), "model": model}


def estimate_cost(duration: int, resolution: str) -> float:
    """按公开报道的每秒单价估算；以方舟实际计费为准。"""
    per_second = {"480p": 0.7, "720p": 1.7, "1080p": 2.7}[resolution]
    return round(duration * per_second, 2)
