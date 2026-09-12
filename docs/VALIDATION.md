# Validierung

Erster vollständiger GitHub-Actions-Lauf erfolgreich: https://github.com/johannesjwolf-coder/automatic-clips/actions/runs/34702463477

- Next.js 16.3.5 Produktionsbuild und TypeScript-Prüfung erfolgreich.
- 7 pytest-Fälle erfolgreich, inklusive echter FFmpeg-Exports, Untertitel, 9:16, Audioprüfung, HTTP-Range-Wiedergabe, Auftragslimit, Neustart und Sommerzeit.
- Chromium: tatsächlicher Studio-Ablauf mit Testvideo, Clip-Erstellung und erfolgreicher Videowiedergabe; Accountanlage und Einstellungen; 1440px Desktop und 390px Mobile ohne horizontales Überlaufen.
- Screenshots, getestetes MP4 und Schnittplan als Workflow-Artefakt (7 Tage Aufbewahrung).

Nicht live getestet: Gemini mit Betreiber-Schlüssel, Plattform-OAuth/Uploads (noch nicht implementiert), Start eines nutzereigenen Codespace. Diesen Codespace startet der Betreiber über den README-Button.
