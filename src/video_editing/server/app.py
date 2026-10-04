"""单所有者手机入口；会话保护，上传流式写入，任务持久化。"""
import hashlib
import hmac
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from .store import db, now, put_file, signed, uid

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_BYTES = 2 * 1024**3


def session_value(expiry):
    sig = hmac.new(os.environ['EDITING_ACCESS_KEY'].encode(), str(expiry).encode(),
                   hashlib.sha256).hexdigest()
    return f'{expiry}.{sig}'


async def owner(request: Request):
    value = request.cookies.get('editing_session', '')
    try:
        expiry = int(value.split('.')[0])
        valid = expiry > time.time() and hmac.compare_digest(value, session_value(expiry))
    except (ValueError, IndexError):
        valid = False
    if not valid:
        raise HTTPException(401, '请先输入访问口令')
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != os.environ['EDITING_ORIGIN'].rstrip('/'):
            raise HTTPException(403, '来源不匹配')


class Login(BaseModel):
    key: str = Field(max_length=200)


@app.post('/api/login')
def login(body: Login, request: Request):
    # Caddy preserves the real address; a bounded per-minute DB counter survives restarts.
    address = request.client.host
    minute = int(time.time() // 60)
    entry = db().login_attempts.find_one_and_update(
        {'_id': f'{address}:{minute}'}, {'$inc': {'count': 1}}, upsert=True,
        return_document=True)
    if entry['count'] > 12:
        raise HTTPException(429, '请稍后再试')
    if not hmac.compare_digest(body.key, os.environ['EDITING_ACCESS_KEY']):
        raise HTTPException(401, '访问口令不正确')
    response = JSONResponse({'ok': True})
    response.set_cookie('editing_session', session_value(int(time.time()) + 30 * 86400),
                        httponly=True, secure=True, samesite='strict', max_age=30 * 86400)
    return response


@app.post('/api/logout', dependencies=[Depends(owner)])
def logout():
    response = JSONResponse({'ok': True})
    response.delete_cookie('editing_session')
    return response


@app.get('/health')
def health():
    db().command('ping')
    return {'ok': True}


@app.get('/')
def index():
    return FileResponse(Path(__file__).with_name('index.html'), headers={
        'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff'})


class ProjectInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.get('/api/projects', dependencies=[Depends(owner)])
def projects():
    rows = list(db().projects.find({}, {'_id': 0}).sort('created_at', -1).limit(100))
    latest = {}
    for job in db().jobs.find({'project_id': {'$in': [p['id'] for p in rows]}},
            {'_id': 0, 'project_id': 1, 'state': 1, 'stage': 1, 'created_at': 1,
             'mode': 1}).sort('created_at', -1):
        latest.setdefault(job['project_id'], job)
    labels = {'ready': '剪辑完成', 'running': '进行中', 'queued': '排队中', 'failed': '剪辑失败'}
    for project in rows:
        uploaded = max((a.get('created_at', '') for a in project['assets']), default='')
        job = latest.get(project['id'])
        state = job['state'] if job else ('pending' if project['assets'] else 'empty')
        if (job and state == 'ready' and job.get('mode') != 'historical'
                and uploaded > job.get('created_at', '')):
            state = 'pending'
        project.update(uploaded_at=uploaded or None, asset_count=len(project['assets']),
                       status=state, status_label=labels.get(state,
                       '待上传' if state == 'empty' else '待剪辑'))
    return rows


@app.post('/api/projects', dependencies=[Depends(owner)])
def create_project(body: ProjectInput):
    project_id = uid()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
    project = {'id': project_id, 'title': body.title, 'created_at': now(),
               'prefix': f'projects/{stamp}-{project_id}', 'assets': []}
    db().projects.insert_one(dict(project))
    return project


def project_or_404(project_id):
    project = db().projects.find_one({'id': project_id}, {'_id': 0})
    if not project:
        raise HTTPException(404, '工程不存在')
    return project


@app.get('/api/projects/{project_id}', dependencies=[Depends(owner)])
def project_detail(project_id: str):
    project = project_or_404(project_id)
    project['versions'] = list(db().jobs.find({'project_id': project_id},
        {'_id': 0, 'lease_token': 0}).sort('created_at', -1).limit(100))
    from .progress import describe
    history = list(db().jobs.find({'state': 'ready', 'mode': {'$in': ['smart', 'quick']}},
        {'_id': 0, 'assets': 1, 'mode': 1, 'id': 1, 'created_at': 1,
         'started_at': 1, 'updated_at': 1}).sort('updated_at', -1).limit(40))
    queue = list(db().jobs.find({'state': {'$in': ['queued', 'running']}},
                              {'_id': 0, 'id': 1, 'state': 1, 'created_at': 1}))
    for version in project['versions']:
        if version.get('mode') != 'historical':
            version['progress'] = describe(version, history, queue)
    return project


@app.post('/api/projects/{project_id}/assets', dependencies=[Depends(owner)])
async def upload(project_id: str, request: Request, filename: str):
    project = project_or_404(project_id)
    if len(project['assets']) >= 30:
        raise HTTPException(400, '每个工程最多30条素材，请新建工程')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.mp4', '.mov', '.m4v', '.mkv', '.webm'):
        raise HTTPException(400, '请选择视频文件')
    if int(request.headers.get('content-length', 0)) > MAX_BYTES:
        raise HTTPException(413, '单条素材不能超过2GB')
    asset_id = uid()
    with TemporaryDirectory(prefix='editing-upload-') as folder:
        path = Path(folder) / ('source' + suffix)
        size = 0
        with path.open('wb') as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, '单条素材不能超过2GB')
                stream.write(chunk)
        if size == 0:
            raise HTTPException(400, '文件为空')
        # Never expose ffprobe/SDK errors or signed source URLs to the browser.
        from starlette.concurrency import run_in_threadpool

        from video_editing.media import probe
        try:
            meta = await run_in_threadpool(probe, path)
            if not meta['video_codec'] or meta['duration'] > 1800:
                raise ValueError('无视频或超过30分钟')
            key = f"{project['prefix']}/assets/{asset_id}/source{suffix}"
            digest = await run_in_threadpool(put_file, key, path, 'video/mp4')
        except Exception:
            raise HTTPException(422, '视频读取或保存失败，请检查文件后重试') from None
    asset = {'id': asset_id, 'name': Path(filename).name[:150], 'key': key,
             'bytes': size, 'sha256': digest, 'duration': meta['duration'], 'created_at': now()}
    db().projects.update_one({'id': project_id}, {'$push': {'assets': asset}})
    return asset


