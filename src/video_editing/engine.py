"""使用固定提交的 vedit 编译时间线；仅适配版本、字幕和交付校验。"""

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .contracts import Plan
from .media import command, fingerprint, local_asset, probe, resolve_font
from .validation import validate_plan

CATEGORIES = {"stroke": "泳姿", "start": "出发技巧", "turn": "转身", "drill": "辅助练习",
              "water_skill": "水中技能", "other": "内容展示"}
ENGINE_REVISION = "2d1247887ad1f4461ba01b92a8afc2209fdd212e"


@contextmanager
def task_space():
    """所有派生图、引擎工程和缓存均在系统临时目录中，异常时同样清理。"""
    with tempfile.TemporaryDirectory(prefix="editing-task-") as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        previous = os.environ.get("VEDIT_CACHE")
        os.environ["VEDIT_CACHE"] = str(root / "engine-cache")
        try:
            yield root
        finally:
            if previous is None:
                os.environ.pop("VEDIT_CACHE", None)
            else:
                os.environ["VEDIT_CACHE"] = previous


def title_card(path: Path, label: str, tag: str, plan: Plan, font: Path, position: str):
    width, height = plan.output.width, plan.output.height
    if plan.output.caption_style == "plain":
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        face = ImageFont.truetype(str(font), max(12, round(width * .05)))
        stroke = max(1, round(width / 540))
        if draw.textlength(label, font=face) + 2 * stroke > width * .9:
            raise ValueError("单行动作名称过长，请精简文字，不自动换行或缩小字幕")
        top = position == "top"
        draw.text((width / 2, height * (.09 if top else .90)), label, font=face,
                  anchor="mt" if top else "mb", fill="white", stroke_width=stroke,
                  stroke_fill=(40, 40, 40, 210))
        image.save(path)
        return
    size = max(12, round(width / 16))
    large = ImageFont.truetype(str(font), size)
    small = ImageFont.truetype(str(font), max(10, round(size * .55)))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = round(width * .05)
    lines, line = [], ""
    for char in label:
        if draw.textlength(line + char, font=large) > width - 4 * margin:
            lines.append(line)
            line = ""
        line += char
    lines.append(line)
    box_height = int(size * (len(lines) * 1.35 + 1.7))
    if box_height > height * .35:
        raise ValueError("字幕过长或画布过矮，需精简文字后重新预览")
    top = int(height * .08) if position == "top" else height - int(height * .10) - box_height
    draw.rounded_rectangle((margin, top, width - margin, top + box_height),
                           radius=max(4, size // 3), fill=(8, 31, 43, 225))
    draw.text((margin * 2, top + size * .3), tag, font=small, fill=(246, 216, 100))
    for index, line in enumerate(lines):
        draw.text((margin * 2, top + size * (1 + index * 1.35)), line,
                  font=large, fill="white")
    image.save(path)


def caption_spans(plan: Plan, coverage: list[dict]) -> list[dict]:
    """Keep equal adjacent labels on screen continuously; previews remain opt-in."""
    contents = {c.id: c for c in plan.contents}
    spans = []

    def append(start, end, label, tag, position):
        style = {"label": label, "tag": tag, "position": position}
        if spans and abs(spans[-1]["end"] - start) < 1e-6 and all(
            spans[-1][key] == value for key, value in style.items()
        ):
            spans[-1]["end"] = end
        else:
            spans.append({"start": start, "end": end, **style})

    for index, (clip, row) in enumerate(zip(plan.clips, coverage, strict=True)):
        start, end = row["clear_output_range"]
        advance = plan.output.next_label_seconds if index + 1 < len(plan.clips) else 0
        content = contents[clip.content_id]
        tag = CATEGORIES[content.category] if plan.output.caption_style == "card" else ""
        append(start, end - advance, content.label, tag, clip.caption_position)
        if advance:
            following = contents[plan.clips[index + 1].content_id]
            append(end - advance, row["output_range"][1], f"接下来：{following.label}",
                   "下一段预告", clip.caption_position)
    return spans


def compile_project(plan: Plan, asset_root: Path, work: Path, font: Path, report: dict):
    # Import after assigning the per-task cache; never configure the operator's global tools.
    from vedit.model import Track
    from vedit.store import Store

    store = Store.create(name=plan.project_id, width=plan.output.width,
                         height=plan.output.height, fps=plan.output.fps)
    store.project.tracks.append(Track(id="V2", kind="video", name="动作名称"))
    media = {a.id: store.import_media([str(local_asset(asset_root, a.path))])[0]
             for a in plan.assets}
    for clip, row in zip(plan.clips, report["coverage"], strict=True):
        start, end = row["output_range"]
        native = store.add_clip(media[clip.asset_id].id, "V1", start,
                                clip.source_in, clip.source_out - clip.source_in)
        store.set_audio(native.id, mute=plan.audio.mode != "source")
        if clip.transition_out:
            store.set_transition(native.id, "dissolve", clip.transition_out)
    spans = caption_spans(plan, report["coverage"])
    report["captions"] = spans
    for index, span in enumerate(spans):
        card = work / f"label-{index}.png"
        title_card(card, span["label"], span["tag"], plan, font, span["position"])
        image = store.import_media([str(card)])[0]
        store.add_clip(image.id, "V2", span["start"], 0, span["end"] - span["start"])
    if plan.audio.mode in ("music", "voiceover"):
        native = store.add_clip(media[plan.audio.asset_id].id, "A1", 0, 0,
                                report["duration_seconds"])
        store.set_audio(native.id, gain_db=plan.audio.gain_db, fade_in=.15, fade_out=.25)
    # Reopen the native project during validation. The persistent authority is the neutral plan;
    # its temporary title assets are regenerated on the next run, never saved as broken links.
    store.save(str(work / "native-project.json"))
    return Store.open(str(work / "native-project.json")).project


def compatible_command(argv: list[str]) -> list[str]:
    help_text = command(["ffmpeg", "-hide_banner", "-h", "full"]).stdout
    if "-filter_complex_script" not in help_text:
        return ["-/filter_complex" if x == "-filter_complex_script" else x for x in argv]
    return argv


def encoding_command(argv: list[str], profile: str) -> list[str]:
    argv = list(argv)
    if profile == "compact":
        if argv[argv.index("-c:v") + 1] != "libx264":
            raise ValueError("compact 编码配置目前只验证过 libx264")
        argv[argv.index("-preset") + 1] = "fast"
        argv[argv.index("-crf") + 1] = "23"
        argv[-1:-1] = ["-maxrate", "8M", "-bufsize", "16M"]
    return argv


def verify_output(path: Path, expected: float, width: int, height: int,
                  audio_mode: str, timeout: float = 600, fps: int | None = None) -> dict:
    metadata = probe(path)
    if abs(metadata["duration"] - expected) > .15:
        raise ValueError("输出时长与已验证时间线不符")
    if (metadata["width"], metadata["height"]) != (width, height):
        raise ValueError("输出尺寸不符")
    if metadata["video_codec"] != "h264" or metadata["pixel_format"] != "yuv420p":
        raise ValueError("输出不是兼容手机的 H.264/yuv420p")
    if metadata["has_audio"] != (audio_mode != "mute"):
        raise ValueError("音轨状态与方案不符")
    if fps is not None and Fraction(metadata["frame_rate"]) != fps:
        raise ValueError("输出帧率与方案不符")
    command(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], timeout)
    return {**metadata, "full_decode": "passed", "sha256": fingerprint(path),
            "bytes": path.stat().st_size,
            "semantic_review": "pending", "visual_review": "pending"}


def publish(source: Path, target: Path):
    """只交付检查通过的文件；不覆盖原素材或以前的版本。"""
    created = False
    try:
        with target.open("xb") as output:
            created = True
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def render_plan(plan: Plan, asset_root: Path, output: Path, font: str | None = None,
                timeout: float = 1800) -> dict:
    from vedit.render import RenderOptions, build_command

    if output.suffix.lower() != ".mp4":
        raise ValueError("当前适配器只交付 .mp4")
    sidecar = output.with_suffix(".report.json")
    if output.exists() or sidecar.exists():
        raise ValueError("输出或报告已存在，请选择新的版本文件名")
    output.parent.mkdir(parents=True, exist_ok=True)
    font_path = resolve_font(font)
    report = validate_plan(plan, asset_root)
    source_hashes = {a.id: fingerprint(local_asset(asset_root, a.path)) for a in plan.assets}
    with task_space() as work:
        project = compile_project(plan, asset_root, work, font_path, report)
        staged = work / "result.mp4"
        options = RenderOptions(output=str(staged), prefer_hw=False, hwaccel_decode=False,
                                threads=2, audio=plan.audio.mode != "mute", quality="high")
        argv, duration, warnings, encoder = build_command(project, options, work)
        if abs(duration - report["duration_seconds"]) > 1e-4:
            raise ValueError("上游引擎编译后的时长发生变化")
        argv = encoding_command(compatible_command(argv), plan.output.encoding_profile)
        command(argv, timeout)
        verified = verify_output(staged, duration, plan.output.width, plan.output.height,
                                 plan.audio.mode, timeout, plan.output.fps)
        report.update({"schema_version": "1.0", "project_id": plan.project_id,
                       "version": plan.version, "engine": "vedit", "engine_revision": ENGINE_REVISION,
                       "encoder": encoder, "warnings": warnings, "output": verified,
                       "source_sha256": source_hashes, "plan": plan.model_dump(mode="json")})
        report_file = work / "report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        publish(staged, output)
        try:
            publish(report_file, sidecar)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    return {"output": str(output), "report": str(sidecar), "technical_check": "passed",
            "duration_seconds": duration, "semantic_review": "pending", "visual_review": "pending"}
