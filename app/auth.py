import logging
import secrets
import time
from dataclasses import dataclass
from email.message import EmailMessage

import aiosmtplib
from fastapi import Request, Response

from app import db
from app.config import config

log = logging.getLogger("mnemosyne.auth")

MAGIC_LINK_TTL_SECONDS = 15 * 60
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_COOKIE = "session"


@dataclass
class Session:
    token: str
    email: str
    expires_at: int


def _now() -> int:
    return int(time.time())


async def send_magic_link(email: str) -> None:
    submitted = email.lower().strip()
    if submitted != config.magic_link_email:
        # Avoid enumeration: no-op, still show "sent" UI to the caller.
        log.warning("magic link requested for non-allowlisted email")
        return

    token = secrets.token_urlsafe(32)
    now = _now()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO magic_links (token, email, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, submitted, now, now + MAGIC_LINK_TTL_SECONDS),
        )

    link = f"{config.base_url}/auth/verify?token={token}"

    if not config.smtp_configured:
        log.warning("SMTP not configured; magic link for %s: %s", submitted, link)
        return

    msg = EmailMessage()
    msg["From"] = config.smtp_from
    msg["To"] = submitted
    msg["Subject"] = "Mnemosyne sign-in link"
    msg.set_content(
        f"Sign in to Mnemosyne:\n\n{link}\n\n"
        f"This link expires in 15 minutes. If you didn't request it, ignore this email."
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_user or None,
            password=config.smtp_password or None,
            start_tls=True,
        )
    except Exception:
        log.exception("failed to send magic link email")


def consume_magic_link(token: str) -> Session | None:
    now = _now()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT email, expires_at, used_at FROM magic_links WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None or row["used_at"] is not None or row["expires_at"] < now:
            return None
        conn.execute("UPDATE magic_links SET used_at = ? WHERE token = ?", (now, token))
        session_token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_TTL_SECONDS
        conn.execute(
            "INSERT INTO sessions (token, email, created_at, expires_at, last_used_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_token, row["email"], now, expires_at, now),
        )
    return Session(token=session_token, email=row["email"], expires_at=expires_at)


def session_from_request(request: Request) -> Session | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    now = _now()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT email, expires_at FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None or row["expires_at"] < now:
            return None
        conn.execute("UPDATE sessions SET last_used_at = ? WHERE token = ?", (now, token))
    return Session(token=token, email=row["email"], expires_at=row["expires_at"])


def set_session_cookie(response: Response, session: Session) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=config.base_url.startswith("https://"),
    )


def revoke(token: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
