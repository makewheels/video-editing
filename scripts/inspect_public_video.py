"""从公开分享页读取正常播放源并抽帧；临时素材由调用者负责finally清理。"""
import argparse
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
      'AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1')


def inspect(video_id, work):
    url = f'https://jingxuan.douyin.com/m/video/{video_id}'
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=25) as response:
        html = response.read().decode('utf-8', 'replace')
    body = next(b for _, b in re.findall(r'<script([^>]*)>(.*?)</script>', html, re.S)
                if 'window._SSR_DATA =' in b)
    data = json.JSONDecoder().raw_decode(body.split('window._SSR_DATA =', 1)[1].lstrip())[0]
    detail = data['data']['storeState']['detail']['videoData']['result']
    model = json.loads(detail['video_model'])
    streams = sorted(model['video_list'], key=lambda x: x['video_meta']['size'])
    stream = streams[0]
    video = work / f'{video_id}.mp4'
    request = urllib.request.Request(stream['main_url'],
                                     headers={'User-Agent': UA, 'Referer': url})
    with urllib.request.urlopen(request, timeout=45) as response, video.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(video)], capture_output=True, text=True, check=True)
    meta = json.loads(result.stdout)
    duration = float(meta['format']['duration'])
    times = [.2, .7, 1.5, 2.5] + [round(duration * i / 20, 3) for i in range(1, 20)]
    times.append(max(0, duration-1))
    sheet = Image.new('RGB', (4*300, 6*220), '#101820')
    draw = ImageDraw.Draw(sheet)
    for i, time in enumerate(times):
        frame = work / f'{video_id}-{i}.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(video),
                        '-frames:v', '1', '-vf', 'scale=300:195:force_original_aspect_ratio=decrease',
                        str(frame)], capture_output=True, check=True, timeout=30)
        with Image.open(frame) as image:
            sheet.paste(image, ((i % 4)*300+(300-image.width)//2, (i//4)*220))
        draw.text(((i%4)*300+8, (i//4)*220+199), f'{time:.2f}s', fill='white')
    sheet.save(work / f'{video_id}.jpg')
    record = {'video_id': video_id, 'source': url, 'title': detail['title'],
              'author': detail['media_user']['screen_name'],
              'author_id': detail['media_user']['id'], 'duration_seconds': duration,
              'sample_times_seconds': times, 'sample_count': len(times),
              'stream_codec': stream['video_meta']['codec_type'],
              'stream_dimensions': [stream['video_meta']['vwidth'], stream['video_meta']['vheight']],
              'audio_present': any(x['codec_type']=='audio' for x in meta['streams']),
              'page_play_count': detail.get('play_count'), 'page_like_count': detail.get('digg_count'),
              'review_boundary': '24 sampled frames; not full realtime viewing or listening'}
    (work / f'{video_id}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('ids', nargs='+')
    args = p.parse_args()
    assert args.work.resolve().parent == Path(tempfile.gettempdir()).resolve()
    assert args.work.name.startswith('editing-review.')
    for vid in args.ids:
        try:
            inspect(vid, args.work)
        except Exception as exc:
            print(json.dumps({'video_id': vid, 'error': type(exc).__name__}), flush=True)
