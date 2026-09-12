# Anbieteradapter und offizielle Quellen

Recherchestand: 12. September 2026. Verfügbarkeit bleibt von Region, Projekt, Modell und Plattformfreigaben abhängig.

## Gemini – implementiert, Live-Test benötigt Schlüssel
Offizielles Python-SDK google-genai, Client.models.generate_content mit JSON-Schema.
YouTube wird als types.Part(file_data=types.FileData(file_uri=canonical_url)) gesendet.
Originaldateien werden über client.files.upload übertragen, bis ACTIVE geprüft und nach der Analyse über client.files.delete entfernt.
Modell konfigurierbar via GEMINI_MODEL; gemini-3.8-flash entspricht dem zum Recherchezeitpunkt gezeigten Dokumentationsbeispiel.
Die YouTube-URL-Funktion ist Preview, öffentliche Videos sind Voraussetzung. Ein API-Zugriff liefert keine Originaldatei zum Rendern.
- https://ai.google.dev/gemini-api/docs/generate-content/video-understanding
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/files

Zeitstempel von Gemini sind Schätzungen, keine garantierte Wortausrichtung. Lange Transkripte können Ausgabelimits überschreiten; ein ungültiges/abgeschnittenes Ergebnis wird abgelehnt und als Fehler dargestellt.
Gemini-Timeouts werden nicht automatisch erneut kostenpflichtig abgesendet. Nutzung zeigt die vom Anbieter gelieferten Prompt-/Antworttokens; Denktokens und Rechnungsbeträge fehlen.
Der Adapter wurde für diesen Auftrag mit isolierten Antworten vorbereitet. Ohne Betreiber-Schlüssel gibt es keinen behaupteten Live-Erfolg.

## YouTube – Veröffentlichung noch nicht implementiert
Geplanter Weg: offizielles OAuth, videos.insert, Verarbeitungskontrolle und Statusabgleich.
Vor Umsetzung aktuellen Auditstatus, Scope und Beschränkungen unbestätigter API-Projekte prüfen.
- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/youtube/terms/developer-policies

## Instagram – Veröffentlichung noch nicht implementiert
Professionellen Account und passenden Login-/Berechtigungsweg prüfen; Container erstellen, Verarbeitung abwarten, veröffentlichen, Status abgleichen.
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api

## TikTok – Veröffentlichung noch nicht implementiert
Keine pauschale Direct-Post-Zusage für interne Uploadwerkzeuge. Vor Umsetzung Anwendungsfall gegen aktuelle Richtlinien prüfen; bis dahin MP4-Export.
- https://developers.tiktok.com/doc/content-sharing-guidelines/

## Browserbetrieb
Codespaces-Port 8000 privat, Next.js Static Export von FastAPI unter derselben Origin bedient.
- https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
- https://nextjs.org/docs/app/guides/single-page-applications
