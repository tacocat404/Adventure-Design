"""소셜 로그인 (카카오 · 구글) — 인가 코드 방식.

흐름: 앱 → /api/auth/{제공자}/start → 제공자 로그인 창 → /api/auth/{제공자}/callback
      → 서버가 코드를 접근 토큰으로 바꾸고 프로필을 확인 → 앱(/#login=...)으로 돌려보냄.
설정 (backend/.env): KAKAO_CLIENT_ID · KAKAO_CLIENT_SECRET (구글 GOOGLE_* 도 같은 모양),
                     OAUTH_BASE (기본 http://localhost:5173 — 앱 주소).
제공자 콘솔에 등록할 redirect URI: {OAUTH_BASE}/api/auth/{제공자}/callback
키가 없는 제공자는 "연결 전"으로 보이고, 개발 중에는 데모 로그인이 대신 돈다.
"""
import base64
import json
import secrets
import urllib.parse
import urllib.request

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.api.main import CONF, ApiError, Social, sign, social, unsign

router = APIRouter()

SPEC = {
    "kakao": {"auth": "https://kauth.kakao.com/oauth/authorize", "token": "https://kauth.kakao.com/oauth/token", "scope": None},
    "google": {"auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token", "scope": "openid profile"},
}


def base():
    return CONF.get("OAUTH_BASE", "http://localhost:5173").rstrip("/")


def keys(p):
    return CONF.get(f"{p.upper()}_CLIENT_ID", ""), CONF.get(f"{p.upper()}_CLIENT_SECRET", "")


def ready():
    """키가 들어 있어 진짜 로그인이 되는 제공자 (카카오는 비밀키가 없어도 됨)"""
    return [p for p in SPEC if keys(p)[0] and (keys(p)[1] or p == "kakao")]


def redirect_uri(p):
    return f"{base()}/api/auth/{p}/callback"


def back(result):
    """앱으로 돌려보낸다. 결과는 주소 # 뒤에 실어서 서버 기록에 남지 않게 한다."""
    packed = base64.urlsafe_b64encode(json.dumps(result, ensure_ascii=False).encode()).decode().rstrip("=")
    return RedirectResponse(f"{base()}/#login={packed}", status_code=302)


@router.get("/api/auth/{provider}/start")
def start(provider: str, role: str = "parent"):
    role = role if role in ("parent", "staff") else "parent"
    if provider not in ready():
        return back({"kind": "error", "role": role, "message": "이 로그인은 아직 연결 전이에요."})
    q = {"client_id": keys(provider)[0], "redirect_uri": redirect_uri(provider), "response_type": "code",
         "state": sign({"p": provider, "r": role, "n": secrets.token_urlsafe(8)}, 600)}
    if SPEC[provider]["scope"]:
        q["scope"] = SPEC[provider]["scope"]
    return RedirectResponse(SPEC[provider]["auth"] + "?" + urllib.parse.urlencode(q), status_code=302)


def exchange(provider, code, state):
    cid, secret = keys(provider)
    data = {"grant_type": "authorization_code", "client_id": cid, "redirect_uri": redirect_uri(provider), "code": code}
    if secret:
        data["client_secret"] = secret
    req = urllib.request.Request(SPEC[provider]["token"], data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.load(urllib.request.urlopen(req, timeout=8))["access_token"]


@router.get("/api/auth/{provider}/callback")
def callback(provider: str, code: str = "", state: str = "", error: str = ""):
    st = unsign(state) if state else None
    if provider not in ready() or not st or st.get("p") != provider:
        return back({"kind": "error", "role": "parent", "message": "로그인을 확인하지 못했어요. 다시 해 주세요."})
    role = st["r"]
    if error or not code:
        return back({"kind": "error", "role": role, "message": "로그인을 취소했어요."})
    try:
        r = social(Social(provider=provider, token=exchange(provider, code, state)))
    except ApiError as e:
        if e.code == "PENDING_APPROVAL":
            return back({"kind": "pending"})
        return back({"kind": "error", "role": role, "message": "로그인을 확인하지 못했어요. 다시 해 주세요."})
    except Exception:
        return back({"kind": "error", "role": role, "message": "로그인을 확인하지 못했어요. 다시 해 주세요."})
    if r.get("needs_signup"):
        return back({"kind": "signup", "role": role, "provider": provider, "ticket": r["ticket"], "name": r["name"]})
    return back({"kind": "in", "role": role, **r})
