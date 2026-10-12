from datetime import datetime, timezone
from pathlib import Path

from app import worker

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def make_watch(client, **extra):
    r = client.post("/api/watches", json={"name": "Carrera", "bph": 28800, **extra})
    assert r.status_code == 201
    return r.json()["id"]


def measure(client, fake_aws, watch_id, fixture):
    """브라우저가 하는 일(측정 생성 → 업로드 → 완료 알림)과 워커 한 번을 흉내 낸다."""
    m = client.post(f"/api/watches/{watch_id}/measurements").json()
    fake_aws.objects[m["upload"]["fields"]["key"]] = str(FIXTURES / fixture)
    assert client.post(f"/api/measurements/{m['id']}/uploaded").json()["status"] == "queued"
    worker.process(fake_aws.queue[-1])
    return client.get(f"/api/measurements/{m['id']}").json()


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_requests_without_session_are_rejected(client):
    client.cookies.clear()
    assert client.get("/api/watches").status_code == 401


def test_watch_collection(client):
    a, b = make_watch(client), make_watch(client, name="Seiko 5", bph=21600)
    assert [w["id"] for w in client.get("/api/watches").json()] == [a, b]
    assert client.patch(f"/api/watches/{a}", json={"model": "WBN2111"}).json()["model"] == "WBN2111"
    assert client.post("/api/watches", json={"name": "x", "bph": 12345}).status_code == 422
    assert client.delete(f"/api/watches/{a}").status_code == 200
    assert len(client.get("/api/watches").json()) == 1


def test_other_users_cannot_touch_my_data(client, other_client, fake_aws):
    watch = make_watch(client)
    m = client.post(f"/api/watches/{watch}/measurements").json()
    reading = client.post(f"/api/watches/{watch}/readings", json=reading_body(utc_seconds_of_day())).json()
    assert other_client.get("/api/watches").json() == []
    for method, url in [
        ("get", f"/api/watches/{watch}"), ("patch", f"/api/watches/{watch}"), ("delete", f"/api/watches/{watch}"),
        ("get", f"/api/watches/{watch}/history"), ("post", f"/api/watches/{watch}/measurements"),
        ("get", f"/api/measurements/{m['id']}"), ("post", f"/api/measurements/{m['id']}/uploaded"),
        ("delete", f"/api/measurements/{m['id']}"), ("delete", f"/api/readings/{reading['id']}"),
        ("post", f"/api/watches/{watch}/readings"),
    ]:
        kwargs = {"json": reading_body(0)} if url.endswith("/readings") else {"json": {}} if method == "patch" else {}
        assert getattr(other_client, method)(url, **kwargs).status_code == 404, url


def test_photo_key_must_be_the_one_we_issued(client):
    watch = make_watch(client)
    issued = client.post(f"/api/watches/{watch}/photo-url", json={"content_type": "image/jpeg"}).json()
    assert client.patch(f"/api/watches/{watch}", json={"photo_key": "photos/someone-else/x.jpg"}).status_code == 400
    assert client.patch(f"/api/watches/{watch}", json={"photo_key": issued["photo_key"]}).json()["photo_url"]
    assert client.post(f"/api/watches/{watch}/photo-url", json={"content_type": "text/html"}).status_code == 400


def reading_body(shown, **extra):
    return {"shown_seconds": shown, "elapsed_ms": 0, "tz_offset_minutes": 0, **extra}


def utc_seconds_of_day():
    t = datetime.now(timezone.utc)
    return t.hour * 3600 + t.minute * 60 + t.second


def test_photo_reading_records_how_far_ahead_the_watch_is(client, fake_aws):
    watch = make_watch(client)
    shown = (utc_seconds_of_day() + 12) % 86400                      # 사진 속 시계가 12초 앞서 있다
    r = client.post(f"/api/watches/{watch}/readings", json=reading_body(shown))
    assert r.status_code == 201 and abs(r.json()["offset_seconds"] - 12) <= 1.5
    assert r.json()["upload"]["fields"]["key"].startswith("photos/")
    # 한국 시간(UTC+9)으로 본 시각을 입력해도 같은 결과여야 한다
    kst = client.post(f"/api/watches/{watch}/readings",
                      json=reading_body((shown + 9 * 3600) % 86400, tz_offset_minutes=-540, with_photo=False)).json()
    assert abs(kst["offset_seconds"] - 12) <= 1.5 and kst["upload"] is None
    # 10초 전에 찍은 사진이면 그만큼 시계가 더 앞서 있던 것이다
    late = client.post(f"/api/watches/{watch}/readings", json=reading_body(shown, elapsed_ms=10_000)).json()
    assert abs(late["offset_seconds"] - 22) <= 1.5

    h = client.get(f"/api/watches/{watch}/history").json()
    assert len(h["readings"]) == 3 and h["worn_rates"] == [] and h["summary"]["worn_rate"] is None
    assert h["readings"][0]["photo_url"]
    assert client.delete(f"/api/readings/{h['readings'][0]['id']}").status_code == 200
    assert fake_aws.deleted


