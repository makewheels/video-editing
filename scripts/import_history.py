"""幂等导入本批已归档素材与成片，只引用既有OSS对象，不搬移原片。"""
import argparse

import oss2

from video_editing.server.store import bucket, db, now


def run(prefix, title):
    objects = list(oss2.ObjectIterator(bucket(), prefix=prefix.rstrip('/') + '/'))
    project_id = 'history-' + prefix.rstrip('/').rsplit('/', 1)[-1]
    assets = []
    videos = []
    for obj in objects:
        relative = obj.key[len(prefix.rstrip('/')) + 1:]
        if relative.startswith('assets/') and relative.lower().endswith('.mp4'):
            assets.append({'id': f'legacy-{len(assets)+1}', 'name': relative.split('/')[-1],
                           'key': obj.key, 'bytes': obj.size, 'duration': 0, 'created_at': now()})
        if relative.startswith('versions/') and relative.lower().endswith('.mp4'):
            videos.append((relative.split('/')[1], obj.key))
    db().projects.update_one({'id': project_id}, {'$setOnInsert': {
        'id': project_id, 'title': title, 'created_at': '2026-09-18T12:48:46+00:00',
        'prefix': prefix.rstrip('/'), 'assets': assets, 'imported': True}}, upsert=True)
    for version, key in videos:
        job_id = project_id + '-' + version
        db().jobs.update_one({'id': job_id}, {'$setOnInsert': {
            'id': job_id, 'project_id': project_id, 'request_id': job_id,
            'state': 'ready', 'stage': '历史成片', 'mode': 'historical',
            'created_at': '2026-09-18T12:48:46+00:00', 'updated_at': now(),
            'video_key': key, 'feedback': version, 'rules': '',
            'summary': '历史成片保留原样。v6尚有重复项目与编号排版待改；技术可播放不代表内容已验收。',
            'semantic_review': 'pending'}}, upsert=True)
    print(f'历史引用导入：{len(assets)}条素材，{len(videos)}个版本')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('prefix')
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    run(args.prefix, args.title)
