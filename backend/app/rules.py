"""기록에서 일오차·대표값·요약을 계산하는 순수 함수들. 기준값은 REQUIREMENTS.md 4.3, 4.5, 4.7."""
from datetime import datetime, timedelta
from math import sqrt
from statistics import linear_regression, mean, median

REPRESENTATIVE_COUNT = 3
OUTLIER_LIMIT = 5.0                   # 최근 측정 중앙값과의 차이(초/일)
OUTLIER_MIN_HISTORY = 3

MIN_READING_GAP = timedelta(hours=12)  # 초침을 ±1초 틀리게 읽어도 일오차 ±2초 안에 들어오는 간격
MAX_READING_OFFSET = 30 * 60          # 시계가 30분 넘게 틀려 있다면 입력 실수로 본다
HALF_DIAL = 6 * 3600                  # 12시간 다이얼이라 오전·오후는 구분하지 않는다

OVERHAUL_RATE = 20.0                  # 일오차가 이쯤 되면 보통 점검(오버홀)을 한다
SUDDEN_JUMP = 15.0                    # 최근 3회 평균이 이전 중앙값보다 이만큼 빨라지면 자성 의심
TREND_MIN_COUNT = 10                  # 추세를 말하려면 필요한 측정 수와 기간
TREND_MIN_SPAN = timedelta(days=90)
TREND_MAX_DAYS = 5 * 365              # 이보다 먼 예상은 말하지 않는다
BEAT_ERROR_GOOD, BEAT_ERROR_OK = 0.5, 1.0   # ms


def dial_offset(shown_seconds: float, true_seconds: float) -> float:
    """시계가 가리킨 시각과 실제 시각(둘 다 자정부터의 초) → 시계가 앞선 초. 12시간 다이얼 기준으로 가까운 쪽을 고른다."""
    return (shown_seconds - true_seconds + HALF_DIAL) % (2 * HALF_DIAL) - HALF_DIAL


def worn_rates(readings: list[tuple[datetime, float, bool]]) -> list[tuple[datetime, float]]:
    """사진 기록 (시각, 앞선 초, 다시 맞춤 여부) 목록(시간순) → (시각, 그 구간의 실제 착용 일오차).

    다시 맞춘 기록은 새 기준점이 되고 그 앞 기록과는 잇지 않는다. 간격이 너무 짧은 기록은 건너뛰고
    더 이른 기준점을 그대로 쓴다(간격이 길수록 정확하다).
    """
    out, base = [], None
    for t, offset, reset in readings:
        if reset or base is None:
            base = (t, offset)
        elif t - base[0] >= MIN_READING_GAP:
            out.append((t, (offset - base[1]) / ((t - base[0]).total_seconds() / 86400)))
            base = (t, offset)
    return out


def representative_rate(done_rates: list[float]) -> float | None:
    """성공한 측정(시간순)의 최근 3회 평균."""
    recent = done_rates[-REPRESENTATIVE_COUNT:]
    return mean(recent) if recent else None


def is_outlier(rate: float, previous_done_rates: list[float]) -> bool:
    recent = previous_done_rates[-5:]
    return len(recent) >= OUTLIER_MIN_HISTORY and abs(rate - median(recent)) > OUTLIER_LIMIT


def period(days: float) -> str:
    if days < 60:
        return f"{round(days)}일"
    months = round(days / 30.44)
    if months < 24:
        return f"{months}개월"
    years, rest = divmod(months, 12)
    return f"{years}년" + (f" {rest}개월" if rest else "")


def trend(points: list[tuple[datetime, float]]) -> dict | None:
    """일오차가 변하는 속도와, 그 추세가 이어질 때 점검 기준(±20초)에 이르기까지 남은 날.

    기록이 부족하면 None. 변화가 측정 흔들림과 구분되지 않으면 per_month가 None이다.
    지금까지의 변화가 직선으로 이어진다고 가정한 참고값이다. 실제 시계는 그렇게 변하지 않을 수 있다.
    """
    span = points[-1][0] - points[0][0] if points else timedelta(0)
    if len(points) < TREND_MIN_COUNT or span < TREND_MIN_SPAN:
        return None
    x = [(t - points[0][0]).total_seconds() / 86400 for t, _ in points]
    y = [r for _, r in points]
    slope, intercept = linear_regression(x, y)
    residual = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))
    error = sqrt(residual / (len(x) - 2)) / sqrt(sum((xi - mean(x)) ** 2 for xi in x))
    out = {"observed_days": span.days, "per_month": None, "days_to_overhaul": None, "target": None}
    if abs(slope) <= 2 * error:           # 기울기가 오차의 두 배도 안 되면 변화라고 보지 않는다
        return out
    now = intercept + slope * x[-1]
    target = OVERHAUL_RATE if slope > 0 else -OVERHAUL_RATE
    days = (target - now) / slope
    out["per_month"] = slope * 30.44
    if 0 < days <= TREND_MAX_DAYS:
        out["days_to_overhaul"], out["target"] = days, target
    return out


def summarize(points: list[tuple[datetime, float]], beat_errors: list[float]) -> dict:
    """성공한 측정 (시각, 일오차)와 비트 에러 목록(시간순) → 화면에 보여 줄 요약.

    평소에는 수치만 적고, 알릴 일(서서히 변함, 갑자기 빨라짐, 오버홀 시기)이 있을 때만 문장을 덧붙인다.

    status: empty | collecting | steady | trending | overhaul | magnetized
    """
    rates = [r for _, r in points]
    rate = representative_rate(rates)
    recent = rates[-5:]
    out = {
        "status": "empty", "sentence": "아직 측정 기록이 없습니다.", "rate": rate,
        "beat_error_ms": median(beat_errors[-REPRESENTATIVE_COUNT:]) if beat_errors else None,
        "spread": (max(recent) - min(recent)) / 2 if len(recent) >= 2 else None,
        "count": len(points), "trend": None,
    }
    if rate is None:
        return out

    head = f"일오차 {rate:+.1f}초"
    be = out["beat_error_ms"]
    if be is None:
        head += "입니다."
    else:
        word = "고릅니다" if be <= BEAT_ERROR_GOOD else "양호합니다" if be <= BEAT_ERROR_OK else "다소 고르지 않습니다"
        head += f", 비트 에러 {be:.1f}ms로 박자가 {word}."

    t = out["trend"] = trend(points)
    if len(rates) >= 6 and mean(rates[-3:]) - median(rates[:-3]) > SUDDEN_JUMP:
        status, tail = "magnetized", "최근 갑자기 빨라졌습니다. 자성의 영향일 수 있습니다."
    elif len(rates) >= REPRESENTATIVE_COUNT and abs(rate) >= OVERHAUL_RATE:
        status, tail = "overhaul", f"일오차가 ±{OVERHAUL_RATE:.0f}초에 이르렀습니다. 오버홀을 고려할 시기입니다."
    elif t is None:
        status, tail = "collecting", ""   # 추세를 말하기엔 기록이 부족하다
    elif t["days_to_overhaul"] is None:
        status, tail = "steady", ""       # 변화가 없거나 아주 느리면 따로 알리지 않는다
    else:
        status = "trending"
        tail = (f"한 달에 {t['per_month']:+.1f}초씩 변하고 있습니다. "
                f"이 추세가 이어지면 약 {period(t['days_to_overhaul'])} 뒤 {t['target']:+.0f}초에 이릅니다.")
    out["status"], out["sentence"] = status, f"{head} {tail}".strip()
    return out
