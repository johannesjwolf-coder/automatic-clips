"""Diagnose für die Gemini-Anbindung. Im Container ausführen:
    cd /opt/automatic-clips && docker compose exec -T clipcontrol python - < scripts/gemini-check.py
Prüft in kleinen Schritten, welcher Teil einer Anfrage von Google abgelehnt wird.
Gibt keine Schlüssel aus. Verbraucht wenige Tokens (eine Mini-Videodatei, 3 Sekunden)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from google import genai
from google.genai import types
from backend import gemini
from backend.models import Analysis

def step(name, fn):
    try:
        result = fn()
        print(f"OK    {name}" + (f" -> {result}" if result else ""))
        return True
    except Exception as e:
        detail = " ".join(str(getattr(e, "message", None) or e).split())[:400]
        print(f"FEHLT {name}: {type(e).__name__} {detail}")
        return False

if not gemini.available():
    sys.exit("GEMINI_API_KEY ist im Container nicht gesetzt.")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
print(f"Analyse-Modell: {gemini.MODEL}  Sprecher-Modell: {gemini.TTS_MODEL}  SDK: {genai.__version__}")

step("Modell vorhanden", lambda: client.models.get(model=gemini.MODEL).name)
step("Text ohne Schema", lambda: client.models.generate_content(model=gemini.MODEL, contents="Antworte nur mit OK.").text.strip()[:20])

simple = {"type": "object", "properties": {"antwort": {"type": "string"}}, "required": ["antwort"]}
step("Text mit einfachem JSON-Schema", lambda: client.models.generate_content(model=gemini.MODEL, contents="Antworte mit {\"antwort\":\"OK\"}.",
    config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=simple)).text.strip()[:40])
step("Text mit Analyse-Schema (wie in der App)", lambda: client.models.generate_content(model=gemini.MODEL,
    contents="Es gibt kein Video. Liefere highlights leer und skip_reason 'Test'.",
    config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=gemini._schema(Analysis),
        temperature=0.2, max_output_tokens=16000)).text.strip()[:60])

with tempfile.TemporaryDirectory() as tmp:
    clip = Path(tmp) / "mini.mp4"
    subprocess.run([gemini.media.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)], check=True)
    uploaded = None
    def upload():
        global uploaded
        uploaded = client.files.upload(file=str(clip), config=types.UploadFileConfig(mime_type="video/mp4"))
        while uploaded.state and uploaded.state.name == "PROCESSING":
            import time; time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        return f"{uploaded.state.name if uploaded.state else '?'} {uploaded.mime_type}"
    if step("Mini-Video hochladen (Files API)", upload) and uploaded is not None:
        part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type)
        step("Video ohne Schema", lambda: client.models.generate_content(model=gemini.MODEL,
            contents=types.Content(parts=[part, types.Part(text="Beschreibe das Video in fünf Wörtern.")])).text.strip()[:60])
        step("Video mit Analyse-Schema (wie in der App)", lambda: client.models.generate_content(model=gemini.MODEL,
            contents=types.Content(parts=[part, types.Part(text="Liefere highlights leer und skip_reason 'Test'.")]),
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=gemini._schema(Analysis),
                temperature=0.2, max_output_tokens=16000)).text.strip()[:60])
        step("Video-Ausschnitt (video_metadata) ohne Schema", lambda: client.models.generate_content(model=gemini.MODEL,
            contents=types.Content(parts=[types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type),
                video_metadata=types.VideoMetadata(start_offset="0.500s", end_offset="2.000s")), types.Part(text="Beschreibe das Video in fünf Wörtern.")])).text.strip()[:60])
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

step("Sprecher-Modell: kurzer Satz", lambda: str(len(gemini._speak(client, "Kore", "ruhig", "Hallo, das ist ein Test.", {"input_tokens": 0, "output_tokens": 0}))) + " Bytes PCM")
client.close()
