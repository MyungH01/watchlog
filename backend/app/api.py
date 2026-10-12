import hashlib
import logging
import secrets
import time
import uuid
from datetime import timedelta
from pathlib import Path
from statistics import mean

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import aws, config, logs, rules
from .analysis import BPH_CANDIDATES
from .models import Measurement, Reading, SessionLocal, SessionToken, User, Watch, now

log = logging.getLogger("watchlog.api")
COOKIE = "wl_session"
COOKIE_MAX_AGE = 365 * 24 * 3600
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
FINISHED = ("done", "low_confidence", "failed")

logs.setup()
app = FastAPI(title="watchlog", openapi_url=None)


@app.middleware("http")
async def access_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
        response = JSONResponse({"detail": "서버 오류가 발생했습니다"}, status_code=500)
    response.headers["x-request-id"] = request_id
    if request.url.path not in ("/health", "/ready"):   # 상태 확인은 초마다 와서 로그를 덮는다
        log.info("request", extra={
            "request_id": request_id, "method": request.method, "path": request.url.path,
            "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000, 1),
        })
    return response


# ---------- 공통 ----------

def db():
    with SessionLocal() as s:
        yield s


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="lax")


def start_session(s: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    s.add(SessionToken(token_hash=hash_token(token), user_id=user.id))
    set_session_cookie(response, token)


def user_from_cookie(request: Request, s: Session) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return s.scalar(select(User).join(SessionToken).where(SessionToken.token_hash == hash_token(token)))


def current_user(request: Request, s: Session = Depends(db)) -> User:
    user = user_from_cookie(request, s)
    if not user:
        raise HTTPException(401, "세션이 없습니다")
    return user


def owned_watch(watch_id: uuid.UUID, user: User = Depends(current_user), s: Session = Depends(db)) -> Watch:
    watch = s.get(Watch, watch_id)
    if not watch or watch.user_id != user.id:   # 남의 것은 존재 여부도 알려 주지 않는다
        raise HTTPException(404, "시계를 찾을 수 없습니다")
    return watch


def owned_measurement(measurement_id: uuid.UUID, user: User = Depends(current_user),
                      s: Session = Depends(db)) -> Measurement:
    m = s.get(Measurement, measurement_id)
    if not m or m.watch.user_id != user.id:
        raise HTTPException(404, "측정을 찾을 수 없습니다")
    return m


def done_points(watch: Watch):
    return [(m.created_at, m.rate_s_per_day) for m in watch.measurements if m.status == "done"]


def watch_json(w: Watch) -> dict:
    visible = [m for m in w.measurements if m.status != "pending"]
    return {
        "id": w.id, "name": w.name, "brand": w.brand, "model": w.model, "bph": w.bph,
        "photo_url": aws.view_url(w.photo_key) if w.photo_key else None,
        "representative_rate": rules.representative_rate([r for _, r in done_points(w)]),
        "last_measured_at": visible[-1].created_at if visible else None,
        "created_at": w.created_at,
    }


def measurement_json(m: Measurement) -> dict:
    return {
        "id": m.id, "watch_id": m.watch_id, "status": m.status, "rate": m.rate_s_per_day,
        "rate_first_half": m.rate_first_half, "rate_second_half": m.rate_second_half,
        "beat_error_ms": m.beat_error_ms, "quality": m.quality, "detected_bph": m.detected_bph,
        "error_reason": m.error_reason, "created_at": m.created_at,
    }


def me_json(user: User) -> dict:
    return {"anonymous": user.google_sub is None, "email": user.email,
            "google_enabled": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)}


def user_object_keys(watches: list[Watch]) -> list[str]:
    keys = []
    for w in watches:
        keys += [w.photo_key] if w.photo_key else []
        keys += [m.audio_key for m in w.measurements]
        keys += [r.photo_key for r in w.readings if r.photo_key]
    return keys


def delete_objects_quietly(keys: list[str]) -> None:
    # DB가 기준이다. S3 정리가 실패해도 사용자 요청은 성공으로 본다 (남은 파일은 수명 주기 규칙으로 정리)
    try:
        if keys:
            aws.delete_objects(keys)
    except Exception:
        log.exception("s3 cleanup failed", extra={"count": len(keys)})


# ---------- 상태 확인 ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(s: Session = Depends(db)):
    try:
        s.execute(text("SELECT 1"))
    except Exception:
        log.exception("readiness check failed")
        raise HTTPException(503, "database unavailable")
    return {"status": "ready"}


# ---------- 세션 ----------

