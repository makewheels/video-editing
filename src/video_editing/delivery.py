"""Local video-2022 delivery adapter, reusing its CLI account and API helpers.

One process per receipt. This is not a queue or an exactly-once distributed worker.
Raw files, credentials, signed URLs and receipts never belong in Git.
"""

import json
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

from .media import command, fingerprint, probe


class Video2022:
    def __init__(self, profile: str):
        try:
            import truststore

            truststore.inject_into_ssl()
            import oss2
            import requests
            from video_cli import client, config
        except ImportError as exc:
            raise ValueError("需要 video-2022/cli 与系统证书支持：uv run --extra delivery "
                             "--with /path/to/video-2022/cli editing ...") from exc
        self.base_url = config.get_base_url(profile).rstrip("/")
        self.token = config.get_token(profile)
        if not self.token:
            raise ValueError(f"video-cli 的 {profile} profile 尚未登录")
        self.client, self.oss2 = client, oss2
        self.session = requests.Session()

    def api(self, method, path, data=None):
        operation = self.client.get if method == "GET" else self.client.post
        return operation(path, data, base_url=self.base_url, token=self.token)

    def _read(self, url):
        try:
            response = self.session.get(url, timeout=45)
        except Exception as exc:
            # Do not include signed URLs or proxy credentials in exceptions/reports.
            raise ValueError(f"视频流连接失败：{type(exc).__name__}") from None
        if response.status_code != 200:
            raise ValueError(f"视频流读取失败：HTTP {response.status_code}")
        return response

    def text(self, url):
        return self._read(url).text

    def download(self, url, target):
        target.write_bytes(self._read(url).content)

    def upload(self, credentials, source):
        oss2 = self.oss2
        endpoint = credentials["endpoint"]
        if not endpoint.startswith("http"):
            endpoint = "https://" + endpoint
        bucket = oss2.Bucket(oss2.StsAuth(credentials["accessKeyId"],
                             credentials["secretKey"], credentials["sessionToken"]),
                             endpoint, credentials["bucket"], connect_timeout=20)
        key = credentials["key"]
        with tempfile.TemporaryDirectory(prefix="editing-upload-") as directory:
            work = Path(directory).resolve()
            assert work.parent == Path(tempfile.gettempdir()).resolve()
            try:
                oss2.resumable_upload(bucket, key, str(source),
                                     store=oss2.ResumableStore(root=str(work)),
                                     multipart_threshold=5 * 1024 * 1024,
                                     part_size=1024 * 1024, num_threads=3)
            except BaseException as exc:
                # Abort only this attempt's incomplete multipart upload, not the video record.
                for file in work.rglob("*"):
                    if file.is_file():
                        try:
                            record = json.loads(file.read_text(encoding="utf-8"))
                            if record.get("key") == key and record.get("upload_id"):
                                bucket.abort_multipart_upload(key, record["upload_id"])
                        except Exception:
                            # Cleanup is best effort if the storage connection is down.
                            pass
                if not isinstance(exc, Exception):
                    raise
                raise ValueError("原片上传失败；视频记录已保留。检查网络后用同一回执重试，"
                                 "不要重新创建视频。远端未完成分片可能需要存储生命周期清理") from None


def _save(path, receipt):
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_delivery(client, video_id, watch_id, expected_seconds=None):
    """READY plus HLS manifests and decoded first/last segments, not a phone UI test."""
    status = client.api("GET", "/video/getVideoStatus", {"videoId": video_id})
    if status["status"] != "READY":
        raise ValueError(f"平台尚未可播放：{status['status']}；保留回执，稍后重试")
    detail = client.api("GET", "/video/getVideoDetail", {"videoId": video_id})
    browser_client = client.api("GET", "/client/requestClientId")["clientId"]
    session = client.api("GET", "/session/requestSessionId")["sessionId"]
    info = client.api("GET", "/watchController/getWatchInfo", {
        "watchId": watch_id, "clientId": browser_client, "sessionId": session})
    if info.get("videoId") != video_id or info.get("videoStatus") != "READY":
        raise ValueError("播放记录与上传视频不一致或尚未就绪")
    master_url = urljoin(client.base_url + "/", info["multivariantPlaylistUrl"])
    master = client.text(master_url)
    if not master.startswith("#EXTM3U"):
        raise ValueError("主播放列表不是有效 HLS")
    variants = [urljoin(master_url, line.strip()) for line in master.splitlines()
                if line.strip() and not line.startswith("#")]
    if not variants:
        raise ValueError("平台返回空播放列表")
    checks = []
    with tempfile.TemporaryDirectory(prefix="editing-stream-check-") as directory:
        work = Path(directory).resolve()
        assert work.parent == Path(tempfile.gettempdir()).resolve()
        for index, url in enumerate(variants):
            playlist = client.text(url)
            if not playlist.startswith("#EXTM3U") or "#EXT-X-ENDLIST" not in playlist:
                raise ValueError("分辨率播放列表尚未完成")
            lines = playlist.splitlines()
            segments = [urljoin(url, line.strip()) for line in lines
                        if line.strip() and not line.startswith("#")]
            duration = sum(float(line.split(":", 1)[1].split(",")[0]) for line in lines
                           if line.startswith("#EXTINF:"))
            if not segments or (expected_seconds is not None
                                and abs(duration - expected_seconds) > 1):
                raise ValueError("在线播放时长不符或缺少分片")
            for label, segment in (("first", segments[0]), ("last", segments[-1])):
                target = work / f"{index}-{label}.ts"
                client.download(segment, target)
                command(["ffmpeg", "-v", "error", "-xerror", "-i", str(target),
                         "-f", "null", "-"], 120)
            checks.append({"variant": index + 1, "segments": len(segments),
                           "duration_seconds": round(duration, 3),
                           "first_last_decode": "passed"})
    return {"status": "READY", "watch_url": detail["watchUrl"],
            "visibility": detail.get("visibility"), "stream_checks": checks,
            "phone_device_test": "not_performed", "visual_review": "pending"}


