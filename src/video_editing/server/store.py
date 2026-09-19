"""MongoDB 记录与私有 OSS。配置仅来自运行时环境。"""
import hashlib
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote

import oss2
from pymongo import MongoClient


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


@lru_cache
def db():
    client = MongoClient(os.environ["EDITING_MONGO_URI"], serverSelectionTimeoutMS=10000)
    database = client.get_default_database()
    database.jobs.create_index([("project_id", 1), ("request_id", 1)], unique=True)
    database.jobs.create_index([("state", 1), ("lease_until", 1)])
    return database


@lru_cache
def bucket():
    return oss2.Bucket(oss2.Auth(os.environ["OSS_ACCESS_KEY_ID"],
                                os.environ["OSS_ACCESS_KEY_SECRET"]),
                       os.environ["OSS_ENDPOINT"], os.environ["OSS_BUCKET"])


def put_file(key, path, content_type="application/octet-stream"):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while part := stream.read(1024 * 1024):
            digest.update(part)
    headers = {"x-oss-forbid-overwrite": "true", "Content-Type": content_type,
               "x-oss-meta-sha256": digest.hexdigest()}
    bucket().put_object_from_file(key, str(path), headers=headers)
    head = bucket().head_object(key)
    if head.content_length != os.path.getsize(path):
        raise ValueError("存储大小验证失败")
    return digest.hexdigest()


def signed(key, download=False):
    params = {}
    if download:
        params["response-content-disposition"] = "attachment; filename=swimming.mp4; filename*=UTF-8''" + quote("游泳剪辑.mp4")
    return bucket().sign_url("GET", key, 3600, params=params, slash_safe=True)

