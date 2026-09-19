"""读取公开分享页的结构化元数据；不把页面数据当作完整视频审片。"""
import argparse
import concurrent.futures
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'


def collect(video_id):
    url = f'https://jingxuan.douyin.com/m/video/{video_id}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode('utf-8', 'replace')
        blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                            html, re.S)
        data = next(json.loads(raw) for raw in blocks
                    if json.loads(raw).get('@type') == 'VideoObject')
        return {'video_id': video_id, 'url': url,
                'observed_at': datetime.now(timezone.utc).isoformat(),
                **{k: data.get(k) for k in ['name', 'uploadDate', 'duration',
                                           'author', 'interactionStatistic']},
                'related_ids': list(dict.fromkeys(re.findall(r'/video/(\d+)', html))),
                'evidence_level': 'public_page_metadata_not_video_review'}
    except Exception as exc:
        return {'video_id': video_id, 'url': url, 'error': type(exc).__name__}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('ids', nargs='+')
    args = p.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(collect, args.ids))
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    for row in rows:
        print(row['video_id'], row.get('author', {}).get('name'), row.get('name'),
              row.get('duration'), row.get('error', ''))
