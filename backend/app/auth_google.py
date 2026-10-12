"""구글 계정 연결 (선택 기능). 익명 사용자에 구글 ID를 덧붙이거나, 이미 연결된 계정으로 세션을 바꾼다."""
import base64
import json
import logging
import secrets
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import config
from .api import COOKIE, db, hash_token, start_session, user_from_cookie
from .models import SessionToken, User, Watch

log = logging.getLogger("watchlog.auth")
router = APIRouter(prefix="/api/auth/google")
STATE_COOKIE = "wl_oauth_state"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def _redirect_uri() -> str:
    return config.PUBLIC_BASE_URL.rstrip("/") + "/api/auth/google/callback"


def _require_enabled() -> None:
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        raise HTTPException(404, "구글 계정 연결이 설정되지 않았습니다")


def exchange_code(code: str) -> dict:
    """인증 코드를 구글에 보내 사용자 정보(sub, email)를 받는다."""
    body = urllib.parse.urlencode({
        "code": code, "client_id": config.GOOGLE_CLIENT_ID, "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": _redirect_uri(), "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=10) as res:
        id_token = json.load(res)["id_token"]
    # 이 토큰은 구글 토큰 주소에서 TLS로 직접 받은 것이라 서명 검증을 생략한다 (OIDC Core 3.1.3.7).
    # 브라우저가 전달한 id_token을 받는 구조로 바꾼다면 반드시 서명을 검증해야 한다.
    payload = id_token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if claims.get("aud") != config.GOOGLE_CLIENT_ID or claims.get("iss") not in ISSUERS or claims.get("exp", 0) < time.time():
        raise ValueError("unexpected id_token claims")
    return claims


def link_google(s: Session, current: User | None, sub: str, email: str | None) -> User:
    """구글 계정에 해당하는 사용자를 돌려준다. 필요하면 익명 사용자의 시계를 그쪽으로 합친다."""
    existing = s.scalar(select(User).where(User.google_sub == sub))
    if existing is None:
        user = current if current and current.google_sub is None else User()
        user.google_sub, user.email = sub, email
        s.add(user)
        s.flush()
        return user
    if current and current.id != existing.id and current.google_sub is None:
        # 이 브라우저에서 익명으로 쌓은 시계를 기존 계정으로 옮기고 익명 사용자는 지운다.
        # 관계를 거치지 않고 직접 고친다: 관계로 지우면 옮긴 시계까지 함께 지워진다.
        s.execute(update(Watch).where(Watch.user_id == current.id).values(user_id=existing.id))
        s.execute(delete(SessionToken).where(SessionToken.user_id == current.id))
        s.execute(delete(User).where(User.id == current.id))
        s.expire_all()
    existing.email = email
    return existing


@router.get("/login")
def login():
    _require_enabled()
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": config.GOOGLE_CLIENT_ID, "redirect_uri": _redirect_uri(), "response_type": "code",
        "scope": "openid email", "state": state, "prompt": "select_account",
    }))
    response.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, secure=config.COOKIE_SECURE, samesite="lax")
    return response


@router.get("/callback")
def callback(request: Request, code: str = "", state: str = "", s: Session = Depends(db)):
    _require_enabled()
    expected = request.cookies.get(STATE_COOKIE)
    # state가 다르면 다른 사람이 만든 로그인 링크를 밟은 것일 수 있다 (CSRF)
    if not code or not expected or not secrets.compare_digest(state, expected):
        raise HTTPException(400, "로그인 요청이 올바르지 않습니다. 다시 시도해 주세요")
    try:
        claims = exchange_code(code)
    except Exception:
        log.exception("google token exchange failed")
        raise HTTPException(502, "구글 로그인에 실패했습니다. 다시 시도해 주세요")

    old_token = request.cookies.get(COOKIE)
    user = link_google(s, user_from_cookie(request, s), claims["sub"], claims.get("email"))
    if old_token:
        s.execute(delete(SessionToken).where(SessionToken.token_hash == hash_token(old_token)))
    response = RedirectResponse("/#/account", status_code=303)
    start_session(s, user, response)
    s.commit()
    response.delete_cookie(STATE_COOKIE)
    log.info("google linked", extra={"user_id": str(user.id)})
    return response
