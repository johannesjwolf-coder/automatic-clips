# ClipControl im Browser und später dauerhaft betreiben

## Jetzt: GitHub Codespaces
1. Repository in GitHub öffnen, **Code → Codespaces → Create codespace on main**.
2. Einrichtung läuft automatisch. In **Ports** Port **8000** öffnen. Die Vorschau muss **Private** bleiben.
3. Backend und Worker starten bei jedem Codespace-Start automatisch.
4. Gemini-Key in GitHub **Settings → Codespaces → Secrets → New secret**, Name GEMINI_API_KEY, dieses Repository freigeben. Codespace danach Stop/Start; bestehende Prozesse sehen nachträgliche Änderungen nicht.
5. Optional GEMINI_MODEL als Secret setzen. Aktueller Standard steht in .env.example und wird in der Oberfläche angezeigt.
6. Unter Einstellungen ein Tages-Auftragslimit setzen. Standard 0 sperrt kostenpflichtige Analysen.

Codespace-Daten liegen in data/ innerhalb des Cloud-Workspace. Sie überleben Stop/Start, jedoch keine Löschung des Codespace. Nie einen Codespace mit ungesicherten Originalen löschen. Codespaces ist kein Backup und stoppt bei Inaktivität.

Die KI-Analyse übermittelt das gewählte Video/den YouTube-Link an Google. Keine Schlüssel in den Chat, Quellcode oder Screenshots schreiben. Die Oberfläche nimmt keine Schlüssel entgegen und gibt keine geheimen Werte zurück.

## Ablauf ohne KI-Schlüssel prüfen
Technisches Testvideo erzeugen → Zeitbereich 1 bis 4 Sekunden → Untertitel aus → Clip erstellen. Das synthetische Ausgangsvideo und der echte MP4-Export sind explizit Testmaterial.
Eigenes Material: Video anlegen → Originaldatei hochladen → Beginn/Ende auswählen → rendern.

## Was für 24/7 noch fehlt
- Ein dauerhaft laufender Linux-Server, z. B. 4 vCPU, 8 GB RAM und ausreichend Video-Speicher als Ausgangspunkt; tatsächlichen Bedarf messen.
- Domain und HTTPS-Reverse-Proxy. Vor öffentlicher Erreichbarkeit eine Betreiberanmeldung mit serverseitiger Autorisierung implementieren oder einen geprüften vorgeschalteten Zugangsschutz einsetzen.
- Persistenter Datenspeicher ausserhalb kurzlebiger Container; externe verschlüsselte Backups mit Restore-Test.
- Für mehrere Worker PostgreSQL + zuverlässige Worker-Warteschlange, S3-Medien, signierte Vorschau-Links, Monitoring und Aufbewahrungsregeln implementieren.
- Für automatische Quellen und Veröffentlichungen: YouTube/Meta Entwicklerprojekte, OAuth-Clientdaten, Callback-Domain, nötige Freigaben. TikTok-Eignung vor einer Integration prüfen.
- Chat/Automationsregeln, Quelleingang, Planungsausführung, Rechteverwaltung, Geldbudgetgrenzen und robuste Publishing-Deduplizierung fehlen noch.
- Erst nach einem End-to-End-Livetest mit echten Accounts und konkreter Uploadbestätigung Veröffentlichungen als erfolgreich anzeigen.

Das vorhandene Dockerfile/Compose startet den getesteten ersten Ablauf, nicht automatisch den gesamten geplanten Automationsdienst.

## Serverstart, wenn ein Server bereitsteht
Repository auf dem Server auschecken, GEMINI_API_KEY als Server-Secret setzen und docker compose up --build -d starten.
Port 8000 ist absichtlich nur auf 127.0.0.1 des Servers veröffentlicht. Der authentifizierende HTTPS-Proxy leitet auf diesen Port weiter.
Keine öffentliche Portbindung als Ersatz für den fehlenden Zugangsschutz verwenden.

