"""生成模块的参数校验与费用估算；测试不发真实请求。"""

import pytest

from video_editing.generation import build_payload, estimate_cost


def test_build_payload_shape():
    payload = build_payload("水下仰视", duration=10, ratio="9:16", resolution="720p", audio=False)
    assert payload["model"] == "doubao-seedance-2-5-260628"
    assert payload["content"] == [{"type": "text", "text": "水下仰视"}]
    assert payload["duration"] == 10
    assert payload["ratio"] == "9:16"
    assert payload["resolution"] == "720p"
    assert payload["generate_audio"] is False


def test_build_payload_audio_flag():
    payload = build_payload("x", duration=4, ratio="16:9", resolution="480p", audio=True)
    assert payload["generate_audio"] is True


@pytest.mark.parametrize("duration", [3, 0, 31])
def test_build_payload_duration_bounds(duration):
    with pytest.raises(ValueError):
        build_payload("x", duration=duration, ratio="9:16", resolution="720p", audio=False)


def test_build_payload_rejects_unknown_resolution():
    with pytest.raises(ValueError):
        build_payload("x", duration=10, ratio="9:16", resolution="4k", audio=False)


def test_estimate_cost_matches_public_rate():
    assert estimate_cost(10, "720p") == 17.0
    assert estimate_cost(4, "480p") == 2.8
    assert estimate_cost(5, "1080p") == 13.5
