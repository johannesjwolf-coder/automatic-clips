import json
import time
from . import db, media, gemini

def recover():
    with db.connection() as c:
        # Never blindly repeat a possibly charged Gemini request after a crash.
        c.execute("UPDATE jobs SET status='failed', stage='Unterbrochen', error='Worker wurde während der Gemini-Anfrage neu gestartet. Ergebnis und Google-Nutzung prüfen; bei Bedarf manuell erneut analysieren.',updated=? WHERE status='running' AND (kind='analysis' OR (kind='render' AND payload LIKE '%\"voiceover\": true%'))", (db.now(),))
        c.execute("UPDATE clips SET status='failed' WHERE status='queued' AND job_id IN (SELECT id FROM jobs WHERE status='failed' AND stage='Unterbrochen')")
        c.execute("UPDATE jobs SET status='queued',stage='Wiederaufnahme nach Neustart',updated=? WHERE status='running' AND kind IN ('render','demo')", (db.now(),))

def claim():
    with db.connection() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT paused FROM settings WHERE id=1").fetchone()[0]:
            return None
        row = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:
            return None
        c.execute("UPDATE jobs SET status='running',stage='Verarbeitung gestartet',updated=? WHERE id=?", (db.now(), row["id"]))
        return db.decode(dict(row))

def process(job):
    ident = job["id"]
    video = db.decode(db.one("SELECT * FROM videos WHERE id=?", (job["video_id"],)))
    try:
        if job["kind"] == "analysis":
            stage = "Gemini analysiert Bild, Sprache und Ton"
        elif job["kind"] == "render" and job["payload"].get("voiceover"):
            stage = "Gemini schreibt und spricht den Text, FFmpeg rendert"
        elif job["kind"] == "render":
            stage = "FFmpeg rendert und prüft den Export"
        else:
            stage = "Testvideo wird erzeugt"
        with db.connection() as c:
            c.execute("UPDATE jobs SET stage=?,updated=? WHERE id=?", (stage, db.now(), ident))
        if job["kind"] == "analysis":
            result, usage = gemini.analyze(video, job["payload"], ident)
            with db.connection() as c:
                c.execute("UPDATE usage SET input_tokens=?,output_tokens=? WHERE job_id=?", (usage["input_tokens"], usage["output_tokens"], ident))
                if c.execute("SELECT status FROM jobs WHERE id=?", (ident,)).fetchone()[0] == "cancelled":
                    return
                c.execute("UPDATE videos SET analysis=? WHERE id=?", (json.dumps(result), video["id"]))
        elif job["kind"] == "render":
            clip = db.decode(db.one("SELECT * FROM clips WHERE job_id=?", (ident,)))
            voice = None
            if clip["plan"].get("voiceover"):
                work = db.DATA / "work" / clip["id"]
                work.mkdir(parents=True, exist_ok=True)
                voice = work / "voice.wav"
                lines, usage = gemini.narrate(video, clip["plan"], ident, voice)
                with db.connection() as c:
                    c.execute("UPDATE usage SET input_tokens=?,output_tokens=? WHERE job_id=?", (usage["input_tokens"], usage["output_tokens"], ident))
                clip["plan"]["narration"] = lines
                clip["plan"]["tts_model"] = gemini.TTS_MODEL
                if clip["plan"]["subtitles"]:
                    clip["plan"]["words"] = media.narration_words(lines, clip["plan"]["start"])
            file, meta = media.render(video, clip, ident, voice)
            with db.connection() as c:
                if c.execute("SELECT status FROM jobs WHERE id=?", (ident,)).fetchone()[0] == "cancelled":
                    return
                c.execute("UPDATE clips SET file=?,metadata=?,plan=?,status='ready' WHERE id=?", (file, json.dumps(meta), json.dumps(clip["plan"]), clip["id"]))
        else:
            path = db.DATA / "originals" / (video["id"] + ".mp4")
            media.demo(path)
            meta = media.probe(path)
            with db.connection() as c:
                c.execute("UPDATE videos SET original=?,metadata=? WHERE id=?", ("originals/" + path.name, json.dumps(meta), video["id"]))
        with db.connection() as c:
            c.execute("UPDATE jobs SET status='done',stage='Abgeschlossen',updated=? WHERE id=? AND status='running'", (db.now(), ident))
            db.event(stage + ": abgeschlossen", video["title"], c)
    except media.Cancelled:
        with db.connection() as c:
            c.execute("UPDATE jobs SET status='cancelled',stage='Abgebrochen',updated=? WHERE id=?", (db.now(), ident))
            c.execute("UPDATE clips SET status='cancelled' WHERE job_id=?", (ident,))
    except Exception as e:
        message = str(e) if isinstance(e, (ValueError, RuntimeError)) else "Verarbeitung fehlgeschlagen. Originaldatei und Serverkonfiguration prüfen."
        with db.connection() as c:
            c.execute("UPDATE jobs SET status='failed',stage='Fehlgeschlagen',error=?,updated=? WHERE id=? AND status!='cancelled'", (message[:1500], db.now(), ident))
            c.execute("UPDATE clips SET status='failed' WHERE job_id=? AND status!='cancelled'", (ident,))
            db.event("Verarbeitung fehlgeschlagen", message[:1500], c)

def main():
    import fcntl
    db.init()
    lock = (db.DATA / "worker.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Es läuft bereits ein ClipControl-Worker.")
    recover()
    while True:
        with db.connection() as c:
            c.execute("INSERT OR REPLACE INTO runtime(key,value) VALUES('worker_heartbeat',?)", (db.now(),))
        job = claim()
        if job:
            process(job)
        else:
            time.sleep(1)
if __name__ == "__main__":
    main()
