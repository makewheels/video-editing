import copy
import json

import pytest

from video_editing.contracts import Plan
from video_editing.media import local_asset
from video_editing.validation import validate_plan


def test_duration_accounts_for_overlap_and_keeps_evidence(plan_data, validation_root):
    report = validate_plan(Plan.model_validate(plan_data), validation_root)
    assert report["duration_seconds"] == 4.4
    assert report["coverage"][1]["output_range"] == [2, 4.4]
    assert report["coverage"][1]["clear_output_range"] == [2.4, 4.4]


@pytest.mark.parametrize("change,expected", [
    (lambda p: p["clips"].pop(), "最后一段|遗漏"),
    (lambda p: p["assets"][0].update(role="reference"), "参考"),
    (lambda p: p["contents"][0].update(status="uncertain"), "尚未确认"),
    (lambda p: p["contents"][0]["evidence"][0].update(modality="asr"), "连续画面"),
    (lambda p: p["clips"][0].update(source_in=.8), "完整保留"),
    (lambda p: p["clips"][0].update(source_out=4), "超出原片"),
    (lambda p: p["clips"][0].update(transition_out=1.2), "连续画面|完整保留"),
    (lambda p: p["clips"][1].update(transition_out=3), "转场|最后一段"),
    (lambda p: p["clips"][0].update(asset_id="unknown"), "未知"),
    (lambda p: p["output"].update(target_seconds=1), "不能自动删内容"),
    (lambda p: p["output"].update(next_label_seconds=5), "预告字幕"),
    (lambda p: p["contents"][0]["evidence"][0].update(end=99), "证据超出"),
    (lambda p: p["contents"][0]["evidence"][0].update(asset_id="missing"), "证据引用"),
])
def test_rejects_editorial_failures(plan_data, validation_root, change, expected):
    change(plan_data)
    with pytest.raises(ValueError, match=expected):
        validate_plan(Plan.model_validate(plan_data), validation_root)


@pytest.mark.parametrize("change", [
    lambda p: p["clips"].append(copy.deepcopy(p["clips"][0])),
    lambda p: p["clips"][0].update(source_in=float("nan")),
    lambda p: p["clips"][0].update(source_out=float("inf")),
    lambda p: p["output"].update(width=361),
    lambda p: p.update(shell="echo unwanted command"),
    lambda p: p["audio"].update(mode="music"),
    lambda p: p.update(parent_version=1),
    lambda p: p.update(allow_reference_footage=True),
])
def test_rejects_invalid_contract(plan_data, change):
    change(plan_data)
    with pytest.raises(ValueError):
        Plan.model_validate(plan_data)


def test_reference_exception_requires_explicit_reason(plan_data, validation_root):
    plan_data["assets"][0]["role"] = "reference"
    plan_data.update(allow_reference_footage=True, reference_use_reason="本次明确允许引用参考镜头")
    assert validate_plan(Plan.model_validate(plan_data), validation_root)["covered_contents"] == 2


def test_short_external_track_is_not_looped(plan_data, validation_root):
    plan_data["assets"].append({"id": "music", "path": "a.mp4", "role": "music"})
    plan_data["audio"] = {"mode": "music", "asset_id": "music", "rights_note": "自制测试音轨"}
    with pytest.raises(ValueError, match="音轨缺失或比成片短"):
        validate_plan(Plan.model_validate(plan_data), validation_root)


def test_traversal_absolute_paths_and_urls_are_rejected(work):
    inside = work / "inside"
    inside.mkdir()
    (work / "secret.txt").write_text("not media")
    for path in ("../secret.txt", str(work / "secret.txt"), "https://example.com/a.mp4"):
        with pytest.raises(ValueError):
            local_asset(inside, path)


def test_symlink_escape_is_rejected(work):
    inside = work / "inside"
    inside.mkdir()
    target = work / "secret.txt"
    target.write_text("not media")
    try:
        (inside / "link").symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows 当前账号无创建符号链接权限；此用例未验证")
        raise
    with pytest.raises(ValueError):
        local_asset(inside, "link")


def test_generated_schema_matches_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    stored = json.loads((root / "schemas/edit-plan.schema.json").read_text())
    assert stored == Plan.model_json_schema()
