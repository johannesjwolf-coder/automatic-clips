"""Checks the actual deployable Docker image, not only the runner environment."""
import time
import httpx
with httpx.Client(base_url="http://127.0.0.1:8001",headers={"X-ClipControl":"1"},timeout=15) as c:
    for _ in range(60):
        try:
            if c.get("/api/health").status_code==200: break
        except httpx.HTTPError: pass
        time.sleep(1)
    else: raise AssertionError("Docker API did not start")
    assert "ClipControl" in c.get("/").text
    result=c.post("/api/demo")
    assert result.status_code==200,result.text
    ident=result.json()["id"]
    for _ in range(60):
        s=c.get("/api/state").json()
        if s["videos"][0]["has_original"]: break
        time.sleep(1)
    else: raise AssertionError(s["jobs"])
    result=c.post(f"/api/videos/{ident}/render",json={"title":"Container smoke","start":1,"end":3,"subtitles":False})
    assert result.status_code==200,result.text
    for _ in range(120):
        s=c.get("/api/state").json()
        clip=s["clips"][0]
        if clip["status"]=="ready": break
        if clip["status"]=="failed": raise AssertionError(s["jobs"])
        time.sleep(1)
    else: raise AssertionError(s["jobs"])
    assert c.get(clip["url"]).headers["content-type"]=="video/mp4"
    print("Docker runtime: UI, worker, source creation, FFmpeg export and media endpoint passed.")
