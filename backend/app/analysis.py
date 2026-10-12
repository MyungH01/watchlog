"""녹음(WAV)에서 기계식 시계의 일오차를 구한다. DB·AWS와 무관한 순수 계산 모듈.

방법은 REQUIREMENTS.md 4.5를 따른다: 고역 포락선 → 박자 판별 → 주기를 바꿔 가며 겹쳐 보기(에포크 폴딩).
"""
import wave
from dataclasses import dataclass

import numpy as np
from scipy import signal

BPH_CANDIDATES = (18000, 21600, 25200, 28800, 36000)
BAND_HZ = (6000, 16000)        # 째깍 소리는 6kHz 이상에만 있다 (실측)
ENV_RATE_HZ = 8000             # 폴딩용 포락선 해상도 (0.125ms)
FOLD_BIN_S = 0.0002
COARSE_PPM, COARSE_STEP = 3000, 10   # ±3000ppm ≈ ±260초/일
FINE_PPM, FINE_STEP = 100, 2
MIN_SECONDS = 10
MIN_QUALITY = 0.25             # 이 미만이면 실패
HALF_DIFF_LIMIT = 3.0          # 앞뒤 절반 일오차 차이(초/일)가 이보다 크면 낮은 신뢰
PPM_TO_S_PER_DAY = 0.0864


class InvalidAudio(Exception):
    """다시 시도해도 소용없는 입력 오류."""


@dataclass
class Result:
    status: str                      # done | low_confidence | failed
    quality: float
    bph: int | None = None
    rate: float | None = None        # 초/일, +면 빠름
    rate_first_half: float | None = None
    rate_second_half: float | None = None
    beat_error_ms: float | None = None
    reason: str | None = None


def read_wav(path) -> tuple[np.ndarray, int]:
    try:
        with wave.open(str(path), "rb") as w:
            fs, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise InvalidAudio(f"WAV 파일이 아닙니다: {e}") from e
    if width != 2:
        raise InvalidAudio("16비트 WAV만 지원합니다")
    if fs < 32000:
        raise InvalidAudio("표본 주파수가 너무 낮습니다")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768
    if ch > 1:
        x = x[::ch]
    if len(x) < MIN_SECONDS * fs:
        raise InvalidAudio("녹음이 너무 짧습니다")
    return x, fs


def envelope(x: np.ndarray, fs: int) -> tuple[np.ndarray, float]:
    """고역 포락선을 ENV_RATE_HZ 근처로 줄여서 돌려준다."""
    hi = min(BAND_HZ[1], 0.45 * fs)
    sos = signal.butter(4, (BAND_HZ[0], hi), btype="bandpass", fs=fs, output="sos")
    env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))
    env = np.minimum(env, np.percentile(env, 99.9))   # 손이 닿는 소리 같은 큰 충격 억제
    k = max(1, fs // ENV_RATE_HZ)
    m = len(env) // k
    return env[: m * k].reshape(m, k).mean(axis=1), fs / k


def _autocorr(env: np.ndarray, rate: float, max_lag_s: float) -> np.ndarray:
    k = max(1, round(rate / 1000))                     # 1ms로 뭉개서 비교
    s = np.convolve(env, np.ones(k) / k, mode="same")
    s = s - s.mean()
    f = np.fft.rfft(s, 2 * len(s))
    ac = np.fft.irfft(f * np.conj(f))[: int(max_lag_s * rate) + 2]
    return ac / ac[0]


def detect_bph(env: np.ndarray, rate: float, known_bph: int | None = None) -> tuple[int, float]:
    """박자와 신호 품질(박자 두 번 간격에서의 자기상관)을 돌려준다. 박자를 알면 판별은 건너뛴다."""
    ac = _autocorr(env, rate, 0.45)

    def peak(lag_s: float) -> float:
        c, w = round(lag_s * rate), max(2, round(lag_s * rate * 0.005))
        return float(ac[c - w : c + w + 1].max())

    if known_bph:
        return known_bph, peak(2 * 3600 / known_bph)
    scores = {}
    for bph in BPH_CANDIDATES:
        beat = 3600 / bph
        scores[bph] = (min(peak(beat), peak(2 * beat)), peak(2 * beat))
    best = max(s[0] for s in scores.values())
    # 36,000 시계는 18,000 후보의 간격에도 맞아떨어지므로, 비슷하면 빠른 박자를 고른다
    bph = max(b for b, s in scores.items() if s[0] >= 0.8 * best)
    return bph, scores[bph][1]


def _profile(env: np.ndarray, rate: float, period: float, nb: int) -> np.ndarray:
    t = np.arange(len(env)) / rate
    b = ((t % period) / period * nb).astype(np.int64)
    return np.bincount(b, weights=env, minlength=nb) / np.maximum(np.bincount(b, minlength=nb), 1)


def _best_ppm(env, rate, nominal, ppms) -> int:
    nb = round(nominal / FOLD_BIN_S)
    sharp = [np.var(_profile(env, rate, nominal * (1 + p * 1e-6), nb)) for p in ppms]
    return int(ppms[int(np.argmax(sharp))])


def measure_rate(env: np.ndarray, rate: float, bph: int, around: int | None = None) -> int:
    """기준 주기 대비 실제 주기 편차(ppm). `around`가 있으면 그 주변만 찾는다."""
    nominal = 2 * 3600 / bph
    if around is None:
        around = _best_ppm(env, rate, nominal, np.arange(-COARSE_PPM, COARSE_PPM + 1, COARSE_STEP))
    return _best_ppm(env, rate, nominal, np.arange(around - FINE_PPM, around + FINE_PPM + 1, FINE_STEP))


def beat_error_ms(env: np.ndarray, rate: float, bph: int, ppm: int) -> float:
    nominal = 2 * 3600 / bph
    nb = round(nominal / FOLD_BIN_S)
    prof = _profile(env, rate, nominal * (1 + ppm * 1e-6), nb)
    prof = np.convolve(np.tile(prof, 3), np.ones(5) / 5, mode="same")[nb : 2 * nb]
    i1 = int(prof.argmax())
    dist = (np.arange(nb) - i1) % nb
    rest = np.where((dist > nb // 4) & (dist < nb - nb // 4), prof, -np.inf)   # "째" 주변은 제외하고 "깍"을 찾는다
    spacing = ((int(rest.argmax()) - i1) % nb) * FOLD_BIN_S
    return abs(spacing - nominal / 2) * 1000


def analyze(path, known_bph: int | None = None) -> Result:
    x, fs = read_wav(path)
    env, rate = envelope(x, fs)
    bph, quality = detect_bph(env, rate, known_bph)
    if quality < MIN_QUALITY:
        return Result("failed", quality, reason="째깍 소리가 충분히 잡히지 않았습니다")
    ppm = measure_rate(env, rate, bph)
    half = len(env) // 2
    first = -measure_rate(env[:half], rate, bph, around=ppm) * PPM_TO_S_PER_DAY
    second = -measure_rate(env[half:], rate, bph, around=ppm) * PPM_TO_S_PER_DAY
    status = "low_confidence" if abs(first - second) > HALF_DIFF_LIMIT else "done"
    return Result(
        status, quality, bph,
        rate=-ppm * PPM_TO_S_PER_DAY,
        rate_first_half=first, rate_second_half=second,
        beat_error_ms=beat_error_ms(env, rate, bph, ppm),
        reason="녹음 앞뒤의 결과가 서로 다릅니다. 다시 측정해 주세요" if status == "low_confidence" else None,
    )
