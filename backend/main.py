import hashlib, hmac, ipaddress, os, secrets, socket, sqlite3, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import AnyHttpUrl, BaseModel, Field

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
DB = os.getenv("DB_PATH", "app.db")
PREVIEWS = Path(__file__).parent / "previews"
PREVIEWS.mkdir(exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

app = FastAPI(title="URL Preview API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/previews", StaticFiles(directory=PREVIEWS), name="previews")
bearer = HTTPBearer()

def q(sql, args=()):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.fetchall(), cur.lastrowid
    finally:
        c.close()


q("""create table if not exists users(
     id integer primary key, email text unique not null, password text not null)""")
q("""create table if not exists previews(
     id integer primary key, user_id integer not null, url text not null,
     title text, image text, created_at text not null)""")



class Credentials(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=128)


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def verify_pw(pw, stored):
    salt, _ = stored.split("$")
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def make_token(uid):
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    return jwt.encode({"sub": str(uid), "exp": exp}, SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    try:
        return int(jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "Session expired. Please log in again.")


@app.post("/api/signup", status_code=201)
def signup(body: Credentials):
    email = body.email.lower()
    try:
        _, uid = q("insert into users(email, password) values(?, ?)", (email, hash_pw(body.password)))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists.")
    return {"token": make_token(uid), "email": email}


@app.post("/api/login")
def login(body: Credentials):
    email = body.email.lower()
    rows, _ = q("select * from users where email = ?", (email,))
    if not rows or not verify_pw(body.password, rows[0]["password"]):
        raise HTTPException(401, "Incorrect email or password.")
    return {"token": make_token(rows[0]["id"]), "email": email}



class UrlIn(BaseModel):
    url: AnyHttpUrl


def ensure_public(url: str):
    """Basic SSRF guard: refuse localhost / private network targets."""
    host = urlparse(url).hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(400, "Could not resolve that website.")
    if any(not ipaddress.ip_address(i[4][0]).is_global for i in infos):
        raise HTTPException(400, "Private or local addresses are not allowed.")


def shoot_with_browser(url: str, path: Path) -> str:
    from playwright.sync_api import sync_playwright
    profile = str(Path(__file__).parent / ".chrome-profile")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chrome", headless=False,
            viewport={"width": 1280, "height": 800}, locale="en-IN",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(5000)  # let the listing finish loading
        title = page.title()
        if "access denied" in title.lower():
            ctx.close()
            raise RuntimeError("blocked by site")
        page.screenshot(path=str(path))
        ctx.close()
    return title


def shoot_with_service(url: str, path: Path):
    try:  
        r = httpx.get("https://api.microlink.io",
                      params={"url": url, "screenshot": "true", "meta": "false", "waitForTimeout": 3000},
                      timeout=60)
        img = httpx.get(r.json()["data"]["screenshot"]["url"], timeout=60)
        img.raise_for_status()
    except Exception:  # thum.io
        img = httpx.get(f"https://image.thum.io/get/width/1280/crop/800/{url}",
                        timeout=45, follow_redirects=True)
        img.raise_for_status()
    if not img.headers.get("content-type", "").startswith("image"):
        raise RuntimeError("not an image")
    path.write_bytes(img.content)


@app.post("/api/previews", status_code=201)
def add_preview(body: UrlIn, uid: int = Depends(current_user)):
    url = str(body.url)
    ensure_public(url)
    name = f"{uuid.uuid4().hex}.png"
    path = PREVIEWS / name
    title = None
    try:
        title = shoot_with_browser(url, path)
    except Exception:
        try:
            shoot_with_service(url, path)
        except Exception:
            path.unlink(missing_ok=True)
            name = None  # saved without an image; UI shows a placeholder
    now = datetime.now(timezone.utc).isoformat()
    _, pid = q("insert into previews(user_id, url, title, image, created_at) values(?,?,?,?,?)",
               (uid, url, title, name, now))
    return {"id": pid, "url": url, "title": title,
            "image": f"/previews/{name}" if name else None, "created_at": now}


@app.get("/api/previews")
def list_previews(uid: int = Depends(current_user)):
    rows, _ = q("select * from previews where user_id = ? order by id desc", (uid,))
    return [{"id": r["id"], "url": r["url"], "title": r["title"],
             "image": f"/previews/{r['image']}" if r["image"] else None,
             "created_at": r["created_at"]} for r in rows]
