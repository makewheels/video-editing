import time

import mongomock
import pytest
from fastapi.testclient import TestClient

from video_editing.server import app as web
from video_editing.server import worker


@pytest.fixture
def client(monkeypatch):
    database = mongomock.MongoClient().editing
    database.jobs.create_index([('project_id', 1), ('request_id', 1)], unique=True)
    monkeypatch.setattr(web, 'db', lambda: database)
    monkeypatch.setattr(worker, 'db', lambda: database)
    monkeypatch.setenv('EDITING_ACCESS_KEY', 'test-access-only')
    monkeypatch.setenv('EDITING_ORIGIN', 'https://testserver')
    with TestClient(web.app, base_url='https://testserver') as client:
        yield client, database


def login(client):
    assert client.post('/api/login', json={'key': 'test-access-only'}).status_code == 200


def test_private_projects_require_session_and_origin(client):
    client, _ = client
    assert client.get('/api/projects').status_code == 401
    login(client)
    assert client.post('/api/projects', json={'title': '课程'},
                       headers={'Origin': 'https://attacker.invalid'}).status_code == 403
    assert client.get('/api/projects').json() == []
    client.post('/api/logout')
    assert client.get('/api/projects').status_code == 401


def test_version_submission_is_idempotent_and_snapshots_assets(client):
    client, database = client
    login(client)
    p = client.post('/api/projects', json={'title': '课程'}).json()
    database.projects.update_one({'id': p['id']}, {'$set': {'assets': [
        {'id': 'source', 'key': 'private/source.mp4'}]}})
    route = '/api/projects/' + p['id'] + '/edits'
    payload = {'request_id': 'request-unique', 'mode': 'quick'}
    a, b = client.post(route, json=payload), client.post(route, json=payload)
    assert a.status_code == b.status_code == 200
    assert a.json()['id'] == b.json()['id']
    database.projects.update_one({'id': p['id']}, {'$set': {'assets': []}})
    job = database.jobs.find_one()
    assert len(job['assets']) == 1 and '教学项目' in job['rules']
    assert client.get('/api/versions/' + job['id'] + '/video').status_code == 404


def test_expired_worker_lease_is_reclaimed_and_fenced(client):
    _, database = client
    database.jobs.insert_one({'id': 'job', 'project_id': 'p', 'request_id': 'r',
        'state': 'running', 'attempts': 1, 'lease_token': 'old',
        'lease_until': time.time() - 10, 'created_at': '2026'})
    new = worker.claim()
    assert new['attempts'] == 2 and new['lease_token'] != 'old'
    result = database.jobs.update_one({'id': 'job', 'lease_token': 'old'},
                                     {'$set': {'state': 'ready'}})
    assert result.matched_count == 0
    assert worker.claim() is None


def test_oversized_upload_rejected_before_reading_body(client):
    client, _ = client
    login(client)
    p = client.post('/api/projects', json={'title': '课程'}).json()
    r = client.post('/api/projects/' + p['id'] + '/assets?filename=x.mp4',
                    content=b'x', headers={'Content-Length': str(3 * 1024**3)})
    assert r.status_code == 413


def test_model_number_prefix_is_removed_before_item_numbering(real_media, monkeypatch):
    from video_editing.engine import caption_spans
    from video_editing.server import planner
    from video_editing.validation import validate_plan

    root, _ = real_media
    decision = planner.Decision(items=[planner.Item(asset_id=key, start=.1, end=2.8,
        label=label, category='water_skill', reason='测试区间') for key, label in
        [('a', '01 入水练习'), ('b', '02 入水练习')]], notes='抽帧待核对')
    monkeypatch.setattr(planner, 'sheet', lambda *args, **kwargs: None)
    monkeypatch.setattr(planner, 'infer', lambda *args: decision)
    plan, _ = planner.create_plan({'project_id': 'test', 'mode': 'smart', 'audio': 'source',
        'feedback': '', 'rules': ''}, {'a': root / 'a.mp4', 'b': root / 'b.mp4'}, root, lambda _: None)
    assert len(plan.contents) == 1 and plan.contents[0].label == '入水练习'
    spans = caption_spans(plan, validate_plan(plan, root)['coverage'])
    assert [s['label'] for s in spans] == ['01  入水练习', '01  入水练习']