## Automatisches Deployment (Server holt sich Updates von GitHub)
Auf dem Server läuft ein systemd-Timer (`clipcontrol-autodeploy.timer`), der alle 2 Minuten `scripts/auto-deploy-check.sh` ausführt. Das Skript vergleicht den laufenden Stand mit `origin/main`. Gibt es einen neuen Commit und ist dessen GitHub-Check `verify` erfolgreich, wird `scripts/deploy-server.sh` gestartet (git reset auf `origin/main`, `docker compose up -d --build`, Healthcheck). Fehlgeschlagene Commits werden nicht deployt. Es sind keine Zugangsdaten nötig, da Repository und Check-Status öffentlich lesbar sind.

Einmalige Einrichtung auf dem Server (als root):
```bash
cd /opt/automatic-clips && git pull --ff-only && bash scripts/install-auto-deploy.sh
```

Nützliche Befehle auf dem Server:
- `journalctl -u clipcontrol-autodeploy -n 50` – Protokoll der letzten Prüfungen/Deployments
- `systemctl start clipcontrol-autodeploy.service` – sofort prüfen statt auf den Timer zu warten
- `bash scripts/deploy-server.sh` – manuelles Update ohne Test-Prüfung
- `systemctl disable --now clipcontrol-autodeploy.timer` – Auto-Deploy abschalten

Während des Neubaus ist die Anwendung kurz nicht erreichbar; das Datenvolume bleibt erhalten. Nach einem Push dauert es Tests (ca. 15 Min) plus bis zu 2 Minuten, bis die Änderung live ist.

## Backup und Wiederherstellung
Für diese Einzelserverversion zuerst Container mit docker compose stop stoppen. Dadurch können SQLite-Hauptdatei, WAL und Originale/Clips gemeinsam aus dem benannten Volume kopiert werden.
Das gesamte Volume als verschlüsseltes Archiv in einen externen Speicher sichern. Keine Videos in Git pushen.
Zum Wiederherstellen in ein leeres Volume kopieren, Besitz für UID 10001 setzen, dieselbe Anwendungsversion starten und Datenbestand/Beispielclip prüfen. Erst danach aktualisieren.
Ein automatischer Backupdienst und ein geprüfter Restore sind noch einzurichten.

## Updates und Fehler
- Vor Updates Volume sichern; neuen Stand über GitHub Actions prüfen und Image neu bauen.
- Migrationsdateien nach Verwendung nicht rückwirkend ändern; neue Migration anhängen.
- Workerfehler: Aktivität/Jobmeldung prüfen. Neue Analyse bewusst auslösen, weil der erste API-Aufruf bereits kostenpflichtig gewesen sein kann.
- Globalpause stoppt neue Verarbeitung; laufendes Rendern im Studio per Auftrag abbrechen.
- Der Status eines vorhandenen Schlüssels bedeutet nur „konfiguriert“, nicht „bei Google erfolgreich getestet“.
- Eine ursprüngliche Gemini-Analyse und eine spätere Originaldatei müssen dieselbe Zeitachse haben. Bei anderen Schnitten die Originaldatei selbst analysieren.

## Fehlgeschlagene Codespaces-Einrichtung
Wenn `.venv/bin/python` oder `npm` fehlen, wurde die vorgesehene Entwicklungsumgebung nicht vollständig erstellt. Ein Codespace kann in einer Wiederherstellungsumgebung (z. B. Alpine) geöffnet sein. In der Befehlspalette **Codespaces: Rebuild Container** ausführen und das Erstellungsprotokoll prüfen. Die neue Containerdefinition enthält Node/npm direkt, ohne externes Node-Feature. `bash scripts/start-codespace.sh` prüft fehlenden Build und Python-Umgebung vor dem Start. Die vorgesehene Basis ist Debian mit Python 3.12, Node 22 und FFmpeg.
