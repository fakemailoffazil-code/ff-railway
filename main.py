from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright
import urllib.parse
import asyncio
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (frontend)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


class TokenRequest(BaseModel):
    token_input: str


def extract_eat(raw: str) -> tuple[str, dict]:
    """EAT token aur URL params extract karo."""
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


async def get_token_via_browser(eat: str, url_params: dict) -> dict:
    """Playwright se kiosgamer browser session simulate karo."""
    kiosgamer_url = (
        f"https://discstore.kiosgamer.co.id/"
        f"?eat={urllib.parse.quote(eat)}"
        f"&lang={url_params.get('lang', 'en')}"
        f"&region={url_params.get('region', 'IND')}"
        f"&account_id={url_params.get('account_id', '')}"
        f"&nickname={urllib.parse.quote(url_params.get('nickname', ''))}"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        result = {}

        # Network response intercept karo
        async def handle_response(response):
            if "callback_redirect" in response.url or "oauth" in response.url:
                try:
                    body = await response.text()
                    import json
                    data = json.loads(body)
                    if "access_token" in data or "token" in data:
                        result.update(data)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # Pehle main page load karo — session/cookies set hote hain
            await page.goto("https://discstore.kiosgamer.co.id/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)

            # Ab EAT URL navigate karo
            await page.goto(kiosgamer_url, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(2)

            # Page URL check karo — redirect hua kya
            current_url = page.url
            if "access_token" in current_url:
                parsed = urllib.parse.urlparse(current_url)
                params = urllib.parse.parse_qs(parsed.query)
                result = {k: v[0] for k, v in params.items()}

            # Page content se bhi try karo
            if not result.get("access_token"):
                content = await page.content()
                import json
                json_match = re.search(r'\{[^{}]*"access_token"[^{}]*\}', content)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except Exception:
                        pass

        except Exception as e:
            result["browser_error"] = str(e)
        finally:
            await browser.close()

        # Fallback: URL params se jo mila woh return karo
        if not result.get("access_token"):
            result.update({
                "account_id": url_params.get("account_id", ""),
                "nickname": url_params.get("nickname", ""),
                "region": url_params.get("region", ""),
                "access_token": "",
                "error": "Could not extract access_token from kiosgamer"
            })

        return result


@app.get("/", response_class=HTMLResponse)
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return HTMLResponse("<h1>FF Token API</h1><p>POST /api/convert with {token_input}</p>")


@app.post("/api/convert")
async def convert_token(req: TokenRequest):
    if not req.token_input or len(req.token_input) < 10:
        raise HTTPException(status_code=400, detail="Invalid token_input")

    eat, url_params = extract_eat(req.token_input)

    if len(eat) < 10:
        raise HTTPException(status_code=400, detail="Could not extract EAT token")

    result = await get_token_via_browser(eat, url_params)

    if result.get("access_token"):
        return {
            "status": "success",
            "access_token": result.get("access_token", ""),
            "account_id": result.get("account_id", url_params.get("account_id", "")),
            "nickname": result.get("nickname", url_params.get("nickname", "")),
            "region": result.get("region", url_params.get("region", "")),
        }
    else:
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "Failed to get access token")
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
