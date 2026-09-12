# Architektur und Projektstand

## Priorität und Umfang
Die letzte Nutzeranweisung gilt: alles in GitHub, nichts auf dem persönlichen Rechner installieren. Browsererprobung über GitHub Codespaces. Erste Lieferung: Analyse → Auswahl → Rendering → Wiedergabe. Accounts und Termine nur vorbereiten; dauerhafte Veröffentlichung noch nicht implementieren.

## Komponenten
- Next.js 16 / React 19 / TypeScript, statischer UI-Export. FastAPI bedient UI, API und Medien auf Port 8000. Dadurch ein einziger privater Codespaces-Port.
- Python 3.12, FastAPI/Pydantic, offizielles google-genai SDK, FFmpeg/FFprobe.
- SQLite WAL statt PostgreSQL für diese Einzelbetreiber-Testumgebung. Versionierte SQL-Migrationen; Daten bleiben ausserhalb Git.
- Persistente SQLite-Warteschlange statt Redis/Celery für exakt einen Worker. Atomare Beanspruchung; OS-Prozesssperre verhindert parallele Worker. Supervisor beendet die API, falls ein Dienst ausfällt; Compose startet den Container neu.
- Lokales Cloud-Volume im Codespace statt S3 für den ersten Ablauf. Browser des Betreibers ist nicht der Verarbeitungsrechner.
- Eigenes CSS statt Tailwind: kleine, bewusst gestaltete Oberfläche ohne zusätzliche Buildabhängigkeit.

## Datenfluss
1. Video-Datensatz mit optionaler kanonischer YouTube-URL anlegen.
2. Original mit zufälligem Namen speichern, technische Metadaten prüfen und eindeutig anhand Video-ID zuordnen.
3. Analyseaufruf nur mit expliziter Materialfreigabe, Schlüssel und freiem Tageskontingent. Kontingent und Job werden gemeinsam gespeichert.
4. Worker sendet YouTube-file_uri oder Files-API-Datei an Gemini. Kein YouTube-Download. Schema und Zeitcodes validieren; Kandidaten und Nutzung speichern.
5. Auswahl erstellt eine neue Clip-Version mit absoluter Originalzeit, Layout, Untertiteln und Herkunft der Auswahl.
6. FFmpeg arbeitet ohne Shell. Untertiteltext wird von ASS-Steuerzeichen bereinigt. Export wird technisch geprüft und vollständig dekodiert. Erst dann Status bereit.
7. Range-fähige Wiedergabe/Download. Account-/Terminentwürfe haben keine Veröffentlichungskomponente.

## Zustandslogik
Jobs: queued → running → done | failed | cancelled.
Bei Neustart: laufende Renderjobs → queued; laufende Analysejobs → failed mit konkretem Hinweis (möglicherweise kostenpflichtige Anfrage bereits erfolgt).
Globalpause verhindert Claims und neue Analyse-/Renderaufträge; laufende Aufträge gesondert abbrechen. Das UI verspricht keine Rücknahme bereits gesendeter Gemini-Anfragen.
Clips: queued → ready | failed | cancelled. Schnittpläne und fertige Versionen werden nicht überschrieben.
Termine: blocked. Alle sind Entwürfe, weil kein Publishingadapter vorhanden ist.

## Tests
pytest prüft URL-Validierung, Zeitumstellung, CSRF-Header, fehlenden Schlüssel, Auftragslimit, Pause, Neustart, Dateiprüfung, echte FFmpeg-Exports (Padding und Crop+Untertitel), Range-Wiedergabe, Accountzuordnung und doppelte Terminslots.
Chromium prüft echten UI-Testvideo-Ablauf, Abspielbarkeit, Accounts, Einstellungen sowie 1440px/390px ohne horizontales Überlaufen.
Gemini wird in isolierten Vertragstests simuliert; nicht als live getestet bezeichnen.
Abhängigkeiten innerhalb unterstützter Major-Versionen; das beim CI-Build tatsächlich aufgelöste npm-Lockfile liegt im CI-Artefakt. Produktions-Releases müssen exakte Versionen/Container-Digests festschreiben.

## Nächste Arbeit
1. Echte Gemini-Aufrufe mit Betreiber-Schlüssel prüfen, Referenzvideo und Kosten messen.
2. Forced Alignment, bessere Transkription bei langen Videos, Personenverfolgung, Dublettenbewertung.
3. PostgreSQL, Alembic-Migration, S3, Celery/Redis, begrenzte Retries mit Backoff/Leases; Reconciliation für externe Schreibaktionen.
4. Betreiberlogin, private signierte Medien-URLs, Tokenverschlüsselung und Secretsverwaltung.
5. Rechteverwaltung, offizieller YouTube-Quellenadapter und S3-Manifeste nach Video-ID.
6. Regeln/Chat über dieselben validierten Dienste; aktiver Scheduler mit IANA-Zeitzonen.
7. Plattformadapter und Zulassungen prüfen, testen, dann aktivieren. Veröffentlichungsschlüssel pro Regel/Slot/Account unabhängig von Clip-Version.
8. Backups, Restore-Drill, Aufbewahrung, Monitoring, echtes Geldbudget.

Offene Punkte sind bewusst keine als fertig ausgegebenen Platzhalter.