@app.post("/api/session")
def open_session(request: Request, response: Response, s: Session = Depends(db)):
    user = user_from_cookie(request, s)
    if user:
        set_session_cookie(response, request.cookies[COOKIE])   # 유효 기간 연장
    else:
        user = User()
        s.add(user)
        s.flush()
        start_session(s, user, response)
        s.commit()
    return me_json(user)


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return me_json(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user), s: Session = Depends(db)):
    if user.google_sub is None:
        raise HTTPException(400, "익명 사용자는 로그아웃하면 기록을 잃습니다")
    s.query(SessionToken).filter_by(token_hash=hash_token(request.cookies[COOKIE])).delete()
    s.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.delete("/api/me")
def delete_me(response: Response, user: User = Depends(current_user), s: Session = Depends(db)):
    keys = user_object_keys(user.watches)
    s.delete(user)
    s.commit()
    delete_objects_quietly(keys)
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------- 시계 ----------

class WatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    brand: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    bph: int | None = None
    photo_key: str | None = None

    @model_validator(mode="after")
    def check_bph(self):
        if self.bph is not None and self.bph not in BPH_CANDIDATES:
            raise ValueError(f"bph는 {BPH_CANDIDATES} 중 하나여야 합니다")
        return self


class WatchPatch(WatchIn):
    name: str | None = Field(None, min_length=1, max_length=100)


@app.get("/api/watches")
def list_watches(user: User = Depends(current_user)):
    return [watch_json(w) for w in sorted(user.watches, key=lambda w: w.created_at)]


@app.post("/api/watches", status_code=201)
def create_watch(body: WatchIn, user: User = Depends(current_user), s: Session = Depends(db)):
    watch = Watch(user_id=user.id, **body.model_dump(exclude={"photo_key"}))
    s.add(watch)
    s.commit()
    return watch_json(watch)


@app.get("/api/watches/{watch_id}")
def get_watch(watch: Watch = Depends(owned_watch)):
    return watch_json(watch)


@app.patch("/api/watches/{watch_id}")
def update_watch(body: WatchPatch, watch: Watch = Depends(owned_watch), s: Session = Depends(db)):
    changes = body.model_dump(exclude_unset=True)
    old_photo = None
    if changes.get("photo_key"):
        # 서버가 내준 경로만 받는다. 남의 파일 경로를 자기 시계에 붙일 수 없게
        if not changes["photo_key"].startswith(f"photos/{watch.user_id}/{watch.id}/"):
            raise HTTPException(400, "사진 경로가 올바르지 않습니다")
        old_photo = watch.photo_key
    if "name" in changes and changes["name"] is None:
        del changes["name"]
    for k, v in changes.items():
        setattr(watch, k, v)
    s.commit()
    delete_objects_quietly([old_photo] if old_photo else [])
    return watch_json(watch)


@app.delete("/api/watches/{watch_id}")
def delete_watch(watch: Watch = Depends(owned_watch), s: Session = Depends(db)):
    keys = user_object_keys([watch])
    s.delete(watch)
    s.commit()
    delete_objects_quietly(keys)
    return {"ok": True}


class PhotoIn(BaseModel):
    content_type: str


@app.post("/api/watches/{watch_id}/photo-url")
def photo_upload_url(body: PhotoIn, watch: Watch = Depends(owned_watch)):
    if body.content_type not in PHOTO_TYPES:
        raise HTTPException(400, "JPEG, PNG, WebP 사진만 올릴 수 있습니다")
    key = f"photos/{watch.user_id}/{watch.id}/{uuid.uuid4().hex}.{PHOTO_TYPES[body.content_type]}"
    return {"photo_key": key, "upload": aws.upload_form(key, body.content_type, config.MAX_PHOTO_BYTES)}


@app.get("/api/watches/{watch_id}/history")
def history(watch: Watch = Depends(owned_watch)):
    done = [m for m in watch.measurements if m.status == "done"]
    worn = rules.worn_rates([(r.taken_at, r.offset_seconds, r.reset) for r in watch.readings])
    summary = rules.summarize([(m.created_at, m.rate_s_per_day) for m in done],
                              [m.beat_error_ms for m in done if m.beat_error_ms is not None])
    # 실제 착용 일오차: 사진 기록으로 구한 최근 3구간 평균. 소리 측정과는 재는 대상이 달라 따로 보여 준다
    summary["worn_rate"] = mean(r for _, r in worn[-3:]) if worn else None
    return {
        "watch": watch_json(watch),
        "measurements": [measurement_json(m) for m in watch.measurements if m.status != "pending"],
        "readings": [{"id": r.id, "taken_at": r.taken_at, "offset_seconds": r.offset_seconds, "reset": r.reset,
                      "photo_url": aws.view_url(r.photo_key) if r.photo_key else None} for r in watch.readings],
        "worn_rates": [{"at": t, "rate": r} for t, r in worn],
        "summary": summary,
    }


