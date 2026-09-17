import json
from pathlib import Path

import pytest

from video_editing import delivery


class FakePlatform:
    base_url = "https://video.example"

    def __init__(self):
        self.calls = []
        self.status = "CREATED"
        self.upload_error = False
        self.create_error = False
        self.empty_playlist = False
        self.downloads = []

    def api(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == "/video/create":
            if self.create_error:
                raise TimeoutError("response lost after creating video")
            return {"videoId": "v1", "fileId": "f1", "watchId": "w1"}
        if path == "/video/getVideoStatus":
            return {"status": self.status}
        if path == "/file/getUploadCredentials":
            return {"secretKey": "must-not-be-persisted"}
        if path == "/video/rawFileUploadFinish":
            self.status = "READY"
        if path == "/video/getVideoDetail":
            return {"watchUrl": self.base_url + "/w?v=w1", "visibility": "UNLISTED"}
        if path == "/client/requestClientId":
            return {"clientId": "client1"}
        if path == "/session/requestSessionId":
            return {"sessionId": "session1"}
        if path == "/watchController/getWatchInfo":
            return {"videoId": "v1", "videoStatus": self.status,
                    "multivariantPlaylistUrl": "/master.m3u8"}
        return {}

    def upload(self, credentials, source):
        self.calls.append(("UPLOAD", "raw", str(source)))
        if self.upload_error:
            raise ValueError("network interrupted")

    def text(self, url):
        if url.endswith("master.m3u8"):
            return "#EXTM3U\n" + ("" if self.empty_playlist else "variant.m3u8\n")
        return "#EXTM3U\n#EXTINF:2.4,\nfirst.ts\n#EXTINF:2.4,\nlast.ts\n#EXT-X-ENDLIST\n"

    def download(self, url, target):
        self.downloads.append(target)
        target.write_bytes(b"mock segment")


@pytest.fixture
def source(work, monkeypatch):
    source = work / "video.mp4"
    source.write_bytes(b"test video")
    monkeypatch.setattr(delivery, "probe", lambda path: {
        "video_codec": "h264", "pixel_format": "yuv420p", "duration": 4.8})
    monkeypatch.setattr(delivery, "command", lambda *args: None)
    return source


def test_upload_failure_reuses_video_and_checks_before_success(source, work):
    client = FakePlatform()
    receipt = work / "video.delivery.json"
    client.upload_error = True
    with pytest.raises(ValueError, match="network"):
        delivery.deliver(source, receipt, "测试", wait_seconds=0, client=client)
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["video_id"] == "v1"
    assert "must-not-be-persisted" not in receipt.read_text(encoding="utf-8")
    client.upload_error = False
    result = delivery.deliver(source, receipt, "测试", wait_seconds=0, client=client)
    assert result["status"] == "READY"
    assert result["phone_device_test"] == "not_performed"
    assert sum(path == "/video/create" for _, path, _ in client.calls) == 1
    paths = [path for _, path, _ in client.calls]
    assert paths.index("/video/updateInfo") < paths.index("raw")
    assert client.downloads and all(not p.exists() for p in client.downloads)


def test_lost_create_response_does_not_create_duplicate(source, work):
    client = FakePlatform()
    client.create_error = True
    receipt = work / "video.delivery.json"
    with pytest.raises(TimeoutError):
        delivery.deliver(source, receipt, "测试", client=client)
    with pytest.raises(ValueError, match="创建结果未确认"):
        delivery.deliver(source, receipt, "测试", client=client)
    assert sum(path == "/video/create" for _, path, _ in client.calls) == 1


def test_changed_source_cannot_reuse_receipt(source, work):
    client = FakePlatform()
    receipt = work / "video.delivery.json"
    delivery.deliver(source, receipt, "测试", client=client)
    source.write_bytes(b"different revision")
    with pytest.raises(ValueError, match="文件或目标环境不符"):
        delivery.deliver(source, receipt, "测试", client=client)


def test_ready_without_stream_is_not_delivery_success(source, work):
    client = FakePlatform()
    client.empty_playlist = True
    receipt = work / "video.delivery.json"
    with pytest.raises(ValueError, match="空播放列表"):
        delivery.deliver(source, receipt, "测试", client=client)
    assert json.loads(receipt.read_text(encoding="utf-8"))["stage"] != "verified"


def test_processing_timeout_does_not_upload_again(source, work):
    client = FakePlatform()
    receipt = work / "video.delivery.json"
    receipt.write_text(json.dumps({"source_sha256": delivery.fingerprint(source),
                                  "profile": "prod", "base_url": client.base_url,
                                  "video_id": "v1", "file_id": "f1", "watch_id": "w1",
                                  "stage": "processing"}), encoding="utf-8")
    client.status = "TRANSCODING"
    with pytest.raises(ValueError, match="尚未完成交付"):
        delivery.deliver(source, receipt, "测试", wait_seconds=0, client=client)
    assert all(method != "UPLOAD" and path != "/video/create"
               for method, path, _ in client.calls)


def test_stream_decode_failure_cleans_temporary_files(monkeypatch):
    client = FakePlatform()
    client.status = "READY"

    def fail(*args):
        raise ValueError("corrupt stream")

    monkeypatch.setattr(delivery, "command", fail)
    with pytest.raises(ValueError, match="corrupt stream"):
        delivery.check_delivery(client, "v1", "w1", 4.8)
    assert client.downloads and all(not Path(p).exists() for p in client.downloads)


def test_delayed_status_does_not_repeat_raw_upload(source, work):
    client = FakePlatform()
    original_api = client.api

    def delayed(method, path, data=None):
        result = original_api(method, path, data)
        if path == "/video/rawFileUploadFinish":
            client.status = "CREATED"
        return result

    client.api = delayed
    receipt = work / "video.delivery.json"
    for _ in range(2):
        with pytest.raises(ValueError, match="尚未完成交付"):
            delivery.deliver(source, receipt, "测试", wait_seconds=0, client=client)
    assert sum(method == "UPLOAD" for method, _, _ in client.calls) == 1
