# ClipControl

Deutschsprachiges Browser-Studio: Video bereitstellen → mit Gemini analysieren → Highlight wählen → mit FFmpeg rendern → Clip abspielen.

## Ohne Installation auf deinem Rechner starten

[![In GitHub Codespaces öffnen](https://github.com/codespaces/badge.svg)](https://codespaces.new/johannesjwolf-coder/automatic-clips)

1. Codespace über den Button erstellen. GitHub baut die Umgebung automatisch; der erste Start dauert einige Minuten.
2. In **Ports** den Port **8000 · ClipControl** im Browser öffnen, falls er nicht automatisch öffnet. **Sichtbarkeit privat lassen.**
3. **Video hinzufügen**: öffentlichen YouTube-Link eintragen oder Video ohne Link anlegen und Originaldatei hochladen.
4. Für echte KI-Analyse ein Codespaces-Secret **GEMINI_API_KEY** für dieses Repository hinterlegen, dann den Codespace neu starten. In ClipControl unter **Einstellungen** ein Tageslimit grösser 0 speichern.
5. Gemini-Analysequelle wählen, Freigabe bestätigen, **Analysieren**. Highlight auswählen, Zeitcodes prüfen, **Clip erstellen**. Fertiges MP4 rechts abspielen oder herunterladen.

Ohne Gemini-Schlüssel: **Technisches Testvideo erzeugen**, Beginn 1 und Ende 4 Sekunden setzen und **Clip erstellen**. Das ist ein echtes FFmpeg-Testbild mit Testton, keine vorgetäuschte KI-Analyse.

Codespaces verbraucht ggf. GitHub-Rechenzeit/Storage. Es stoppt bei Inaktivität und ist kein 24/7-Hosting. Bei gestopptem Codespace arbeitet ClipControl nicht weiter. Auf deinem Rechner sind keine Entwicklungsprogramme nötig.

## Was tatsächlich implementiert ist

- Öffentliche YouTube-URLs direkt als Gemini-Videoeingabe (Preview-Funktion des Anbieters; nicht jedes Video/Modell/Projekt unterstützt sie).
- Gemini Files API für die Analyse hochgeladener Originaldateien, Verarbeitung abwarten, temporäre Anbieterdatei danach löschen.
- Strukturierte Highlights mit Originalzeitcodes, Begründung, Bild-/Audioereignissen und geschätzten Wortzeitcodes. Strenge Validierung der Modellantworten.
- Originaldateien separat hochladen und mit FFprobe prüfen. Ein Link ist **kein Downloadmechanismus**.
- Manuelle Auswahl und Änderung von Beginn/Ende; zusammenhängende Clips von 1–180 Sekunden.
- FFmpeg H.264/AAC, 1080×1920, 30 fps, vollständiges Bild mit Padding oder expliziter mittiger Zuschnitt, Lautheitsanpassung.
- Optionale eingebrannte Untertitel aus Gemini-Wortzeitcodes. Keine garantierte Forced-Alignment-Genauigkeit, kein automatisches Personentracking.
- Unveränderliche Exportversionen mit gespeicherten Schnittplänen, Wiedergabe mit Range-Requests und MP4-Download.
- SQLite-Migrationen, persistente Aufträge, genau ein Worker, Abbruch, globale Verarbeitungspause.
- Renderaufträge werden nach Worker-Neustart erneut aufgenommen. Unterbrochene Gemini-Anfragen werden wegen möglicher Kosten **nicht blind wiederholt**.
- Pro UTC-Tag begrenzte Zahl neu angeforderter KI-Jobs, atomare Reservierung; Eingabe-/Ausgabetokens soweit geliefert.
- Account-Datensätze und Terminentwürfe mit explizitem Zielaccount, UTC-Speicherung und Sommerzeitprüfung. Noch keine OAuth-Verbindung und keine Veröffentlichungen.
- GitHub Actions: Backendtests, echte Videoexports, Chromium-Bedienung auf Desktop und Mobile, Wiedergabeprüfung. Ergebnisbilder und Beispielclip liegen im Workflow-Artefakt.

## Echte Einschränkungen dieser ersten Version

**Kein vollständiger Automationsdienst:** Kanalüberwachung, Cloudspeicher-Eingang, Chatsteuerung, aktive Regeln, automatisches Personentracking, Pausenkürzungen, Plattform-OAuth und Uploads sind nächste Ausbaustufen. Die Oberfläche kennzeichnet vorbereitete Termine als blockiert. Ein gespeicherter Account ist keine Verbindung.

**Kein Live-KI-Test ohne Schlüssel:** Tests verwenden ausdrücklich isolierte Gemini-Antworten. Der Produktionsadapter führt echte API-Aufrufe durch, wird aber erst nach deiner Einrichtung live geprüft.

**Zugriff:** Für private GitHub-Codespaces-Portweiterleitung. Noch keine eigene Betreiberanmeldung. Nicht öffentlich freigeben. Originaldateien und API haben innerhalb des Ports dieselbe Zugriffsgrenze. Docker veröffentlicht standardmässig nur an 127.0.0.1.

**Kosten:** Das Auftragslimit ist keine Euro-/Franken-Budgetgarantie. Abgebrochene oder fehlgeschlagene API-Anfragen können kostenpflichtig sein. Zusätzliches Denktoken-/Kostenreporting und Geldbudget-Steuerung fehlen. Google-Projektkosten separat prüfen.

**Medien:** MP4 empfohlen; andere zulässige Eingabecontainer werden von FFmpeg verarbeitet, sind aber nicht in jedem Browser als Original abspielbar. Export immer MP4. Bei YouTube-Analyse muss die bereitgestellte Originaldatei dieselbe Zeitachse haben; eine automatische Identitätsprüfung gibt es noch nicht. Wortzeitcodes vor Verwendung prüfen.

## Weitere Dokumentation

- [Architektur, Entscheidungen und Fortschritt](docs/ARCHITECTURE.md)
- [Betrieb, Einrichtung und nächster Schritt zu 24/7](docs/OPERATIONS.md)
- [Offizielle API-Quellen](docs/INTEGRATIONS.md)
- [Automatische Prüfungen](../../actions)

## Serverstart (später, auf einem Linux-Server)

```sh
docker compose up --build -d
```

Docker Compose liefert diese erste Version mit SQLite und lokalem persistentem Volume. Ein Serverbetrieb für mehrere Worker benötigt weitere Infrastruktur; siehe Betriebsanleitung. Es werden keine Zugangsdaten und keine Nutzervideos in Git gespeichert.
