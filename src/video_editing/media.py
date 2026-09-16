"""只读素材探测、受限路径解析和运行环境检查。"""

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path


def command(argv: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(f"{Path(argv[0]).name} 执行失败：{result.stderr[-3000:]}")
    return result


def local_asset(root: Path, path: str) -> Path:
    """服务接口不得传入任意绝对路径、URL 或逃逸根目录的符号链接。"""
    candidate = Path(path)
    if candidate.is_absolute() or "://" in path:
        raise ValueError("素材路径必须相对 --asset-root，不能是 URL 或绝对路径")
    root = root.resolve(strict=True)
    resolved = (root / candidate).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"素材路径超出允许目录或不是文件：{path}")
    return resolved


def probe(path: Path) -> dict:
    raw = json.loads(command([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ]).stdout)
    videos = [x for x in raw["streams"] if x["codec_type"] == "video"]
    audios = [x for x in raw["streams"] if x["codec_type"] == "audio"]
    video = videos[0] if videos else {}
    duration = float(raw.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("素材缺少有效的有限时长")
    return {
        "duration": duration,
        "width": video.get("width"), "height": video.get("height"),
        "video_codec": video.get("codec_name"), "has_audio": bool(audios),
        "audio_codec": audios[0].get("codec_name") if audios else None,
        "pixel_format": video.get("pix_fmt"), "frame_rate": video.get("avg_frame_rate"),
        "rotation": next((x["rotation"] for x in video.get("side_data_list", [])
                          if "rotation" in x), video.get("tags", {}).get("rotate", 0)),
        "color_transfer": video.get("color_transfer"),
    }


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_font(explicit: str | None = None) -> Path:
    if explicit or os.environ.get("EDITING_FONT"):
        path = Path(explicit or os.environ["EDITING_FONT"]).expanduser()
        if not path.is_file():
            raise ValueError("指定的 EDITING_FONT/--font 不存在")
        return path.resolve()
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"),
    ]
    for name in candidates:
        if Path(name).is_file():
            return Path(name)
    raise ValueError("未找到中文字体。安装 Noto CJK，或用 EDITING_FONT/--font 指定字体文件")


def doctor(font: str | None = None) -> dict:
    checks = {}
    for name in ("ffmpeg", "ffprobe"):
        binary = shutil.which(name)
        checks[name] = {"available": bool(binary)}
        if binary:
            checks[name]["version"] = command([name, "-version"]).stdout.splitlines()[0]
    missing = []
    optional = {}
    if checks["ffmpeg"]["available"]:
        filters = {line.split()[1] for line in command(
            ["ffmpeg", "-hide_banner", "-filters"]).stdout.splitlines() if len(line.split()) >= 2}
        encoders = {line.split()[1] for line in command(
            ["ffmpeg", "-hide_banner", "-encoders"]).stdout.splitlines() if len(line.split()) >= 2}
        missing = sorted({"overlay", "scale", "fps", "trim", "concat", "amix"} - filters)
        missing += sorted({"libx264", "aac"} - encoders)
        optional = {name: name in filters for name in
                    ("drawtext", "subtitles", "xfade", "loudnorm", "silencedetect", "blackdetect")}
    try:
        checks["font"] = {"available": True, "file": str(resolve_font(font))}
    except ValueError as exc:
        checks["font"] = {"available": False, "error": str(exc)}
    return {
        "ready": all(x["available"] for x in checks.values()) and not missing,
        "checks": checks, "missing_required": missing, "optional_filters": optional,
        "caption_backend": "Pillow PNG overlay（不依赖 drawtext/libass）",
        "note": "环境检查通过不代表动作识别、账号额度、服务器或手机链路已验证",
    }
