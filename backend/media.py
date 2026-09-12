import json
import os
import re
import subprocess
import time
from pathlib import Path
from . import db

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")

class Cancelled(Exception):
    pass

def run(args, job_id=None, timeout=1800):
    # No shell; untrusted text is never interpolated into commands.
    with __import__("tempfile").TemporaryFile() as log:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        started = time.monotonic()
        try:
            while p.poll() is None:
                if time.monotonic() - started > timeout:
                    raise RuntimeError("Verarbeitung hat das Zeitlimit überschritten.")
                if job_id:
                    job = db.one("SELECT status FROM jobs WHERE id=?", (job_id,))
                    if not job or job["status"] == "cancelled":
                        raise Cancelled()
                time.sleep(0.25)
            if p.returncode:
                # Raw paths/input metadata may be sensitive: don't expose ffmpeg logs.
                raise RuntimeError("FFmpeg konnte die Datei nicht verarbeiten. Bitte Format und Datei prüfen.")
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()

def probe(path):
    result = subprocess.run([FFPROBE, "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, timeout=60, check=True)
    raw = json.loads(result.stdout)
    video = next((s for s in raw["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("Die Datei enthält keine Videospur.")
    duration = float(raw["format"].get("duration", video.get("duration", 0)))
    if not 0 < duration <= 14400 or not 0 < video["width"] <= 8192 or not 0 < video["height"] <= 8192:
        raise ValueError("Unterstützt: Videos bis 4 Stunden und 8192 Pixel Kantenlänge.")
    return {"duration": duration, "width": video["width"], "height": video["height"],
        "audio": any(s["codec_type"] == "audio" for s in raw["streams"]),
        "codec": video.get("codec_name"), "bytes": Path(path).stat().st_size}

def ass_time(seconds):
    n = max(0, round(seconds * 100))
    return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"

def subtitles(path, words, start, end, size):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size},&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,4,1,2,100,170,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chosen = [w for w in words if w["end"] > start and w["start"] < end]
    for i in range(0, len(chosen), 5):
        group = chosen[i:i+5]
        # Remove ASS control syntax, preserving ordinary spoken text.
        text = " ".join(re.sub(r"[{}\\\r\n]", "", w["text"]) for w in group)
        a, b = max(start, group[0]["start"])-start, min(end, group[-1]["end"])-start
        if b > a:
            lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{text}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

def render(video, clip, job_id):
    plan = clip["plan"]
    src = db.DATA / video["original"]
    meta = probe(src)
    if plan["end"] > meta["duration"] + 0.05:
        raise ValueError("Der Ausschnitt liegt ausserhalb der Originaldatei.")
    work = db.DATA / "work" / clip["id"]
    work.mkdir(parents=True, exist_ok=True)
    # All filter paths are generated hex IDs, never user paths.
    if plan["layout"] == "crop":
        filt = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    else:
        filt = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x101315,setsar=1"
    if plan.get("words") and plan["subtitles"]:
        sub = work / "captions.ass"
        subtitles(sub, plan["words"], plan["start"], plan["end"], plan["font_size"])
        # Linux Codespace/server path. Avoid drive-letter escaping issues.
        filt += ",ass=" + sub.as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    output = db.DATA / "clips" / (clip["id"] + ".mp4")
    temp = work / "output.mp4"
    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-protocol_whitelist", "file,pipe", "-ss", str(plan["start"]), "-i", str(src),
        "-t", str(plan["end"]-plan["start"]), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", filt, "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-movflags", "+faststart", str(temp)]
    run(args, job_id)
    check = probe(temp)
    if check["width"] != 1080 or check["height"] != 1920 or abs(check["duration"] - (plan["end"]-plan["start"])) > 0.3:
        raise ValueError("Der Export hat die technische Prüfung nicht bestanden.")
    if meta["audio"] and not check["audio"]:
        raise ValueError("Im Export fehlt die Audiospur.")
    run([FFMPEG, "-v", "error", "-i", str(temp), "-f", "null", "-"], job_id)
    temp.replace(output)
    return "clips/" + output.name, check

def demo(path):
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "testsrc2=size=640x360:rate=30:duration=12", "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=48000:duration=12",
        "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(path)], timeout=60)
