"""배포된 서비스가 끝까지 동작하는지 확인한다: 세션 → 시계 등록 → 녹음 업로드 → 큐 → 워커 → 결과.

사용법: python scripts/smoke.py [기본 주소] [WAV 파일]
        기본값은 http://localhost:8000 과 fixtures/rec3.wav (기준 일오차 +5.5초/일)
끝나면 만든 사용자와 파일을 지운다.
"""
import sys
import time
from pathlib import Path

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
wav = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[2] / "fixtures" / "rec3.wav"

with httpx.Client(base_url=base, timeout=30) as c:
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/ready").status_code == 200, "DB 연결 실패"
    c.post("/api/session").raise_for_status()
    watch = c.post("/api/watches", json={"name": "smoke test", "bph": 28800}).json()
    m = c.post(f"/api/watches/{watch['id']}/measurements").json()

    upload = m["upload"]
    r = httpx.post(upload["url"], data=upload["fields"], files={"file": ("rec.wav", wav.read_bytes(), "audio/wav")})
    assert r.status_code in (200, 204), f"S3 업로드 실패: {r.status_code} {r.text[:200]}"

    c.post(f"/api/measurements/{m['id']}/uploaded").raise_for_status()
    start = time.time()
    while True:
        result = c.get(f"/api/measurements/{m['id']}").json()
        if result["status"] in ("done", "low_confidence", "failed"):
            break
        assert time.time() - start < 180, f"3분 안에 분석이 끝나지 않았습니다 (상태: {result['status']})"
        time.sleep(2)
    print(f"status={result['status']} rate={result['rate']} quality={result['quality']} "
          f"bph={result['detected_bph']} ({time.time() - start:.0f}초)")
    c.delete("/api/me").raise_for_status()
    assert result["status"] == "done", result
print("OK")