class EditInput(BaseModel):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    feedback: str = Field(default='', max_length=4000)
    mode: str = Field(default='smart', pattern='^(smart|quick)$')
    audio: str = Field(default='source', pattern='^(source|mute)$')
    lesson_count: int | None = Field(default=None, ge=1, le=100)


@app.post('/api/projects/{project_id}/edits', dependencies=[Depends(owner)])
def edit(project_id: str, body: EditInput):
    project = project_or_404(project_id)
    old = db().jobs.find_one({'project_id': project_id, 'request_id': body.request_id}, {'_id': 0})
    if old:
        return old
    if not project['assets']:
        raise HTTPException(400, '请先上传素材')
    if db().jobs.count_documents({'state': {'$in': ['queued', 'running']}}) >= 8:
        raise HTTPException(429, '任务队列已满，请等待当前剪辑完成')
    job_id = uid()
    prompts = Path(__file__).resolve().parents[3] / 'prompts'
    snapshot = '\n\n'.join((prompts / file).read_text() for file in
                           ['course-outcomes.md', 'swimming-terms.md'])
    job = {'id': job_id, 'project_id': project_id, 'request_id': body.request_id,
           'state': 'queued', 'stage': '等待剪辑', 'created_at': now(), 'updated_at': now(),
           'feedback': body.feedback, 'mode': body.mode, 'audio': body.audio,
           'lesson_count': body.lesson_count, 'assets': project['assets'],
           'prefix': f"{project['prefix']}/versions/{job_id}",
           'rules': snapshot, 'attempts': 0}
    try:
        db().jobs.insert_one(dict(job))
    except DuplicateKeyError:
        return db().jobs.find_one({'project_id': project_id, 'request_id': body.request_id}, {'_id': 0})
    return job


@app.get('/api/versions/{job_id}/video', dependencies=[Depends(owner)])
def video(job_id: str, download: bool = False):
    job = db().jobs.find_one({'id': job_id, 'state': 'ready'})
    if not job or not job.get('video_key'):
        raise HTTPException(404, '视频尚未就绪')
    return RedirectResponse(signed(job['video_key'], download), status_code=307,
                            headers={'Cache-Control': 'no-store'})


@app.get('/api/versions/{job_id}/report', dependencies=[Depends(owner)])
def report(job_id: str):
    job = db().jobs.find_one({'id': job_id}, {'_id': 0, 'lease_token': 0})
    if not job:
        raise HTTPException(404, '版本不存在')
    return JSONResponse({key: job.get(key) for key in
                         ['id', 'feedback', 'rules', 'summary', 'state', 'error', 'created_at']})
