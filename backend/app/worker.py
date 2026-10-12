"""SQS에서 분석 요청을 받아 녹음을 분석한다. 한 번에 한 건, 같은 메시지를 두 번 받아도 안전하다."""
import json
import logging
import os
import signal
import tempfile
import time
import uuid

from . import aws, config, logs, rules
from .analysis import InvalidAudio, analyze
from .models import Measurement, SessionLocal, now

log = logging.getLogger("watchlog.worker")
FINISHED = ("done", "low_confidence", "failed")
OUTLIER_REASON = "최근 측정들과 차이가 큽니다. 한 번 더 측정하면 확인됩니다"
_stop = False


def discard_audio(key: str) -> None:
    """분석이 끝난 녹음은 보관하지 않는다. 지우지 못해도 측정 결과에는 영향이 없고, 남은 파일은 버킷의 수명 주기 규칙이 정리한다."""
    try:
        aws.delete_objects([key])
    except Exception:
        log.exception("audio cleanup failed", extra={"key": key})


def process(measurement_id: str) -> None:
    """측정 한 건을 분석해 저장한다. 예외가 나가면 호출자는 메시지를 지우지 않는다(= 재시도)."""
    with SessionLocal() as s:
        m = s.get(Measurement, uuid.UUID(measurement_id))
        if m is None or m.status in FINISHED:
            log.info("skip", extra={"measurement_id": measurement_id, "status": m.status if m else "missing"})
            return
        m.status = "processing"
        s.commit()

        start = time.perf_counter()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            size = aws.object_size(m.audio_key)
            if size is None or size > config.MAX_AUDIO_BYTES:
                raise InvalidAudio("녹음 파일이 없거나 너무 큽니다")
            aws.download(m.audio_key, path)
            result = analyze(path, known_bph=m.watch.bph)
        except InvalidAudio as e:
            # 다시 해도 같은 결과이므로 실패로 확정한다
            m.status, m.error_reason, m.analyzed_at = "failed", str(e), now()
            s.commit()
            discard_audio(m.audio_key)
            log.info("analyzed", extra={"measurement_id": measurement_id, "status": "failed", "reason": str(e)})
            return
        finally:
            os.unlink(path)

        m.status, m.error_reason = result.status, result.reason
        m.quality, m.detected_bph = result.quality, result.bph
        if result.status != "failed":
            m.rate_s_per_day, m.beat_error_ms = result.rate, result.beat_error_ms
            m.rate_first_half, m.rate_second_half = result.rate_first_half, result.rate_second_half
            earlier = [x for x in m.watch.measurements if x.id != m.id and x.status in ("done", "low_confidence")]
            if result.status == "done" and rules.is_outlier(result.rate, [x.rate_s_per_day for x in earlier if x.status == "done"]):
                last = earlier[-1]
                if last.error_reason == OUTLIER_REASON and abs(result.rate - last.rate_s_per_day) <= rules.OUTLIER_LIMIT:
                    # 바로 앞 측정도 같은 값으로 튀었다면 측정 실수가 아니라 시계가 실제로 변한 것이다. 둘 다 반영한다.
                    # (이 규칙이 없으면 자성 등으로 일오차가 크게 변한 뒤의 측정이 영영 반영되지 않는다)
                    last.status, last.error_reason = "done", None
                else:
                    m.status, m.error_reason = "low_confidence", OUTLIER_REASON
            if m.watch.bph is None:
                m.watch.bph = result.bph
        m.analyzed_at = now()
        s.commit()
        discard_audio(m.audio_key)
        log.info("analyzed", extra={
            "measurement_id": measurement_id, "status": m.status, "quality": round(result.quality, 3),
            "rate": result.rate, "seconds": round(time.perf_counter() - start, 2),
        })


def run() -> None:
    logs.setup()
    busy = False

    def stop(*_):
        global _stop
        _stop = True
        if busy:
            log.info("stop requested; finishing current job")
        else:
            raise SystemExit(0)   # 메시지를 기다리는 중이면(최대 20초) 바로 끝낸다

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker started", extra={"queue": config.SQS_QUEUE_URL})
    try:
        while not _stop:
            try:
                messages = aws.sqs().receive_message(
                    QueueUrl=config.SQS_QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=20
                ).get("Messages", [])
            except Exception:
                log.exception("receive failed")
                time.sleep(5)
                continue
            for msg in messages:
                busy = True
                try:
                    process(json.loads(msg["Body"])["measurement_id"])
                except (KeyError, ValueError):
                    log.error("bad message dropped", extra={"body": msg["Body"][:200]})
                except Exception:
                    # 지우지 않으면 보이지 않는 시간이 지난 뒤 다시 전달된다. 재시도 한도는 큐 설정(격리 큐)이 맡는다
                    log.exception("processing failed; will retry")
                    continue
                finally:
                    busy = False
                aws.sqs().delete_message(QueueUrl=config.SQS_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
    finally:
        log.info("worker stopped")
