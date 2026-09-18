import json
import subprocess
import sys

import numpy as np
import pytest

from video_editing.contracts import Plan
from video_editing.engine import render_plan, task_space, verify_output
from video_editing.media import command, fingerprint, probe

pytestmark = pytest.mark.integration


def test_real_muted_render_and_non_destructive_retry(real_media, work):
    source_root, plan = real_media
    before = fingerprint(source_root / "a.mp4")
    output = work / "成片 空格.mp4"
    result = render_plan(plan, source_root, output)
    assert abs(probe(output)["duration"] - 4.4) < .1
    assert not probe(output)["has_audio"]
    assert fingerprint(source_root / "a.mp4") == before
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert report["covered_contents"] == 2
    assert report["output"]["full_decode"] == "passed"
    assert report["output"]["semantic_review"] == "pending"
    assert result["visual_review"] == "pending"
    original = fingerprint(output)
    with pytest.raises(ValueError, match="已存在"):
        render_plan(plan, source_root, output)
    assert fingerprint(output) == original


def test_source_audio_is_retained(real_media, work):
    source_root, plan = real_media
    data = plan.model_dump()
    data["audio"]["mode"] = "source"
    output = work / "source-audio.mp4"
    render_plan(Plan.model_validate(data), source_root, output)
    assert probe(output)["has_audio"]


def test_source_loudness_normalization_preserves_video(real_media, work):
    from video_editing.engine import normalize_audio

    source_root, plan = real_media
    data = plan.model_dump()
    data["audio"] = {"mode": "source", "normalize_loudness": True}
    output = work / "clear-source.mp4"
    render_plan(Plan.model_validate(data), source_root, output)
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert report["audio_normalization"]["applied"]
    assert report["plan"]["audio"]["mode"] == "source"
    normalized = work / "renormalized.mp4"
    measurement = normalize_audio(output, normalized)["input"]
    assert -17 < float(measurement["input_i"]) < -15
    assert float(measurement["input_tp"]) < -1
    def video_hash(path):
        return command(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
                        "-c", "copy", "-f", "hash", "-"]).stdout
    assert video_hash(output) == video_hash(normalized)


def test_music_replaces_instead_of_mixing_source_audio(real_media, work):
    import shutil

    source_root, plan = real_media
    for name in ("a.mp4", "b.mp4"):
        shutil.copyfile(source_root / name, work / name)
    command(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=880:duration=5", str(work / "tone.wav")])
    data = plan.model_dump()
    data["assets"].append({"id": "music", "path": "tone.wav", "role": "music"})
    data["audio"] = {"mode": "music", "asset_id": "music", "rights_note": "自制测试音轨"}
    output = work / "music.mp4"
    render_plan(Plan.model_validate(data), work, output)
    pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(output),
                                   "-t", "1", "-vn", "-ac", "1", "-ar", "8000",
                                   "-f", "f32le", "-"])
    spectrum = abs(np.fft.rfft(np.frombuffer(pcm, dtype=np.float32)))
    assert spectrum[880] > spectrum[440] * 100


def test_mixed_audio_contains_source_and_music(real_media, work):
    import shutil

    source_root, plan = real_media
    for name in ("a.mp4", "b.mp4"):
        shutil.copyfile(source_root / name, work / name)
    command(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=880:duration=5", str(work / "tone.wav")])
    data = plan.model_dump()
    data["assets"].append({"id": "music", "path": "tone.wav", "role": "music"})
    data["audio"] = {"mode": "mixed", "asset_id": "music", "rights_note": "自制测试音轨",
                     "gain_db": -8, "source_gain_db": -18}
    output = work / "mixed.mp4"
    render_plan(Plan.model_validate(data), work, output)
    pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(output),
                                   "-t", "1", "-vn", "-ac", "1", "-ar", "8000",
                                   "-f", "f32le", "-"])
    spectrum = abs(np.fft.rfft(np.frombuffer(pcm, dtype=np.float32)))
    assert spectrum[440] > spectrum[500] * 100
    assert 2 < spectrum[880] / spectrum[440] < 5


def test_failed_render_does_not_publish_or_leave_workdir(real_media, work, monkeypatch):
    from video_editing import engine

    source_root, plan = real_media
    original = engine.command
    directories = []

    def fail_on_render(argv, timeout=120):
        if str(work) not in " ".join(argv) and any(str(x).endswith("result.mp4") for x in argv):
            from pathlib import Path

            directories.extend(Path(x).parent for x in argv if str(x).endswith("result.mp4"))
            raise subprocess.TimeoutExpired("ffmpeg", .001)
        return original(argv, timeout)

    monkeypatch.setattr(engine, "command", fail_on_render)
    with pytest.raises(subprocess.TimeoutExpired):
        render_plan(plan, source_root, work / "failed.mp4")
    assert not (work / "failed.mp4").exists()
    assert directories and all(not p.exists() for p in directories)


def test_task_space_restores_environment_on_failure(monkeypatch):
    import os

    monkeypatch.setenv("VEDIT_CACHE", "original-cache")
    with pytest.raises(RuntimeError):
        with task_space() as directory:
            assert directory.exists()
            raise RuntimeError("cancel")
    assert not directory.exists()
    assert os.environ["VEDIT_CACHE"] == "original-cache"


def test_truncated_output_rejected(work):
    path = work / "broken.mp4"
    path.write_bytes(b"broken")
    with pytest.raises(ValueError):
        verify_output(path, 1, 360, 640, "mute")


def test_cli_demo_is_json_and_leaves_no_artifacts(work):
    import os

    env = {**os.environ, "TMPDIR": str(work), "TEMP": str(work), "TMP": str(work)}
    result = subprocess.run([sys.executable, "-m", "video_editing.cli", "demo"],
                            env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["technical_check"] == "passed"
    assert not list(work.iterdir())
