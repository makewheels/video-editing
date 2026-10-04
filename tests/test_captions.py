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


def test_badge_is_readable_panel_without_category(work):
    data = example_plan(simple=True)
    data["output"]["caption_style"] = "badge"
    plan = Plan.model_validate(data)
    first, second = work / "badge.png", work / "badge-other.png"
    title_card(first, "蹬壁滑行", "泳姿", plan, resolve_font(), "top")
    title_card(second, "蹬壁滑行", "无关分类", plan, resolve_font(), "top")
    assert first.read_bytes() == second.read_bytes()
    with Image.open(first) as image:
        assert image.getpixel((image.width // 2, round(image.height * .08)))[3] == 210
        assert image.getpixel((image.width // 2, image.height // 2))[3] == 0


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


def test_same_title_stays_visible_during_dissolve(validation_root):
    data = example_plan(simple=True)
    data["clips"][0]["transition_out"] = .3
    data["output"]["target_seconds"] = 4.5
    for item in data["contents"]:
        item["label"] = "蛙泳"
    plan = Plan.model_validate(data)
    spans = caption_spans(plan, validate_plan(plan, validation_root)["coverage"])
    assert len(spans) == 1
    assert spans[0]["start"] == 0 and spans[0]["end"] == 4.5


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


def test_numbered_equal_titles_remain_separate(validation_root):
    data = example_plan(simple=True)
    data['output'].update(caption_style='badge', number_clips=True, motion_style='energetic')
    for item in data['contents']:
        item['label'] = '蛙泳'
    plan = Plan.model_validate(data)
    spans = caption_spans(plan, validate_plan(plan, validation_root)['coverage'])
    assert [s['sequence'] for s in spans] == ['01 / 02', '02 / 02']
    assert [s['label'] for s in spans] == ['蛙泳', '蛙泳']


@pytest.mark.integration
def test_animated_numbered_video_preserves_timing_and_audio(real_media, work):
    from video_editing.media import command

    source_root, _ = real_media
    data = example_plan(simple=True)
    data['output'].update(caption_style='badge', number_clips=True, motion_style='energetic')
    data['audio'] = {'mode': 'source'}
    data['clips'][0].update(transition_out=.3, transition_style='wipe_left')
    data['output']['target_seconds'] = 4.5
    plan = Plan.model_validate(data)
    target = work / 'animated.mp4'
    render_plan(plan, source_root, target)
    report = json.loads(target.with_suffix('.report.json').read_text())
    assert report['output']['full_decode'] == 'passed'
    assert report['output']['has_audio']
    assert abs(report['output']['duration'] - 4.5) < .1
    assert len(report['motion']) == 2
    assert [s['sequence'] for s in report['captions']] == ['01 / 02', '02 / 02']
    # The turquoise badge must enter, stay readable, and leave within each clip.
    def pixels_at(time):
        path = work / f'frame-{time}.png'
        command(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(target),
                 '-frames:v', '1', str(path)])
        with Image.open(path) as frame:
            raw = frame.convert('RGB').tobytes()
            return sum(1 for r, g, b in zip(raw[::3], raw[1::3], raw[2::3], strict=True)
                       if g > 140 and b > 130 and r < 100 and abs(g-b) < 70)
    assert pixels_at(.7) > pixels_at(0) + 20
    assert pixels_at(.7) > pixels_at(2.07) + 20


def test_teaching_item_number_reused_across_clips(validation_root):
    data = example_plan(simple=True)
    data['output']['number_contents'] = True
    data['output']['motion_style'] = 'energetic'
    first_id = data['contents'][0]['id']
    data['contents'][0]['evidence'].extend(data['contents'][1]['evidence'])
    data['contents'] = data['contents'][:1]
    data['clips'][1]['content_id'] = first_id
    plan = Plan.model_validate(data)
    spans = caption_spans(plan, validate_plan(plan, validation_root)['coverage'])
    assert [s['label'] for s in spans] == ['01  测试画面一', '01  测试画面一']
    assert all(s['sequence'] is None for s in spans)
