import json

import pytest
from PIL import Image

from video_editing.contracts import Plan
from video_editing.demo import example_plan
from video_editing.engine import caption_spans, render_plan, title_card
from video_editing.media import probe, resolve_font
from video_editing.validation import validate_plan


def test_old_plans_keep_card_style_and_quality(plan_data):
    plan = Plan.model_validate(plan_data)
    assert plan.output.caption_style == "card"
    assert plan.output.encoding_profile == "high_quality"


def test_plain_caption_has_no_panel_or_category(work):
    plan = Plan.model_validate(example_plan(simple=True))
    first, second = work / "first.png", work / "second.png"
    title_card(first, "蛙泳", "泳姿", plan, resolve_font(), "top")
    title_card(second, "蛙泳", "无关分类", plan, resolve_font(), "top")
    assert first.read_bytes() == second.read_bytes()
    with Image.open(first) as image:
        alpha = image.getchannel("A")
        painted = sum(count for value, count in enumerate(alpha.histogram()) if value > 0)
        assert 0 < painted < image.width * image.height * .02
        assert image.getpixel((image.width // 10, image.height // 10))[3] == 0


def test_adjacent_equal_titles_have_one_unbroken_span(validation_root):
    data = example_plan(simple=True)
    for item in data["contents"]:
        item["label"] = "蛙泳"
    plan = Plan.model_validate(data)
    spans = caption_spans(plan, validate_plan(plan, validation_root)["coverage"])
    assert len(spans) == 1
    assert spans[0]["start"] == 0 and spans[0]["end"] == 4.8
    assert spans[0]["label"] == "蛙泳" and spans[0]["tag"] == ""


def test_different_titles_still_switch_with_picture(validation_root):
    plan = Plan.model_validate(example_plan(simple=True))
    spans = caption_spans(plan, validate_plan(plan, validation_root)["coverage"])
    assert [s["start"] for s in spans] == [0, 2.4]
    assert all("接下来" not in s["label"] for s in spans)


@pytest.mark.integration
def test_simple_compact_video_is_real_and_records_style(real_media, work):
    source_root, _ = real_media
    plan = Plan.model_validate(example_plan(simple=True))
    target = work / "simple.mp4"
    render_plan(plan, source_root, target)
    actual = probe(target)
    assert abs(actual["duration"] - 4.8) < .1 and not actual["has_audio"]
    report = json.loads(target.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["output"]["full_decode"] == "passed"
    assert len(report["captions"]) == 2
    assert report["plan"]["output"]["caption_style"] == "plain"
    assert report["plan"]["output"]["encoding_profile"] == "compact"