def deliver(source: Path, receipt_path: Path, title: str, profile="prod",
            visibility="UNLISTED", wait_seconds=300, client=None):
    """Retry with the same receipt; do not recreate a video after an uncertain create."""
    if source.resolve() == receipt_path.resolve():
        raise ValueError("回执不能覆盖视频")
    client = client or Video2022(profile)
    media = probe(source)
    if media["video_codec"] != "h264" or media["pixel_format"] != "yuv420p":
        raise ValueError("先导出 H.264/yuv420p MP4，再上传")
    command(["ffmpeg", "-v", "error", "-xerror", "-i", str(source), "-f", "null", "-"], 600)
    digest = fingerprint(source)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("source_sha256") != digest or receipt.get("profile") != profile
                or receipt.get("base_url") != client.base_url):
            raise ValueError("回执的文件或目标环境不符，请勿覆盖其他交付记录")
        if not receipt.get("video_id"):
            raise ValueError("上次创建结果未确认。先在平台核对并恢复 video_id/file_id/watch_id，"
                             "不要自动再次创建")
    else:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {"source_sha256": digest, "profile": profile, "base_url": client.base_url,
                   "stage": "create_pending", "duration_seconds": media["duration"]}
        with receipt_path.open("x", encoding="utf-8") as file:
            json.dump(receipt, file, ensure_ascii=False, indent=2)
        created = client.api("POST", "/video/create", {
            "videoType": "USER_UPLOAD", "rawFilename": source.name,
            "size": source.stat().st_size, "ttl": "PERMANENT"})
        receipt.update(video_id=created["videoId"], file_id=created["fileId"],
                       watch_id=created["watchId"], stage="created")
        _save(receipt_path, receipt)
    video_id = receipt["video_id"]
    status = client.api("GET", "/video/getVideoStatus", {"videoId": video_id})["status"]
    if status in ("CREATED", "UPLOADING"):
        client.api("POST", "/video/updateInfo", {
            "id": video_id, "title": title, "visibility": visibility})
        if not receipt.get("raw_uploaded") and receipt["stage"] != "raw_uploaded":
            credentials = client.api("GET", "/file/getUploadCredentials",
                                     {"fileId": receipt["file_id"]})
            client.upload(credentials, source)
            receipt["stage"] = "raw_uploaded"
            receipt["raw_uploaded"] = True
            _save(receipt_path, receipt)
        client.api("GET", "/file/uploadFinish", {"fileId": receipt["file_id"]})
        client.api("GET", "/video/rawFileUploadFinish", {"videoId": video_id})
    deadline = time.monotonic() + wait_seconds
    while True:
        status = client.api("GET", "/video/getVideoStatus", {"videoId": video_id})["status"]
        receipt.update(stage="processing", platform_status=status)
        _save(receipt_path, receipt)
        if status == "READY":
            break
        if "FAIL" in status or time.monotonic() >= deadline:
            raise ValueError(f"平台状态 {status}，尚未完成交付；保留回执稍后重试")
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    result = check_delivery(client, video_id, receipt["watch_id"], media["duration"])
    receipt.update(stage="verified", verification=result)
    _save(receipt_path, receipt)
    return {**result, "receipt": str(receipt_path)}
