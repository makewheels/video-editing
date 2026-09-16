import argparse
import json
import signal
import sys
import tempfile
from pathlib import Path

from .contracts import Plan
from .demo import demo
from .engine import publish, render_plan
from .media import command, doctor, fingerprint, probe
from .validation import validate_plan


def inspect_media(input_path: Path, sheet: Path | None) -> dict:
    metadata = probe(input_path)
    result = {"media": metadata, "sha256": fingerprint(input_path),
              "note": "关键帧只能用于定位；动作判断仍需查看连续片段"}
    if sheet is not None:
        if not metadata["video_codec"] or not metadata["duration"]:
            raise ValueError("无法为无视频或无有效时长的素材生成联系表")
        if sheet.suffix.lower() not in (".jpg", ".png"):
            raise ValueError("联系表请使用 .jpg 或 .png")
        sheet.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="editing-inspect-") as directory:
            output = Path(directory) / sheet.name
            interval = metadata["duration"] / 12
            command(["ffmpeg", "-v", "error", "-i", str(input_path), "-vf",
                     f"fps=1/{interval},scale=240:-2,tile=4x3", "-frames:v", "1", str(output)])
            publish(output, sheet)
        result["contact_sheet"] = str(sheet)
        result["sample_interval_seconds"] = interval
    return result


def parser():
    p = argparse.ArgumentParser(description="模型无关的剪辑验证工作台；所有命令输出 JSON")
    sub = p.add_subparsers(dest="command", required=True)
    check = sub.add_parser("doctor", help="检查 FFmpeg、滤镜、编码器和中文字体")
    check.add_argument("--font")
    inspect = sub.add_parser("inspect", help="探测媒体；可选生成关键帧联系表")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--sheet", type=Path)
    sub.add_parser("schema", help="输出剪辑方案 JSON Schema")
    for name in ("validate", "render"):
        action = sub.add_parser(name)
        action.add_argument("plan", type=Path)
        action.add_argument("--asset-root", required=True, type=Path)
        if name == "render":
            action.add_argument("--output", required=True, type=Path)
            action.add_argument("--font")
            action.add_argument("--timeout", type=float, default=1800)
    run = sub.add_parser("demo", help="真实渲染合成素材；不需要 API 或私人视频")
    run.add_argument("--output", type=Path, help="省略时检查后自动删除所有演示文件")
    run.add_argument("--font")
    return p


def execute(args) -> dict:
    if args.command == "doctor":
        return doctor(args.font)
    if args.command == "inspect":
        return inspect_media(args.input.resolve(strict=True), args.sheet)
    if args.command == "schema":
        return Plan.model_json_schema()
    if args.command == "demo":
        return demo(args.output, args.font)
    plan = Plan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    if args.command == "validate":
        return validate_plan(plan, args.asset_root)
    if args.timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    return render_plan(plan, args.asset_root, args.output, args.font, args.timeout)


def main():
    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        args = parser().parse_args()
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command == "doctor" and not result["ready"] else 0
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "任务已取消，临时文件已清理"}, ensure_ascii=False),
              file=sys.stderr)
        return 130
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
