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

# Discover widgets at import time, then mount their routers.
widget_api.discover()
for _w in widget_api.registry.all():
    if _w.router is not None:
        app.include_router(_w.router, prefix=f"/widgets/{_w.id}", tags=[_w.id])


@app.on_event("startup")
def _startup() -> None:
    db.init()


def current_session(request: Request) -> auth.Session:
    session = auth.session_from_request(request)
    if session is None:
        raise HTTPException(status_code=401)
    return session


def maybe_session(request: Request) -> auth.Session | None:
    return auth.session_from_request(request)


def _workspace_from(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _annotated_layout(workspace: str) -> list[dict]:
    """Drop layout entries whose widget is no longer registered."""
    out = []
    for it in widget_api.get_layout(workspace):
        w = widget_api.registry.get(it.get("widget_id"))
        if w is None:
            continue
        out.append({**it, "widget": w})
    return out


@app.get("/", response_class=HTMLResponse)
def root(request: Request, session: auth.Session | None = Depends(maybe_session)) -> Response:
    if session is None:
        return RedirectResponse("/login", status_code=302)
    workspace = _workspace_from(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "email": session.email,
            "workspace": workspace,
            "all_widgets": widget_api.registry.all(),
            "layout_items": _annotated_layout(workspace),
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
def auth_verify(token: str) -> Response:
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
    workspace = _workspace_from(request)
    payload = await request.json()
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="expected a list")
    # Preserve widget_id (and any other meta we set on the server) by merging
    # with the stored layout. Gridstack's save() only emits {id,x,y,w,h}.
    existing = {it.get("id"): it for it in widget_api.get_layout(workspace)}
    merged = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        instance_id = item.get("id")
        prev = existing.get(instance_id, {})
        merged.append({
            "id": instance_id,
            "widget_id": prev.get("widget_id") or item.get("widget_id"),
            "x": int(item.get("x", 0)),
            "y": int(item.get("y", 0)),
            "w": int(item.get("w", 1)),
            "h": int(item.get("h", 1)),
        })
    widget_api.save_layout(workspace, merged)
    return Response(status_code=204)


@app.post("/layout/add")
def layout_add(
    request: Request,
    widget_id: str = Form(...),
    session: auth.Session = Depends(current_session),
) -> Response:
    workspace = _workspace_from(request)
    try:
        widget_api.add_to_layout(workspace, widget_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/", status_code=303)


@app.post("/layout/remove")
def layout_remove(
    request: Request,
    instance_id: str = Form(...),
    session: auth.Session = Depends(current_session),
) -> Response:
    workspace = _workspace_from(request)
    widget_api.remove_from_layout(workspace, instance_id)
    return RedirectResponse("/", status_code=303)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
