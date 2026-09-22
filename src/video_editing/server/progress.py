"""可核对的步骤进度；估时只使用规模相近、同模式的历史任务。"""
from datetime import datetime, timezone
from statistics import median

STEPS = ['等待开始', '读取工程素材', '采样素材画面', '识别教学项目并去重',
         '复核选中动作区间', '渲染视频与字幕', '保存成片与剪辑记录', '成片已就绪']


def stamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


def describe(job, history, queue, clock=None):
    clock = clock if clock is not None else datetime.now(timezone.utc).timestamp()
    steps = STEPS if job.get('mode') != 'quick' else [STEPS[i] for i in (0, 1, 5, 6, 7)]
    state = job['state']
    stage = job.get('active_stage') or job.get('stage')
    index = steps.index(stage) if stage in steps else (0 if state == 'queued' else 1)
    if state == 'ready':
        index = len(steps) - 1
    start = stamp(job.get('started_at')) or stamp(job.get('created_at')) or clock
    end = stamp(job.get('updated_at')) if state in ('ready', 'failed') else clock
    elapsed = max(0, int((end or clock) - start))
    result = {'steps': [{'name': name, 'status': (
        'complete' if state == 'ready' or i < index else
        'failed' if state == 'failed' and i == index else
        'current' if i == index else 'pending')} for i, name in enumerate(steps)],
        'completed': len(steps) if state == 'ready' else index,
        'total': len(steps), 'elapsed_seconds': elapsed, 'estimate_seconds': None,
        'estimate_samples': 0, 'estimate_note': '', 'queue_ahead': 0}
    if state == 'queued':
        result['queue_ahead'] = sum(1 for other in queue if other['id'] != job['id'] and
            (other['state'] == 'running' or other.get('created_at', '') < job['created_at']))
        result['estimate_note'] = '开始处理后估算剩余时间；排队时间不计入剪辑用时'
        return result
    if state != 'running':
        return result
    samples = []
    count = max(1, len(job.get('assets', [])))
    for old in history:
        if old.get('mode') != job.get('mode') or old['id'] == job['id']:
            continue
        old_count = len(old.get('assets', []))
        duration = sum(a.get('duration', 0) for a in job.get('assets', []))
        old_duration = sum(a.get('duration', 0) for a in old.get('assets', []))
        ratio = count / old_count if old_count else 0
        if not .5 <= ratio <= 2:
            continue
        if duration and old_duration and not .5 <= duration / old_duration <= 2:
            continue
        before = stamp(old.get('started_at')) or stamp(old.get('created_at'))
        after = stamp(old.get('updated_at'))
        if before and after and 1 < after - before < 3600:
            samples.append((after - before) * ratio)
    result['estimate_samples'] = len(samples)
    if not samples:
        result['estimate_note'] = '尚无相近素材的历史用时，暂不能可靠估算；下方显示当前步骤'
    else:
        typical = median(samples)
        low, high = typical * .65, typical * 1.8
        if elapsed >= high:
            result['estimate_note'] = '已超过历史用时范围，仍在处理；网络和素材复杂度可能增加耗时'
        else:
            result['estimate_seconds'] = [max(10, int(low - elapsed)),
                                          max(20, int(high - elapsed))]
            result['estimate_note'] = f'参考{len(samples)}次相近任务，估计会随处理情况变化'
    return result
