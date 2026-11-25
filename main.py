from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import urllib.parse
import urllib.request
import json
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


class TokenRequest(BaseModel):
    token_input: str


def extract_eat(raw: str) -> tuple[str, dict]:
    raw = raw.strip()
    url_params = {}
    if "?" in raw:
        try:
            parsed = urllib.parse.urlparse(raw)
            params = urllib.parse.parse_qs(parsed.query)
            url_params = {k: v[0] for k, v in params.items()}
        except Exception:
            pass
    match = re.search(r'[?&]eat=([^&#\s]+)', raw)
    if match:
        eat = urllib.parse.unquote(match.group(1))
    else:
        eat = raw
    return eat, url_params


def call_token_api(eat_input: str) -> dict:
    payload = json.dumps({"token_input": eat_input}).encode()
    req = urllib.request.Request(
        "https://eat.freefire.site/api/convert",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://eat.freefire.site",
            "Referer": "https://eat.freefire.site/",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


@app.get("/", response_class=HTMLResponse)
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return HTMLResponse("<h1>FF Token API</h1>")


@app.post("/api/convert")
async def convert_token(req: TokenRequest):
    if not req.token_input or len(req.token_input) < 10:
        raise HTTPException(status_code=400, detail="Invalid token_input")

    eat, url_params = extract_eat(req.token_input)

    if len(eat) < 10:
        raise HTTPException(status_code=400, detail="Could not extract EAT token")

    try:
        result = call_token_api(eat)
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise HTTPException(status_code=502, detail=f"API error: {err}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if result.get("access_token"):
        return {
            "status": "success",
            "access_token": result.get("access_token", ""),
            "account_id": result.get("account_id", url_params.get("account_id", "")),
            "nickname": result.get("nickname", url_params.get("nickname", "")),
            "region": result.get("region", url_params.get("region", "")),
        }
    else:
        raise HTTPException(status_code=502, detail=result.get("error", "Failed"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
