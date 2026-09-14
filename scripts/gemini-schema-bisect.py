"""Findet heraus, welche Schema-Schlüsselwörter Gemini ablehnt. Im Container ausführen:
    cd /opt/automatic-clips && docker compose exec -T clipcontrol python - < scripts/gemini-schema-bisect.py
Nur kurze Textanfragen, keine Videos."""
import copy
import json
import os
from google import genai
from google.genai import types
from backend import gemini
from backend.models import Analysis

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
PROMPT = "Es gibt kein Video. Liefere highlights leer und skip_reason 'Test'."

def without(schema, keys):
    def clean(node):
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in keys}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node
    return clean(copy.deepcopy(schema))

def attempt(label, schema):
    try:
        text = client.models.generate_content(model=gemini.MODEL, contents=PROMPT,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema)).text
        print(f"OK    {label} -> {text.strip()[:50]!r}")
        return True
    except Exception as e:
        detail = " ".join(str(getattr(e, "message", None) or e).split())[:200]
        print(f"FEHLT {label}: {detail}")
        return False

base = gemini._schema(Analysis)
print("Schema-Grösse:", len(json.dumps(base)), "Zeichen")
attempt("Aktuelles App-Schema", base)
for keys in (("additionalProperties",), ("title",), ("maxItems",), ("minimum", "maximum"), ("default",), ("description",)):
    attempt("ohne " + "+".join(keys), without(base, keys))
attempt("ohne alle genannten", without(base, ("additionalProperties", "title", "maxItems", "minimum", "maximum", "default", "description")))
# Schrittweise Tiefe: nur Analysis ohne highlights-Details
flat = copy.deepcopy(base)
flat["properties"]["highlights"] = {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}
attempt("Highlights auf ein Feld reduziert", flat)
# Eigenes Schema von Hand, Struktur wie die App, ohne Pydantic-Extras
hand = {"type": "object", "properties": {
    "summary": {"type": "string"}, "language": {"type": "string"}, "skip_reason": {"type": "string"},
    "highlights": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"}, "score": {"type": "integer"},
        "reason": {"type": "string"}, "visual": {"type": "string"}, "transcript": {"type": "string"},
        "words": {"type": "array", "items": {"type": "object", "properties": {"start": {"type": "number"}, "end": {"type": "number"}, "text": {"type": "string"}},
            "required": ["start", "end", "text"]}}},
        "required": ["title", "start", "end", "score", "reason", "visual", "transcript", "words"]}}},
    "required": ["summary", "language", "skip_reason", "highlights"]}
attempt("Handgeschriebenes Schema (gleiche Struktur)", hand)
client.close()
