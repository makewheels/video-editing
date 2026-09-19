"""按私有清单归档素材批次；凭据仅从进程环境读取，不覆盖不同内容。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

import oss2


def digest(stream):
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return value.hexdigest()


def archive(manifest_path, receipt_path):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    prefix = manifest['prefix'].rstrip('/') + '/'
    if not prefix.startswith('batches/') or '..' in PurePosixPath(prefix).parts:
        raise ValueError('批次路径必须在batches下')
    bucket = oss2.Bucket(oss2.Auth(os.environ['OSS_ACCESS_KEY_ID'],
                                 os.environ['OSS_ACCESS_KEY_SECRET']),
                         os.environ['OSS_ENDPOINT'], os.environ['OSS_BUCKET'],
                         connect_timeout=60)
    receipt = {'bucket': os.environ['OSS_BUCKET'], 'prefix': prefix, 'objects': []}
    for item in manifest['files']:
        relative = PurePosixPath(item['target'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('目标路径必须是批次内相对路径')
        key = prefix + str(relative)
        expected = item.get('sha256')
        if 'local_path' in item:
            source = Path(item['local_path'])
            with source.open('rb') as stream:
                actual = digest(stream)
            if expected and actual != expected:
                raise ValueError('本地源文件与清单散列不符')
            expected = actual
            size = source.stat().st_size
        else:
            source = item['source_key']
            head = bucket.head_object(source)
            size = head.content_length
        if not bucket.object_exists(key):
            headers = {'x-oss-forbid-overwrite': 'true'}
            if expected:
                headers['x-oss-meta-sha256'] = expected
            if 'local_path' in item:
                bucket.put_object_from_file(key, str(source), headers=headers)
            else:
                bucket.copy_object(bucket.bucket_name, source, key, headers=headers)
        head = bucket.head_object(key)
        if head.content_length != size:
            raise ValueError('远端目标大小冲突；禁止覆盖')
        # Local uploads are fully read back. Existing OSS copies are compared by CRC64.
        if expected:
            response = bucket.get_object(key)
            try:
                if digest(response) != expected:
                    raise ValueError('远端全量回读SHA-256不符；禁止覆盖')
            finally:
                response.resp.response.close()
            check = 'sha256_full_readback'
        else:
            origin = bucket.head_object(source)
            if origin.server_crc is None or origin.server_crc != head.server_crc:
                raise ValueError('OSS复制后CRC64不符')
            check = 'crc64_server_copy'
        receipt['objects'].append({'key': key, 'bytes': size, 'sha256': expected,
                                   'verification': check})
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'key': key, 'verified': check}, ensure_ascii=False), flush=True)
    receipt['status'] = 'verified'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        archive(args.manifest, args.receipt)
    except Exception as exc:
        # SDK errors can contain signed URLs or request credentials.
        raise SystemExit(f'归档未完成：{type(exc).__name__}；保留清单并检查连接或对象冲突') from None
