import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError
from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from . import db, gemini, media
from .models import VideoCreate, AnalyzeRequest, RenderRequest, Settings, Account, Schedule, youtube_url, to_utc

@asynccontextmanager
async def lifespan(app):
    db.init()
    yield
app = FastAPI(title="ClipControl", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

@app.middleware("http")
async def safety(request: Request, call_next):
    # Same-origin UI uses this header; cross-origin browser forms cannot set it.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-clipcontrol") != "1":
        return JSONResponse({"detail": "Anfrage stammt nicht aus dem Kontrollzentrum."}, status_code=403)
    origin = request.headers.get("origin")
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    allowed_origins = {"https://" + host, "http://" + host}
    # Codespaces can replace Host without sending X-Forwarded-Host.
    # Allow only this workspace's exact private forwarded-port origin.
    codespace = os.getenv("CODESPACE_NAME")
    forwarding_domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if codespace and forwarding_domain:
        allowed_origins.add(f"https://{codespace}-8000.{forwarding_domain}")
        # GitHub forwarding rewrites Origin to this HTTPS loopback target.
        allowed_origins.add("https://localhost:8000")
    if origin and origin not in allowed_origins:
        return JSONResponse({"detail": "Fremder Ursprung nicht erlaubt."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    return response

def require_video(ident):
    row = db.one("SELECT * FROM videos WHERE id=?", (ident,))
    if not row:
        raise HTTPException(404, "Video nicht gefunden.")
    return db.decode(row)

def queue(c, video_id, kind, payload=None):
    ident, created = db.uid(), db.now()
    c.execute("INSERT INTO jobs(id,video_id,kind,payload,status,stage,created,updated) VALUES(?,?,?,?,'queued','Wartet auf Worker',?,?)",
        (ident, video_id, kind, json.dumps(payload or {}), created, created))
    return ident

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/state")
def state():
    videos = [db.decode(v) for v in db.rows("SELECT * FROM videos ORDER BY created DESC")]
    clips = [db.decode(c) for c in db.rows("SELECT * FROM clips ORDER BY created DESC")]
    jobs = [db.decode(j) for j in db.rows("SELECT * FROM jobs ORDER BY created DESC LIMIT 100")]
    for v in videos:
        v["has_original"] = bool(v.pop("original"))
        v["original_url"] = "/api/videos/" + v["id"] + "/original" if v["has_original"] else None
    for c in clips:
        c.pop("file", None)
        c["url"] = "/api/clips/" + c["id"] + "/video" if c["status"] == "ready" else None
    settings = db.one("SELECT paused,daily_limit FROM settings WHERE id=1")
    usage = db.one("SELECT COUNT(*) AS requests,SUM(input_tokens) AS input_tokens,SUM(output_tokens) AS output_tokens FROM usage WHERE day=?", (db.now()[:10],))
    return {"videos": videos, "clips": clips, "jobs": jobs, "settings": settings,
        "accounts": db.rows("SELECT * FROM accounts"),
        "schedules": db.rows("SELECT s.*,a.name AS account_name,a.platform,c.title AS clip_title FROM schedules s JOIN accounts a ON a.id=s.account_id JOIN clips c ON c.id=s.clip_id ORDER BY scheduled_at"),
        "events": db.rows("SELECT * FROM events ORDER BY id DESC LIMIT 60"),
        "usage": usage, "system": {"gemini": gemini.available(), "model": gemini.MODEL, "tts_model": gemini.TTS_MODEL,
            "ffmpeg": bool(shutil.which(media.FFMPEG)), "ffprobe": bool(shutil.which(media.FFPROBE)),
            "worker": db.one("SELECT value FROM runtime WHERE key='worker_heartbeat'"),
            "publishing": False, "access": "Codespaces: Port privat lassen. Noch keine öffentliche Anmeldung.",
            "version": "0.1.0"}}

@app.put("/api/settings")
def update_settings(body: Settings):
    with db.connection() as c:
        c.execute("UPDATE settings SET paused=?,daily_limit=? WHERE id=1", (body.paused, body.daily_limit))
        db.event("Verarbeitung pausiert" if body.paused else "Einstellungen gespeichert", f"Tageslimit: {body.daily_limit} Gemini-Aufträge (UTC-Tag)", c)
    return body

@app.post("/api/videos")
def create_video(body: VideoCreate):
    try:
        url = youtube_url(body.youtube_url) if body.youtube_url else None
    except ValueError as e:
        raise HTTPException(422, str(e))
    ident = db.uid()
    with db.connection() as c:
        c.execute("INSERT INTO videos(id,title,youtube_url,created) VALUES(?,?,?,?)", (ident, body.title, url, db.now()))
        db.event("Video angelegt", body.title, c)
    return {"id": ident}

@app.post("/api/demo")
def create_demo():
    if not shutil.which(media.FFMPEG):
        raise HTTPException(503, "FFmpeg ist nicht installiert.")
    ident = db.uid()
    with db.connection() as c:
        if c.execute("SELECT 1 FROM jobs WHERE kind='demo' AND status IN ('queued','running')").fetchone():
            raise HTTPException(409, "Ein Testvideo wird bereits erzeugt.")
        c.execute("INSERT INTO videos(id,title,created,demo) VALUES(?,?,?,1)", (ident, "Technisches Testvideo · 12 Sekunden", db.now()))
        queue(c, ident, "demo")
        db.event("Technisches Testvideo angefordert", "Synthetisches Testbild und Testton; keine KI-Analyse.", c)
    return {"id": ident}

@app.post("/api/videos/{ident}/original")
async def upload(ident: str, file: UploadFile):
    require_video(ident)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
        raise HTTPException(422, "Bitte MP4, MOV, MKV oder WebM hochladen.")
    # Immutable association: each video gets one original; replace via a new video.
    if require_video(ident).get("original"):
        raise HTTPException(409, "Dieses Video hat bereits eine Originaldatei. Für anderes Material ein neues Video anlegen.")
    path = db.DATA / "originals" / (db.uid() + suffix)
    total = 0
    try:
        with path.open("wb") as target:
            while chunk := await file.read(1024*1024):
                total += len(chunk)
                if total > int(os.getenv("MAX_UPLOAD_MB", "1024")) * 1024 * 1024:
                    raise HTTPException(413, "Die Datei überschreitet das konfigurierte Upload-Limit.")
                target.write(chunk)
        try:
            meta = await run_in_threadpool(media.probe, path)
        except (ValueError, subprocess.SubprocessError, FileNotFoundError):
            raise HTTPException(422, "Kein unterstütztes Video oder FFprobe nicht verfügbar. Datei prüfen.")
        with db.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT original FROM videos WHERE id=?", (ident,)).fetchone()[0]:
                raise HTTPException(409, "Es wurde bereits eine Originaldatei zugeordnet.")
            c.execute("UPDATE videos SET original=?,metadata=? WHERE id=?", ("originals/" + path.name, json.dumps(meta), ident))
            db.event("Originaldatei geprüft und zugeordnet", f"Video {ident}; {meta['duration']:.1f} Sekunden", c)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"metadata": meta}

@app.post("/api/videos/{ident}/analyze")
def analyze(ident: str, body: AnalyzeRequest):
    video = require_video(ident)
    if not body.consent:
        raise HTTPException(422, "Bitte bestätigen, dass Gemini den gewählten Inhalt analysieren darf.")
    if not gemini.available():
        raise HTTPException(503, "GEMINI_API_KEY fehlt. Auf dem Server in .env eintragen und die Anwendung neu starten.")
    if body.source == "youtube" and not video["youtube_url"]:
        raise HTTPException(422, "YouTube-Link fehlt.")
    if body.source == "original" and not video["original"]:
        raise HTTPException(422, "Originaldatei benötigt.")
    with db.connection() as c:
        c.execute("BEGIN IMMEDIATE")
        settings = c.execute("SELECT * FROM settings WHERE id=1").fetchone()
        if settings["paused"]:
            raise HTTPException(409, "Verarbeitung ist pausiert.")
        day = db.now()[:10]
        used = c.execute("SELECT COUNT(*) FROM usage WHERE day=?", (day,)).fetchone()[0]
        if used >= settings["daily_limit"]:
            raise HTTPException(409, "Tageslimit erreicht oder noch nicht eingerichtet. In Einstellungen ein Auftragslimit festlegen.")
        try:
            job = queue(c, ident, "analysis", body.model_dump())
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Für dieses Video läuft bereits eine Analyse.")
        c.execute("INSERT INTO usage(job_id,day) VALUES(?,?)", (job, day))
        db.event("Gemini-Analyse eingeplant", video["title"], c)
    return {"job_id": job}

@app.post("/api/videos/{ident}/render")
def render(ident: str, body: RenderRequest):
    video = require_video(ident)
    if not video["original"]:
        raise HTTPException(409, "Originaldatei benötigt. Der YouTube-Link wird nur zur Analyse verwendet.")
    if body.end > video["metadata"]["duration"] + 0.05:
        raise HTTPException(422, "Das Ende liegt ausserhalb der Originaldatei.")
    plan = body.model_dump()
    plan.update({"original": video["original"], "words": [], "selection": "Manueller Ausschnitt", "version": 1})
    if body.candidate is not None:
        candidates = (video.get("analysis") or {}).get("highlights", [])
        if body.candidate >= len(candidates):
            raise HTTPException(422, "Highlight nicht gefunden.")
        candidate = candidates[body.candidate]
        plan["words"] = candidate["words"]
        plan["selection"] = candidate["reason"]
        plan["model"] = video["analysis"].get("model")
        plan["analysis_source"] = video["analysis"].get("source")
    if body.voiceover:
        # Der Sprechertext ersetzt geschätzte Wortzeitcodes; der Ausschnitt geht zur Vertonung an Google.
        plan["words"] = []
        if not body.consent:
            raise HTTPException(422, "Bitte bestätigen, dass Gemini den Ausschnitt für den KI-Sprecher verarbeiten darf.")
        if not gemini.available():
            raise HTTPException(503, "GEMINI_API_KEY fehlt. Auf dem Server in .env eintragen und die Anwendung neu starten.")
    elif body.subtitles and not plan["words"]:
        raise HTTPException(422, "Keine Wortzeitstempel vorhanden. Untertitel ausschalten oder zuerst analysieren.")
    with db.connection() as c:
        c.execute("BEGIN IMMEDIATE")
        settings = c.execute("SELECT * FROM settings WHERE id=1").fetchone()
        if settings["paused"]:
            raise HTTPException(409, "Verarbeitung ist pausiert.")
        existing = c.execute("SELECT c.id,c.job_id FROM clips c JOIN jobs j ON j.id=c.job_id WHERE c.video_id=? AND c.plan=? AND j.status IN ('queued','running')", (ident, json.dumps(plan))).fetchone()
        if existing:
            return {"clip_id": existing["id"], "job_id": existing["job_id"]}
        day = db.now()[:10]
        if body.voiceover and c.execute("SELECT COUNT(*) FROM usage WHERE day=?", (day,)).fetchone()[0] >= settings["daily_limit"]:
            raise HTTPException(409, "Tageslimit erreicht oder noch nicht eingerichtet. In Einstellungen ein Auftragslimit festlegen.")
        job = queue(c, ident, "render", {"voiceover": body.voiceover})
        if body.voiceover:
            c.execute("INSERT INTO usage(job_id,day) VALUES(?,?)", (job, day))
        clip = db.uid()
        c.execute("INSERT INTO clips(id,video_id,job_id,title,plan,status,created) VALUES(?,?,?,?,?,'queued',?)",
            (clip, ident, job, body.title, json.dumps(plan), db.now()))
        db.event("Clip mit KI-Sprecher vorgemerkt" if body.voiceover else "Clip zum Rendern vorgemerkt", body.title, c)
    return {"clip_id": clip, "job_id": job}

@app.post("/api/jobs/{ident}/cancel")
def cancel(ident: str):
    with db.connection() as c:
        job = c.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
        if not job:
            raise HTTPException(404, "Auftrag nicht gefunden.")
        if job["status"] not in ("queued", "running"):
            raise HTTPException(409, "Dieser Auftrag ist bereits beendet.")
        c.execute("UPDATE jobs SET status='cancelled',stage='Abgebrochen',updated=? WHERE id=?", (db.now(), ident))
        c.execute("UPDATE clips SET status='cancelled' WHERE job_id=?", (ident,))
        db.event("Auftrag abgebrochen", "Bereits gesendete Gemini-Anfragen können noch Kosten verursachen.", c)
    return {"status": "cancelled"}

@app.get("/api/videos/{ident}/original")
def original(ident: str):
    video = require_video(ident)
    if not video["original"]:
        raise HTTPException(404, "Originaldatei benötigt.")
    return FileResponse(db.DATA / video["original"])

@app.get("/api/clips/{ident}/video")
def clip_file(ident: str, download: bool = False):
    clip = db.one("SELECT * FROM clips WHERE id=?", (ident,))
    if not clip or clip["status"] != "ready" or not clip["file"]:
        raise HTTPException(404, "Clip ist noch nicht bereit.")
    return FileResponse(db.DATA / clip["file"], media_type="video/mp4",
        filename="clipcontrol-" + ident[:8] + ".mp4" if download else None)

@app.get("/api/clips/{ident}/plan")
def clip_plan(ident: str):
    clip = db.one("SELECT * FROM clips WHERE id=?", (ident,))
    if not clip:
        raise HTTPException(404, "Clip nicht gefunden.")
    return db.decode(clip)["plan"]

@app.post("/api/accounts")
def add_account(body: Account):
    ident = db.uid()
    with db.connection() as c:
        c.execute("INSERT INTO accounts(id,platform,name,external_id) VALUES(?,?,?,?)", (ident, body.platform, body.name, body.external_id))
        db.event("Zielaccount als Vorbereitung gespeichert", body.name + " · OAuth noch nicht verbunden", c)
    return {"id": ident, "status": "setup_required"}

@app.post("/api/accounts/{ident}/pause")
def pause_account(ident: str):
    with db.connection() as c:
        if not c.execute("SELECT 1 FROM accounts WHERE id=?", (ident,)).fetchone():
            raise HTTPException(404, "Account nicht gefunden.")
        c.execute("UPDATE accounts SET paused=1-paused WHERE id=?", (ident,))
    return {"ok": True}

@app.post("/api/schedules")
def schedule(body: Schedule):
    try:
        at = to_utc(body.local_time, body.timezone)
    except (ValueError, ZoneInfoNotFoundError) as e:
        raise HTTPException(422, str(e))
    if at <= db.now():
        raise HTTPException(422, "Der Termin muss in der Zukunft liegen.")
    with db.connection() as c:
        clip = c.execute("SELECT status FROM clips WHERE id=?", (body.clip_id,)).fetchone()
        account = c.execute("SELECT id FROM accounts WHERE id=?", (body.account_id,)).fetchone()
        if not clip or clip[0] != "ready" or not account:
            raise HTTPException(422, "Bitte einen fertigen Clip und einen gespeicherten Zielaccount auswählen.")
        ident = db.uid()
        try:
            c.execute("INSERT INTO schedules(id,clip_id,account_id,scheduled_at,timezone) VALUES(?,?,?,?,?)", (ident, body.clip_id, body.account_id, at, body.timezone))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Dieser Account hat zu dieser Uhrzeit bereits einen Termin.")
        db.event("Termin als Entwurf gespeichert", "Veröffentlichung blockiert: Plattformanbindung noch nicht implementiert.", c)
    return {"id": ident, "status": "blocked"}

@app.delete("/api/schedules/{ident}")
def remove_schedule(ident: str):
    with db.connection() as c:
        c.execute("DELETE FROM schedules WHERE id=?", (ident,))
        db.event("Terminentwurf entfernt", ident, c)
    return {"ok": True}

static = Path(os.getenv("CLIPCONTROL_STATIC", "frontend/out"))
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="ui")
