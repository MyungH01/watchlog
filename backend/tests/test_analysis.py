"""실제 아이폰 녹음(fixtures)으로 분석 모듈을 검증한다. 기준값은 REQUIREMENTS.md 7장."""
import shutil
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from app.analysis import InvalidAudio, analyze

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
GOOD = {"rec2.wav": 6.9, "rec3.wav": 5.5, "rec4.wav": 8.6, "rec5.wav": 8.1, "rec6.wav": 6.0}


@pytest.fixture(scope="module")
def results():
    return {name: analyze(FIXTURES / name) for name in GOOD}


@pytest.mark.parametrize("name,expected", GOOD.items())
def test_good_recordings(results, name, expected):
    r = results[name]
    assert r.status == "done"
    assert r.bph == 28800
    assert r.rate == pytest.approx(expected, abs=1.0)


def test_average_of_good_recordings(results):
    assert np.mean([r.rate for r in results.values()]) == pytest.approx(7.0, abs=1.0)


def test_weak_recording_is_processed():
    r = analyze(FIXTURES / "rec1_weak_signal.wav")
    assert r.bph == 28800 and r.rate is not None   # 이상값 판정은 과거 기록이 있는 워커 쪽에서 한다


def test_noise_only_fails(tmp_path):
    p = tmp_path / "noise.wav"
    x = (np.random.default_rng(0).standard_normal(48000 * 20) * 3000).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(x.tobytes())
    r = analyze(p)
    assert r.status == "failed" and r.rate is None


def test_other_beat_rate(tmp_path):
    # 표본은 그대로 두고 헤더의 표본 주파수만 36,000Hz로 바꾸면 0.75배속 = 21,600bph처럼 보인다
    p = tmp_path / "slow.wav"
    shutil.copy(FIXTURES / "rec3.wav", p)
    with open(p, "r+b") as f:
        f.seek(24); f.write(struct.pack("<II", 36000, 72000))
    assert analyze(p).bph == 21600


def test_not_a_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"not audio")
    with pytest.raises(InvalidAudio):
        analyze(p)
