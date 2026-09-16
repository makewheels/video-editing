import tempfile
from pathlib import Path

import pytest

from video_editing.contracts import Plan
from video_editing.demo import example_plan, make_sources


@pytest.fixture
def work():
    with tempfile.TemporaryDirectory(prefix="editing-test-") as directory:
        yield Path(directory)


@pytest.fixture
def plan_data():
    return example_plan()


@pytest.fixture
def validation_root(work, monkeypatch):
    for name in ("a.mp4", "b.mp4"):
        (work / name).write_bytes(b"fixture")
    monkeypatch.setattr("video_editing.validation.probe", lambda path: {
        "duration": 3, "video_codec": "h264", "has_audio": True,
        "color_transfer": "bt709"})
    return work


@pytest.fixture(scope="module")
def real_media():
    with tempfile.TemporaryDirectory(prefix="editing-integration-") as directory:
        root = Path(directory)
        make_sources(root)
        yield root, Plan.model_validate(example_plan())