# ---------- 사진 기록 ----------

class ReadingIn(BaseModel):
    shown_seconds: float = Field(ge=0, lt=86400)          # 사진 속 시계가 가리킨 시각 (자정부터의 초)
    elapsed_ms: float = Field(ge=0, le=3600_000)          # 셔터를 누른 뒤 지금까지 흐른 시간 (브라우저가 잰 값)
    tz_offset_minutes: int = Field(ge=-900, le=900)       # 브라우저의 Date.getTimezoneOffset()
    reset: bool = False
    with_photo: bool = True


@app.post("/api/watches/{watch_id}/readings", status_code=201)
def add_reading(body: ReadingIn, watch: Watch = Depends(owned_watch), s: Session = Depends(db)):
    # 촬영 시각은 서버 시계로 정한다. 폰 시계가 틀려 있어도 "지금부터 얼마 전에 찍었는지"는 정확하다.
    taken_at = now() - timedelta(milliseconds=body.elapsed_ms)
    local = taken_at - timedelta(minutes=body.tz_offset_minutes)
    true_seconds = local.hour * 3600 + local.minute * 60 + local.second + local.microsecond / 1e6
    offset = rules.dial_offset(body.shown_seconds, true_seconds)
    if abs(offset) > rules.MAX_READING_OFFSET:
        raise HTTPException(422, "실제 시각과 30분 넘게 차이 납니다. 사진 속 시각을 다시 확인해 주세요")
    rid = uuid.uuid4()
    key = f"photos/{watch.user_id}/{watch.id}/readings/{rid}.jpg" if body.with_photo else None
    reading = Reading(id=rid, watch_id=watch.id, taken_at=taken_at, offset_seconds=round(offset, 1),
                      reset=body.reset, photo_key=key)
    s.add(reading)
    s.commit()
    return {"id": rid, "offset_seconds": reading.offset_seconds,
            "upload": aws.upload_form(key, "image/jpeg", config.MAX_PHOTO_BYTES) if key else None}


@app.delete("/api/readings/{reading_id}")
def delete_reading(reading_id: uuid.UUID, user: User = Depends(current_user), s: Session = Depends(db)):
    reading = s.get(Reading, reading_id)
    if not reading or reading.watch.user_id != user.id:
        raise HTTPException(404, "기록을 찾을 수 없습니다")
    key = reading.photo_key
    s.delete(reading)
    s.commit()
    delete_objects_quietly([key] if key else [])
    return {"ok": True}


# ---------- 소리 측정 ----------

@app.post("/api/watches/{watch_id}/measurements", status_code=201)
def create_measurement(watch: Watch = Depends(owned_watch), s: Session = Depends(db)):
    mid = uuid.uuid4()
    m = Measurement(id=mid, watch_id=watch.id, audio_key=f"audio/{watch.user_id}/{mid}.wav")
    s.add(m)
    s.commit()
    return {"id": m.id, "upload": aws.upload_form(m.audio_key, "audio/wav", config.MAX_AUDIO_BYTES)}


@app.post("/api/measurements/{measurement_id}/uploaded")
def measurement_uploaded(m: Measurement = Depends(owned_measurement), s: Session = Depends(db)):
    # pending과 queued 모두 다시 큐에 넣을 수 있게 해서, 큐 전송이 실패했을 때 브라우저가 재시도할 수 있다.
    # 같은 메시지가 두 번 들어가도 워커가 한 번만 처리한다.
    if m.status in ("pending", "queued"):
        if aws.object_size(m.audio_key) is None:
            raise HTTPException(400, "녹음 파일이 아직 올라오지 않았습니다")
        m.status = "queued"
        s.commit()
        aws.enqueue(str(m.id))
    return measurement_json(m)


@app.get("/api/measurements/{measurement_id}")
def get_measurement(m: Measurement = Depends(owned_measurement)):
    return measurement_json(m)


@app.delete("/api/measurements/{measurement_id}")
def delete_measurement(m: Measurement = Depends(owned_measurement), s: Session = Depends(db)):
    key = m.audio_key
    s.delete(m)
    s.commit()
    delete_objects_quietly([key])
    return {"ok": True}


from .auth_google import router as google_router  # noqa: E402  (위의 공통 함수를 쓰므로 여기서 불러온다)

app.include_router(google_router)


# ---------- 웹 화면 (빌드된 정적 파일) ----------

if config.STATIC_DIR:
    static = Path(config.STATIC_DIR).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (static / path).resolve()
        if path and file.is_file() and static in file.parents:
            return FileResponse(file)
        return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})
