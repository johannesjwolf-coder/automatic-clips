import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from backend import db, worker, media, gemini
from backend.main import app
from backend.models import Analysis, youtube_url, to_utc

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA", tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app, headers={"X-ClipControl":"1"}) as c:
        yield c

def create(c):
    r = c.post("/api/videos", json={"title":"Test source","youtube_url":"https://youtu.be/abcdefghijk"})
    assert r.status_code == 200
    return r.json()["id"]

def source(c):
    ident = create(c)
    path = db.DATA / "input.mp4"
    media.demo(path)
    with path.open("rb") as stream:
        r = c.post(f"/api/videos/{ident}/original", files={"file":("original.mp4",stream,"video/mp4")})
    assert r.status_code == 200, r.text
    return ident, path

def test_url_allowlist():
    assert youtube_url("https://youtu.be/abcdefghijk?t=8") == "https://www.youtube.com/watch?v=abcdefghijk"
    for invalid in ["http://youtube.com/watch?v=abcdefghijk","https://youtube.com.evil.test/watch?v=abcdefghijk","https://localhost/test","https://user@youtube.com/watch?v=abcdefghijk","https://youtube.com/playlist?list=x"]:
        with pytest.raises(ValueError):
            youtube_url(invalid)

def test_dst():
    assert to_utc("2026-07-01T12:00","Europe/Zurich") == "2026-07-01T10:00:00+00:00"
    assert to_utc("2026-12-01T12:00","Europe/Zurich") == "2026-12-01T11:00:00+00:00"
    for value in ["2026-03-29T02:30","2026-10-25T02:30"]:
        with pytest.raises(ValueError):
            to_utc(value,"Europe/Zurich")

def test_csrf_missing_key_and_limits(client, monkeypatch):
    ident=create(client)
    no_header = TestClient(app).post("/api/demo")
    assert no_header.status_code == 403
    request={"consent":True,"source":"youtube","max_seconds":90}
    assert client.post(f"/api/videos/{ident}/analyze",json=request).status_code == 503
    monkeypatch.setenv("GEMINI_API_KEY","test-never-sent")
    assert client.post(f"/api/videos/{ident}/analyze",json=request).status_code == 409
    client.put("/api/settings",json={"paused":False,"daily_limit":1})
    r=client.post(f"/api/videos/{ident}/analyze",json=request)
    assert r.status_code == 200
    assert client.post(f"/api/videos/{ident}/analyze",json=request).status_code == 409
    client.put("/api/settings",json={"paused":True,"daily_limit":1})
    assert worker.claim() is None
    client.post("/api/jobs/"+r.json()["job_id"]+"/cancel")
    assert worker.claim() is None
    assert client.get("/api/state").json()["usage"]["requests"] == 1

