"""单进程渲染，MongoDB租约与持久队列，版本对象隔离。"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pymongo import ReturnDocument

from .store import bucket, db, now, put_file, uid


def claim():
    clock = time.time()
    return db().jobs.find_one_and_update(
        {"$or": [{"state": "queued"}, {"state": "running", "lease_until": {"$lt": clock}}],
         "attempts": {"$lt": 3}},
        {"$set": {"state": "running", "lease_until": clock + 120,
                  "lease_token": uid(), "updated_at": now(), "started_at": now(),
                  "active_stage": "读取工程素材", "stage_events": []}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)


def run_one(job):
    query = {"id": job["id"], "lease_token": job["lease_token"], "state": "running"}
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(20):
            try:
                db().jobs.update_one(query, {"$set": {"lease_until": time.time() + 120}})
            except Exception:
                pass
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with TemporaryDirectory(prefix="editing-job-") as folder:
            packet = Path(folder) / "job.json"
            packet.write_text(json.dumps(job, default=str, ensure_ascii=False))
            process = subprocess.Popen([sys.executable, "-m", "video_editing.server.worker",
                                        "execute", str(packet)], start_new_session=True,
                                        env={**os.environ, "TMPDIR": folder})
            try:
                code = process.wait(timeout=3500)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = -1
            if code:
                raise RuntimeError("剪辑执行未完成，请稍后重试")
    except Exception:
        db().jobs.update_one(query, {"$set": {"state": "failed", "stage": "剪辑未完成",
            "error": "执行中断或超时，可重新提交生成新版本", "updated_at": now()}})
    finally:
        stop.set()
        thread.join(timeout=2)


def execute(packet):
    from video_editing.engine import render_plan

    from .planner import create_plan
    job = json.loads(Path(packet).read_text())
    query = {"id": job["id"], "lease_token": job["lease_token"], "state": "running"}
    def progress(stage):
        result = db().jobs.update_one(query, {"$set": {"stage": stage, "active_stage": stage, "updated_at": now()},
            "$push": {"stage_events": {"stage": stage, "at": now()}}})
        if not result.matched_count:
            raise RuntimeError("任务租约已失效")
    try:
        with TemporaryDirectory(prefix="editing-render-") as folder:
            work, paths = Path(folder), {}
            progress("读取工程素材")
            for asset in job['assets']:
                path = work / (asset['id'] + Path(asset['key']).suffix)
                bucket().get_object_to_file(asset['key'], str(path))
                paths[asset['id']] = path
            plan, notes = create_plan(job, paths, work, progress)
            progress("渲染视频与字幕")
            output = work / 'video.mp4'
            result = render_plan(plan, work, output, timeout=1600)
            progress("保存成片与剪辑记录")
            # Attempt prefixes fence old workers and retain every finished render.
            prefix = job['prefix'] + '/attempt-' + job['lease_token']
            plan_path = work / 'plan.json'
            plan_path.write_text(plan.model_dump_json(indent=2))
            rules_path = work / 'prompt.txt'
            rules_path.write_text(job['rules'] + '\n本轮反馈：' + job['feedback'])
            request_path = work / 'request.json'
            request_path.write_text(json.dumps({k: job.get(k) for k in
                ['id', 'project_id', 'assets', 'feedback', 'mode', 'audio', 'lesson_count',
                 'created_at']}, ensure_ascii=False, indent=2))
            for name, path, mime in [('request.json', request_path, 'application/json'),
                    ('video.mp4', output, 'video/mp4'),
                    ('plan.json', plan_path, 'application/json'),
                    ('report.json', output.with_suffix('.report.json'), 'application/json'),
                    ('prompt.txt', rules_path, 'text/plain; charset=utf-8')]:
                put_file(prefix + '/' + name, path, mime)
            progress("成片已就绪")
            db().jobs.update_one(query, {'$set': {'state': 'ready', 'stage': '成片已就绪',
                'video_key': prefix + '/video.mp4', 'summary': notes,
                'duration': result['duration_seconds'], 'updated_at': now(),
                'technical_check': 'passed', 'semantic_review': 'pending'}})
    except Exception as exc:
        # Do not leak SDK URLs, provider response bodies or credentials.
        message = (str(exc) if isinstance(exc, (ValueError, RuntimeError)) else '处理失败，请重试')
        db().jobs.update_one(query, {'$set': {'state': 'failed', 'stage': '剪辑未完成',
            'error': message[:500], 'updated_at': now()}})


def main():
    while True:
        try:
            db().jobs.update_many({'state': 'running', 'attempts': {'$gte': 3},
                                   'lease_until': {'$lt': time.time()}},
                                  {'$set': {'state': 'failed', 'error': '多次执行中断，请重新提交'}})
            job = claim()
            if job:
                run_one(job)
            else:
                time.sleep(3)
        except Exception:
            time.sleep(10)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'execute':
        execute(sys.argv[2])
    else:
        main()