def test_photo_reading_rejects_an_implausible_time(client):
    watch = make_watch(client)
    wrong = (utc_seconds_of_day() + 3 * 3600) % 86400                # 세 시간 틀린 입력
    assert client.post(f"/api/watches/{watch}/readings", json=reading_body(wrong)).status_code == 422


def test_measurement_flow(client, fake_aws):
    watch = make_watch(client, bph=None)
    m = client.post(f"/api/watches/{watch}/measurements").json()
    assert client.post(f"/api/measurements/{m['id']}/uploaded").status_code == 400   # 아직 파일이 없다
    done = measure(client, fake_aws, watch, "rec3.wav")
    assert done["status"] == "done" and abs(done["rate"] - 5.5) < 1.0
    assert m["upload"]["fields"]["key"].replace(m["id"], done["id"]) in fake_aws.deleted   # 분석이 끝난 녹음은 바로 지운다
    w = client.get(f"/api/watches/{watch}").json()
    assert w["bph"] == 28800                 # "모름"으로 등록한 박자가 첫 측정으로 채워진다
    assert abs(w["representative_rate"] - 5.5) < 1.0


def test_worker_handles_duplicate_messages(client, fake_aws):
    watch = make_watch(client)
    done = measure(client, fake_aws, watch, "rec3.wav")
    fake_aws.objects.clear()                 # 두 번째 처리에서 파일을 다시 읽으려 하면 실패한다
    worker.process(done["id"])
    assert client.get(f"/api/measurements/{done['id']}").json() == done
    worker.process("00000000-0000-0000-0000-000000000000")   # 지워진 측정의 메시지도 조용히 넘어간다


def test_broken_audio_is_marked_failed(client, fake_aws, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    watch = make_watch(client)
    m = client.post(f"/api/watches/{watch}/measurements").json()
    fake_aws.objects[m["upload"]["fields"]["key"]] = str(bad)
    client.post(f"/api/measurements/{m['id']}/uploaded")
    worker.process(m["id"])
    assert client.get(f"/api/measurements/{m['id']}").json()["status"] == "failed"


def test_weak_recording_is_low_confidence_after_good_ones(client, fake_aws):
    watch = make_watch(client)
    for name in ("rec2.wav", "rec3.wav", "rec4.wav"):
        assert measure(client, fake_aws, watch, name)["status"] == "done"
    weak = measure(client, fake_aws, watch, "rec1_weak_signal.wav")
    assert weak["status"] == "low_confidence"
    rep = client.get(f"/api/watches/{watch}").json()["representative_rate"]
    assert abs(rep - 7.0) < 1.0              # 반영하지 않은 측정은 대표값에 들어가지 않는다


def test_a_repeated_jump_is_accepted_as_a_real_change(client, fake_aws):
    watch = make_watch(client)
    for name in ("rec2.wav", "rec3.wav", "rec4.wav"):
        measure(client, fake_aws, watch, name)
    first = measure(client, fake_aws, watch, "rec1_weak_signal.wav")
    assert first["status"] == "low_confidence"
    second = measure(client, fake_aws, watch, "rec1_weak_signal.wav")      # 다시 재도 같은 값이 나왔다
    assert second["status"] == "done"
    assert client.get(f"/api/measurements/{first['id']}").json()["status"] == "done"   # 앞의 측정도 함께 반영된다


def test_deleting_removes_files(client, fake_aws):
    watch = make_watch(client)
    m = client.post(f"/api/watches/{watch}/measurements").json()
    assert client.delete("/api/me").status_code == 200
    assert m["upload"]["fields"]["key"] in fake_aws.deleted
    assert client.get("/api/watches").status_code == 401
