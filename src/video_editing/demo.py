"""无私人素材、无模型 API、无 GPU 的真实端到端演示。"""

import json
import tempfile
from pathlib import Path

from .contracts import Plan
from .engine import render_plan
from .media import command


def example_plan() -> dict:
    return {
        "schema_version": "1.0", "project_id": "synthetic-demo", "version": 1,
        "assets": [{"id": "a", "path": "a.mp4"}, {"id": "b", "path": "b.mp4"}],
        "contents": [
            {"id": "first", "label": "测试画面一", "category": "other", "status": "confirmed",
             "evidence": [{"asset_id": "a", "start": .5, "end": 1.5,
                           "modality": "continuous_visual", "note": "合成色卡，不代表游泳识别"}]},
            {"id": "second", "label": "测试画面二", "category": "other", "status": "confirmed",
             "evidence": [{"asset_id": "b", "start": .5, "end": 1.5,
                           "modality": "continuous_visual", "note": "合成图案，仅检查真实渲染"}]},
        ],
        "clips": [
            {"id": "c1", "asset_id": "a", "content_id": "first", "source_in": 0,
             "source_out": 2.4, "transition_out": .4, "reason": "检查第一段和溶解转场"},
            {"id": "c2", "asset_id": "b", "content_id": "second", "source_in": 0,
             "source_out": 2.4, "reason": "检查第二段和中文字幕"},
        ],
        "audio": {"mode": "mute"},
        "output": {"width": 360, "height": 640, "fps": 25, "target_seconds": 4.4,
                   "tolerance_seconds": .05, "next_label_seconds": .3},
        "rules_snapshot": {"scope": "合成素材测试；数值仅作演示，不是用户长期偏好"},
    }


def make_sources(root: Path):
    for name, source in [("a", "testsrc2"), ("b", "smptebars")]:
        command(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                 f"{source}=s=360x640:r=25:d=3", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-shortest", str(root / f"{name}.mp4")])


def demo(output: Path | None, font: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="editing-demo-") as directory:
        root = Path(directory)
        make_sources(root)
        result = render_plan(Plan.model_validate(example_plan()), root,
                             output or root / "demo.mp4", font)
        if output is None:
            return {"ok": True, "duration_seconds": result["duration_seconds"],
                    "technical_check": "passed", "artifacts": "已自动清理",
                    "note": "仅验证真实渲染，不表示已实现素材语义理解或手机平台"}
        # Persist only the explicitly requested artifact. Sources are synthetic and regenerated.
        report_path = Path(result["report"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["reproduce"] = "uv run editing demo --output <新的成片路径>"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
