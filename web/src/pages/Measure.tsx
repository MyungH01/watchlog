import { useEffect, useRef, useState } from "react";
import { api, fmtRate, Measurement } from "../api";
import { go } from "../App";
import { Recorder, RecorderState, startRecorder, TARGET_SECONDS } from "../recorder";

type Phase = "idle" | "recording" | "uploading" | "analyzing" | "result" | "error";
const R = 96, CIRC = 2 * Math.PI * R;
const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);

export function Measure({ watchId }: { watchId: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [rec, setRec] = useState<RecorderState | null>(null);
  const [result, setResult] = useState<Measurement | null>(null);
  const [error, setError] = useState("");
  const recorder = useRef<Recorder | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const alive = useRef(true);

  useEffect(() => () => { alive.current = false; recorder.current?.cancel(); }, []);

  // 최근 2초의 포락선을 타임그래퍼 기록지처럼 그린다
  useEffect(() => {
    const c = canvas.current;
    if (!c || !rec) return;
    const g = c.getContext("2d")!;
    g.clearRect(0, 0, c.width, c.height);
    const max = Math.max(...rec.bins, 1e-9);
    g.fillStyle = rec.detected ? "#ffd166" : "rgba(255,255,255,0.35)";
    rec.bins.forEach((b, i) => {
      const hgt = (b / max) * c.height;
      g.fillRect((i / 2000) * c.width, c.height - hgt, 1, hgt);
    });
  }, [rec]);

  async function submit(wav: Blob) {
    setPhase("uploading");
    try {
      const id = await api.submitRecording(watchId, wav);
      setPhase("analyzing");
      while (alive.current) {
        const m = await api.measurement(id);
        if (["done", "low_confidence", "failed"].includes(m.status)) { setResult(m); setPhase("result"); return; }
        await new Promise((r) => setTimeout(r, 2000));
      }
    } catch (e) { fail((e as Error).message); }
  }

  function fail(message: string) { setError(message); setPhase("error"); }

  async function start() {
    setError(""); setRec(null);
    try {
      recorder.current = await startRecorder((s) => alive.current && setRec(s));
    } catch {
      return fail("마이크를 사용할 수 없습니다. 브라우저 설정에서 마이크 권한을 허용해 주세요.");
    }
    setPhase("recording");
    recorder.current.done.then(submit, () =>
      alive.current && fail("3분 안에 째깍 소리를 충분히 모으지 못했습니다. 더 조용한 곳에서 마이크 위치를 바꿔 다시 해 보세요."));
  }

  const progress = rec?.progress ?? 0;
  // 한 번이라도 진행됐다가 0으로 돌아갔다면 소리가 끊겨 다시 시작한 것이다
  const everProgressed = useRef(false);
  if (phase === "recording" && progress > 0.05) everProgressed.current = true;
  if (phase !== "recording") everProgressed.current = false;
  const restarted = everProgressed.current;

  return (
    <>
      <header className="top">
        <button className="ghost" onClick={() => go(`/watch/${watchId}`)}>← 뒤로</button>
        <h1>소리로 측정</h1>
      </header>

      {(phase === "idle" || phase === "error") && (
        <section className="panel">
          {error && <p className="notice bad">{error}</p>}
          <ol className="steps">
            <li>조용한 곳에서 핸드폰을 책상 위에 올려 둡니다.</li>
            <li>시계 뒷면을 핸드폰 하단의 마이크에 밀착시킵니다. 아이폰은 충전 단자 <b>왼쪽</b> 구멍입니다.</li>
            <li>째깍 소리가 감지되면 진행 원이 채워집니다. {TARGET_SECONDS}초 동안 그대로 유지해 주세요.</li>
          </ol>
          <p className="sub">어디가 마이크인지 모르겠으면, 측정을 시작한 뒤 손톱으로 구멍 주변을 긁어 보세요. 아래 기록선이 크게 튀는 곳입니다.</p>
          <button className="primary wide" onClick={start}>측정 시작</button>
          {isLocal && (
            <label className="devfile">개발용: WAV 파일로 측정
              <input id="dev-wav" type="file" accept=".wav,audio/wav" onChange={(e) => e.target.files?.[0] && submit(e.target.files[0])} />
            </label>
          )}
        </section>
      )}

      {phase === "recording" && (
        <section className="meter">
          <div className="ring">
            <svg viewBox="-110 -110 220 220" aria-hidden="true">
              {Array.from({ length: 60 }, (_, i) => (
                <line key={i} y1="-108" y2={i % 5 ? -104 : -100} transform={`rotate(${i * 6})`} className="tick" />
              ))}
              <circle r={R} className="ring-bg" />
              <circle r={R} className="ring-fg" transform="rotate(-90)" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - progress)} />
            </svg>
            <div className="ring-center">
              <b>{Math.round(progress * TARGET_SECONDS)}</b>
              <small>/ {TARGET_SECONDS}초</small>
            </div>
          </div>
          <p className={`detect ${rec?.detected ? "on" : "off"}`} role="status">
            {rec?.detected
              ? `째깍 감지됨, 초당 약 ${rec.beatsPerSecond.toFixed(0)}회`
              : restarted && progress === 0
                ? "소리가 끊겨 처음부터 다시 측정합니다. 시계를 마이크에 더 가까이 대 주세요"
                : "시계를 마이크에 더 가까이 대 주세요"}
          </p>
          <canvas ref={canvas} width={1000} height={160} className="tape" />
          <button className="ghost wide" onClick={() => { recorder.current?.cancel(); setPhase("idle"); }}>취소</button>
        </section>
      )}

      {(phase === "uploading" || phase === "analyzing") && (
        <section className="meter">
          <div className="ring busy"><svg viewBox="-110 -110 220 220" aria-hidden="true"><circle r={R} className="ring-fg spin" strokeDasharray={`${CIRC / 4} ${CIRC}`} /></svg></div>
          <p className="detect on" role="status">{phase === "uploading" ? "녹음을 올리는 중" : "분석 중입니다. 보통 30초쯤 걸립니다."}</p>
        </section>
      )}

      {phase === "result" && result && (
        <section className="reading result">
          {result.status === "failed" ? (
            <>
              <p className="reading-label">측정하지 못했습니다</p>
              <p className="notice bad">{result.error_reason}</p>
            </>
          ) : result.status === "low_confidence" ? (
            <>
              <p className="reading-label">한 번 더 측정해 주세요</p>
              <p className="notice warn">{result.error_reason}</p>
              <p className="footnote">이번 값 {fmtRate(result.rate)}초/일은 일오차와 그래프에 반영하지 않았습니다.</p>
            </>
          ) : (
            <>
              <p className="reading-label">이번 측정</p>
              <p className="reading-value">{fmtRate(result.rate)}<small> 초/일 (±2)</small></p>
              <dl className="facts">
                <div><dt>박자</dt><dd>{result.detected_bph?.toLocaleString()}회/시간</dd></div>
                <div><dt>비트 에러</dt><dd>{result.beat_error_ms?.toFixed(1)}ms</dd></div>
                <div><dt>신호 품질</dt><dd>{result.quality?.toFixed(2)}</dd></div>
              </dl>
              <p className="footnote">이 자세에서 측정한 순간의 값이며, 핸드폰 자체의 시간 오차가 섞인 참고값입니다.</p>
            </>
          )}
          <button className="primary wide" onClick={() => setPhase("idle")}>다시 측정</button>
          <button className="ghost wide" onClick={() => go(`/watch/${watchId}`)}>기록 보기</button>
        </section>
      )}
    </>
  );
}
