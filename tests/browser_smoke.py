"""Real Chromium desktop/mobile smoke test, including playback of real FFmpeg output."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import httpx

BASE="http://127.0.0.1:8000"
out=Path("test-results")
out.mkdir(exist_ok=True)
with httpx.Client(base_url=BASE,headers={"X-ClipControl":"1"},timeout=60) as c:
    for _ in range(90):
        try:
            if c.get("/api/health").status_code == 200: break
        except httpx.HTTPError: pass
        time.sleep(1)
    else: raise AssertionError("Server not ready")
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100})
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(BASE)
        page.get_by_role("heading",name="Dein nächster guter Clip.").wait_for()
        page.get_by_text("Gemini wartet auf deinen API-Schlüssel").wait_for()
        page.screenshot(path=str(out/"studio-desktop-empty.png"),full_page=True)
        page.get_by_role("button",name="Technisches Testvideo erzeugen").click()
        for _ in range(120):
            state=c.get("/api/state").json()
            if state["videos"] and state["videos"][0]["has_original"]: break
            time.sleep(1)
        else: raise AssertionError(state)
        ident=state["videos"][0]["id"]
        page.get_by_label("Beginn (Sekunden)").fill("1")
        page.get_by_label("Ende (Sekunden)").fill("4")
        page.get_by_label("Clip-Titel",exact=True).fill("Browser-Testclip")
        page.get_by_role("button",name="Clip erstellen",exact=True).click()
        for _ in range(180):
            state=c.get("/api/state").json()
            if state["clips"] and state["clips"][0]["status"] == "ready": break
            if state["clips"] and state["clips"][0]["status"] == "failed": raise AssertionError(state["jobs"])
            time.sleep(1)
        else: raise AssertionError(state)
        video=page.get_by_label("Fertiger Clip",exact=True)
        video.wait_for(timeout=20000)
        video.evaluate("(v) => { v.muted=true; return v.play(); }")
        page.wait_for_timeout(1500)
        assert video.evaluate("(v) => v.currentTime > 0 && v.videoWidth === 1080 && v.videoHeight === 1920")
        video.evaluate("(v) => v.pause()")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(out/"studio-desktop-rendered.png"),full_page=True)
        page.get_by_role("button",name="Zielaccounts",exact=True).click()
        page.get_by_label("Account-Name",exact=True).fill("QA-Account")
        page.get_by_label("Kanal- oder Account-Kennung").fill("qa-only")
        page.get_by_role("button",name="Account speichern",exact=True).click()
        page.get_by_role("heading",name="QA-Account").wait_for()
        page.get_by_role("button",name="Einstellungen",exact=True).click()
        page.get_by_label("Maximal neue Gemini-Aufträge pro Tag").fill("3")
        page.get_by_role("button",name="Limit speichern",exact=True).click()
        page.get_by_text("Tageslimit gespeichert.",exact=True).wait_for()
        page.get_by_role("button",name="Studio",exact=True).click()
        page.set_viewport_size({"width":390,"height":844})
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(out/"studio-mobile.png"),full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
        page.get_by_role("button",name="Video hinzufügen",exact=True).click()
        page.get_by_label("Titel",exact=True).fill("Mobile Eingabe")
        page.get_by_role("button",name="Video anlegen",exact=True).click()
        page.get_by_role("dialog").wait_for(state="hidden")
        assert any(v["title"]=="Mobile Eingabe" for v in c.get("/api/state").json()["videos"])
        assert not errors,errors
        browser.close()
    # Keep the actual sample export with the CI artifacts for review.
    clip=next(x for x in state["clips"] if x["status"]=="ready")
    (out/"verified-clip.mp4").write_bytes(c.get(clip["url"]).content)
    (out/"verified-plan.json").write_text(json.dumps(clip["plan"],indent=2))
