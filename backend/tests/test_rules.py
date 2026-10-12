from datetime import datetime, timedelta, timezone

import pytest

from app import rules

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def day(n: float) -> datetime:
    return T0 + timedelta(days=n)


def test_dial_offset_picks_the_near_side_of_a_12_hour_dial():
    assert rules.dial_offset(8 * 3600 + 30, 8 * 3600 + 23) == 7           # 시계가 7초 빠름
    assert rules.dial_offset(8 * 3600 + 30, 20 * 3600 + 23) == 7          # 오후 8시에 찍어도 같다
    assert rules.dial_offset(5, 12 * 3600 - 5) == 10                      # 12시를 넘어가는 경우
    assert rules.dial_offset(11 * 3600 + 59 * 60 + 50, 10) == -20


def test_worn_rate_between_two_photos():
    # 월요일 +7초, 이틀 뒤 +21초 → 하루 +7초
    assert rules.worn_rates([(day(0), 7, False), (day(2), 21, False)]) == [(day(2), 7.0)]


def test_reset_starts_a_new_baseline():
    readings = [(day(0), 7, False), (day(2), 21, False), (day(2.1), 1, True), (day(4.1), 11, False)]
    assert rules.worn_rates(readings) == [(day(2), 7.0), (day(4.1), pytest.approx(5.0))]


def test_photos_taken_too_close_are_skipped_but_baseline_is_kept():
    readings = [(day(0), 0, False), (day(0.1), 1, False), (day(1), 6, False)]
    assert rules.worn_rates(readings) == [(day(1), 6.0)]


def test_representative_rate_is_mean_of_last_three():
    assert rules.representative_rate([100, 6, 7, 8]) == 7
    assert rules.representative_rate([]) is None


def test_outlier_needs_history():
    assert not rules.is_outlier(-2, [7, 7])
    assert rules.is_outlier(-2, [6, 7, 8])
    assert not rules.is_outlier(9, [6, 7, 8])


def series(rates, step=10):
    return [(day(i * step), r) for i, r in enumerate(rates)]


def test_period_wording():
    assert [rules.period(d) for d in (9, 150, 400, 830)] == ["9일", "5개월", "13개월", "2년 3개월"]


def test_summary_without_measurements():
    assert rules.summarize([], [])["status"] == "empty"


def test_summary_states_rate_and_beat_error():
    s = rules.summarize(series([7.0, 7.2, 7.1]), [0.3, 0.3, 0.3])
    assert s["status"] == "collecting"
    assert s["sentence"] == "일오차 +7.1초, 비트 에러 0.3ms로 박자가 고릅니다."
    assert s["spread"] == pytest.approx(0.1)


def test_no_trend_when_change_is_within_noise():
    wobble = [6 + (0.8 if i % 2 else -0.8) for i in range(40)]
    s = rules.summarize(series(wobble), [])
    assert s["status"] == "steady"
    assert s["sentence"] == "일오차 +6.3초입니다."      # 변화가 없으면 수치만 보여 준다


def test_trend_projects_when_overhaul_threshold_is_reached():
    # 열흘마다 +0.5초 → 한 달에 약 +1.5초. 지금 +12초이니 +20초까지 160일(약 5개월)
    s = rules.summarize(series([4 + 0.5 * i for i in range(17)]), [])
    assert s["status"] == "trending"
    assert s["trend"]["per_month"] == pytest.approx(1.52, abs=0.01)
    assert s["trend"]["days_to_overhaul"] == pytest.approx(160, abs=1)
    assert "약 5개월 뒤 +20초에 이릅니다" in s["sentence"]


def test_slowing_watch_projects_toward_minus_twenty():
    s = rules.summarize(series([-4 - 0.5 * i for i in range(17)]), [])
    assert s["trend"]["target"] == -20 and "-20초에 이릅니다" in s["sentence"]


def test_too_slow_a_change_gives_no_date():
    s = rules.summarize(series([5 + 0.01 * i for i in range(40)]), [])
    assert s["status"] == "steady" and s["sentence"].endswith("초입니다.")


def test_already_past_threshold():
    s = rules.summarize(series([22, 23, 22]), [])
    assert s["status"] == "overhaul" and "오버홀을 고려할 시기" in s["sentence"]


def test_sudden_jump_reads_as_magnetism_not_trend():
    s = rules.summarize(series([5] * 12 + [30, 31, 32]), [])
    assert s["status"] == "magnetized"
