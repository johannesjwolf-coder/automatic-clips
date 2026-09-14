import math
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

def youtube_url(value: str):
    u = urlparse(value.strip())
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Bitte einen öffentlichen HTTPS-YouTube-Videolink verwenden.")
    host = (u.hostname or "").lower()
    if host == "youtu.be":
        video_id = u.path.strip("/")
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if u.path == "/watch":
            video_id = parse_qs(u.query).get("v", [""])[0]
        elif re.fullmatch(r"/(shorts|live)/[A-Za-z0-9_-]{11}", u.path):
            video_id = u.path.rsplit("/", 1)[1]
        else:
            video_id = ""
    else:
        video_id = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Der Link muss auf ein einzelnes YouTube-Video zeigen.")
    return "https://www.youtube.com/watch?v=" + video_id

class Word(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=80)
    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Ungültiger Wortzeitcode.")
        return self

class Highlight(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=3000)
    visual: str = Field(max_length=2000)
    transcript: str = Field(max_length=12000)
    words: list[Word] = Field(default_factory=list, max_length=700)
    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Das Ende muss nach dem Beginn liegen.")
        return self

class Analysis(StrictModel):
    summary: str = Field(max_length=4000)
    language: str = Field(max_length=80)
    skip_reason: str = Field(max_length=2000)
    highlights: list[Highlight] = Field(max_length=5)
    def checked(self, limit, duration=None):
        for h in self.highlights:
            if h.end - h.start > limit + 0.05:
                raise ValueError("Gemini hat das konfigurierte Clip-Limit überschritten.")
            if duration and h.end > duration + 0.1:
                raise ValueError("Gemini-Zeitcodes liegen ausserhalb der Originaldatei.")
            previous = h.start
            for w in h.words:
                if w.start < h.start or w.end > h.end + 0.05 or w.start < previous:
                    raise ValueError("Gemini hat unplausible Wortzeitcodes geliefert.")
                previous = w.start
        if not self.highlights and not self.skip_reason:
            raise ValueError("Gemini hat weder Highlights noch einen Grund geliefert.")
        return self

class NarrationLine(StrictModel):
    start: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=400)

class Narration(StrictModel):
    lines: list[NarrationLine] = Field(max_length=40)
    def checked(self, duration):
        if not self.lines:
            raise ValueError("Gemini hat keinen Sprechtext geliefert.")
        previous = 0.0
        for line in self.lines:
            if line.start < previous:
                raise ValueError("Gemini hat unplausible Sprechzeiten geliefert.")
            if line.start > duration:
                raise ValueError("Gemini hat Sprechzeiten ausserhalb des Clips geliefert.")
            previous = line.start
        return self

class VideoCreate(StrictModel):
    title: str = Field(default="Neues Video", min_length=1, max_length=180)
    youtube_url: str = Field(default="", max_length=500)
class AnalyzeRequest(StrictModel):
    max_seconds: int = Field(default=90, ge=5, le=180)
    source: Literal["youtube", "original"] = "youtube"
    consent: bool = False
class RenderRequest(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    layout: Literal["contain", "crop"] = "contain"
    subtitles: bool = True
    font_size: int = Field(default=58, ge=32, le=80)
    candidate: int | None = Field(default=None, ge=0, le=4)
    # KI-Sprecher: Gemini schreibt den Text (oder spricht den eigenen), Gemini-TTS vertont ihn.
    voiceover: bool = False
    voice: Literal["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Zephyr", "Orus"] = "Kore"
    voice_style: str = Field(default="", max_length=300)
    voice_text: str = Field(default="", max_length=1500)
    consent: bool = False
    @model_validator(mode="after")
    def limits(self):
        duration = self.end-self.start
        if not 1 <= duration <= 180:
            raise ValueError("Ein Clip muss 1 bis 180 Sekunden lang sein.")
        if self.voiceover and len(self.voice_text.split()) > duration * 3:
            raise ValueError(f"Der eigene Sprechtext ist zu lang für {duration:.0f} Sekunden (höchstens etwa {int(duration*3)} Wörter).")
        return self
class Settings(StrictModel):
    paused: bool
    daily_limit: int = Field(ge=0, le=100)
class Account(StrictModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    name: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=150)
class Schedule(StrictModel):
    clip_id: str
    account_id: str
    local_time: str
    timezone: str = "Europe/Zurich"
def to_utc(local_time, zone):
    tz = ZoneInfo(zone)
    naive = datetime.fromisoformat(local_time)
    if naive.tzinfo is not None:
        raise ValueError("Bitte eine lokale Uhrzeit ohne Offset angeben.")
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    back = first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    if back != naive:
        raise ValueError("Diese Uhrzeit existiert wegen der Sommerzeitumstellung nicht.")
    if first.utcoffset() != second.utcoffset():
        raise ValueError("Diese Uhrzeit ist wegen der Zeitumstellung doppeldeutig. Bitte eine andere Uhrzeit wählen.")
    return first.astimezone(timezone.utc).isoformat()
