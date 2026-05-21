from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth, db, widget_api
from app.config import config

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Mnemosyne")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    db.init()
    widget_api.discover()


def current_session(request: Request) -> auth.Session:
    session = auth.session_from_request(request)
    if session is None:
        raise HTTPException(status_code=401)
    return session


def maybe_session(request: Request) -> auth.Session | None:
    return auth.session_from_request(request)


@app.get("/", response_class=HTMLResponse)
def root(request: Request, session: auth.Session | None = Depends(maybe_session)) -> Response:
    if session is None:
        return RedirectResponse("/login", status_code=302)
    workspace = request.cookies.get("workspace", "personal")
    if workspace not in ("personal", "work"):
        workspace = "personal"
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "email": session.email,
            "workspace": workspace,
            "widgets": widget_api.registry.all(),
            "layout": widget_api.get_layout(workspace),
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, sent: bool = False) -> Response:
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "sent": sent, "email_hint": config.magic_link_email},
    )


@app.post("/auth/request")
async def auth_request(email: str = Form(...)) -> Response:
    await auth.send_magic_link(email)
    return RedirectResponse("/login?sent=1", status_code=303)


@app.get("/auth/verify")
def auth_verify(token: str, response: Response) -> Response:
    session = auth.consume_magic_link(token)
    if session is None:
        raise HTTPException(status_code=400, detail="invalid or expired link")
    resp = RedirectResponse("/", status_code=303)
    auth.set_session_cookie(resp, session)
    return resp


@app.post("/auth/logout")
def auth_logout(session: auth.Session = Depends(current_session)) -> Response:
    auth.revoke(session.token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp


@app.post("/workspace/{name}")
def switch_workspace(name: str, session: auth.Session = Depends(current_session)) -> Response:
    if name not in ("personal", "work"):
        raise HTTPException(status_code=400, detail="unknown workspace")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("workspace", name, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return resp


@app.post("/layout")
async def save_layout(
    request: Request,
    session: auth.Session = Depends(current_session),
) -> Response:
    workspace = request.cookies.get("workspace", "personal")
    if workspace not in ("personal", "work"):
        workspace = "personal"
    payload = await request.json()
    widget_api.save_layout(workspace, payload)
    return Response(status_code=204)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