def test_real_render_upload_playback_and_schedule(client):
    ident,path=source(client)
    # A second original cannot invalidate an existing analysis/edit plan.
    with path.open("rb") as stream:
        assert client.post(f"/api/videos/{ident}/original",files={"file":("again.mp4",stream)}).status_code == 409
    bad=client.post(f"/api/videos/{ident}/render",json={"title":"Too long","start":0,"end":50,"subtitles":False})
    assert bad.status_code == 422
    payload={"title":"Real FFmpeg test","start":1,"end":4,"subtitles":False}
    r=client.post(f"/api/videos/{ident}/render",json=payload)
    assert r.status_code == 200,r.text
    assert client.post(f"/api/videos/{ident}/render",json=payload).json()["clip_id"] == r.json()["clip_id"]
    job=worker.claim()
    assert job["kind"] == "render"
    worker.process(job)
    state=client.get("/api/state").json()
    clip=state["clips"][0]
    assert clip["status"] == "ready",state["jobs"]
    result=client.get(clip["url"])
    assert result.status_code == 200
    assert result.headers["content-type"] == "video/mp4"
    ranged=client.get(clip["url"],headers={"Range":"bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100
    meta=media.probe(db.DATA/"clips"/(clip["id"]+".mp4"))
    assert meta["width"] == 1080 and meta["height"] == 1920
    assert meta["audio"] and abs(meta["duration"]-3)<0.3
    plan=client.get("/api/clips/"+clip["id"]+"/plan").json()
    assert plan["start"] == 1 and plan["end"] == 4
    account=client.post("/api/accounts",json={"name":"My Shorts","platform":"youtube","external_id":"UC-test"}).json()
    slot={"clip_id":clip["id"],"account_id":account["id"],"local_time":"2099-08-01T12:00","timezone":"Europe/Zurich"}
    r=client.post("/api/schedules",json=slot)
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    assert client.post("/api/schedules",json=slot).status_code == 409
    assert client.get("/api/state").json()["schedules"][0]["account_id"] == account["id"]
    assert client.delete("/api/schedules/"+r.json()["id"]).status_code == 200
    assert client.get("/api/state").json()["schedules"] == []

def test_restart_recovery(client):
    ident=create(client)
    with db.connection() as c:
        from backend.main import queue
        a=queue(c,ident,"analysis")
        r=queue(c,ident,"render")
        c.execute("UPDATE jobs SET status='running'")
    worker.recover()
    assert db.one("SELECT status FROM jobs WHERE id=?",(a,))["status"] == "failed"
    assert db.one("SELECT status FROM jobs WHERE id=?",(r,))["status"] == "queued"
    # Reopening migrations does not reset data/settings.
    client.put("/api/settings",json={"paused":True,"daily_limit":7})
    db.init()
    assert client.get("/api/state").json()["settings"]["daily_limit"] == 7

def test_gemini_adapter_contract_and_caption_render(client, monkeypatch):
    ident,_=source(client)
    monkeypatch.setenv("GEMINI_API_KEY","test-never-sent")
    result={"summary":"Test response from isolated adapter","language":"de","skip_reason":"","highlights":[
        {"title":"Test highlight","start":1,"end":4,"score":70,"reason":"Mock adapter for validation, not live Gemini.","visual":"Synthetic video","transcript":"Das ist ein Test.",
         "words":[{"start":1.1,"end":1.4,"text":"Das"},{"start":1.5,"end":1.8,"text":"ist"},{"start":2,"end":2.3,"text":"ein"},{"start":2.4,"end":2.9,"text":"Test."}]}]}
    fake=MagicMock()
    fake.models.generate_content.return_value=MagicMock(text=json.dumps(result),usage_metadata=MagicMock(prompt_token_count=120,candidates_token_count=80))
    monkeypatch.setattr(gemini.genai,"Client",lambda **kwargs:fake)
    client.put("/api/settings",json={"paused":False,"daily_limit":2})
    client.post(f"/api/videos/{ident}/analyze",json={"source":"youtube","consent":True,"max_seconds":30})
    worker.process(worker.claim())
    state=client.get("/api/state").json()
    assert state["videos"][0]["analysis"]["highlights"][0]["start"] == 1
    assert state["usage"]["input_tokens"] == 120
    request=fake.models.generate_content.call_args.kwargs
    assert request["contents"].parts[0].file_data.file_uri == "https://www.youtube.com/watch?v=abcdefghijk"
    assert request["config"].response_mime_type == "application/json"
    r=client.post(f"/api/videos/{ident}/render",json={"title":"Captions + crop","start":1,"end":4,"layout":"crop","candidate":0,"subtitles":True})
    assert r.status_code == 200,r.text
    worker.process(worker.claim())
    assert client.get("/api/state").json()["clips"][0]["status"] == "ready"
    assert (db.DATA/"work"/r.json()["clip_id"]/"captions.ass").exists()

def test_bad_gemini_timestamps_and_fake_files(client):
    data={"summary":"test","language":"de","skip_reason":"","highlights":[{"title":"bad","start":1,"end":200,"score":50,"reason":"bad","visual":"","transcript":"","words":[]}]}
    with pytest.raises(ValueError):
        Analysis.model_validate(data).checked(90,300)
    ident=create(client)
    r=client.post(f"/api/videos/{ident}/original",files={"file":("fake.mp4",b"not a video","video/mp4")})
    assert r.status_code == 422
    assert not client.get("/api/state").json()["videos"][0]["has_original"]
