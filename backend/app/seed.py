"""점검 알림을 눈으로 확인하기 위한 6개월치 예시 기록. 새 익명 사용자와 시계 세 개를 만들고 세션 토큰을 출력한다."""
import random
import secrets
from datetime import timedelta

from .api import COOKIE, hash_token
from .models import Measurement, Reading, SessionLocal, SessionToken, User, Watch, now

DAYS, STEP = 180, 6


def _rate(kind: str, day: int) -> float:
    if kind == "drift":            # 반년에 걸쳐 +4 → +13
        return 4 + 9 * day / DAYS
    if kind == "magnetized":       # 마지막 3주에 갑자기 +30대
        return 5 + (28 if day > DAYS - 20 else 0)
    return 6.0


def run() -> None:
    rng = random.Random(1)
    token = secrets.token_urlsafe(32)
    with SessionLocal() as s:
        user = User()
        s.add(user)
        s.flush()
        s.add(SessionToken(token_hash=hash_token(token), user_id=user.id))
        for name, kind in (("[예시] 안정적인 시계", "stable"), ("[예시] 서서히 변하는 시계", "drift"),
                           ("[예시] 갑자기 빨라진 시계", "magnetized")):
            watch = Watch(user_id=user.id, name=name, bph=28800)
            s.add(watch)
            s.flush()
            for day in range(0, DAYS + 1, STEP):
                at = now() - timedelta(days=DAYS - day)
                rate = _rate(kind, day) + rng.uniform(-1, 1)
                s.add(Measurement(
                    watch_id=watch.id, status="done", audio_key=f"seed/{watch.id}/{day}.wav",
                    rate_s_per_day=rate, rate_first_half=rate, rate_second_half=rate,
                    beat_error_ms=0.3, quality=0.9, detected_bph=28800, created_at=at, analyzed_at=at,
                ))
            if kind == "stable":
                # 최근 한 달, 사흘마다 찍은 사진 기록. 하루 5초씩 앞서 가서 실제 착용 일오차 +5초가 나온다
                for ago in range(30, -1, -3):
                    s.add(Reading(watch_id=watch.id, taken_at=now() - timedelta(days=ago),
                                  offset_seconds=round(5 * (30 - ago) + rng.uniform(-1, 1), 1), reset=ago == 30))
        s.commit()
    print("예시 사용자를 만들었습니다. 브라우저 개발자 도구에서 아래 쿠키를 설정한 뒤 새로고침하세요.")
    print(f"  {COOKIE}={token}")
