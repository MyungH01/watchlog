import { useEffect, useRef, useState } from "react";
import { api, fmtRate } from "../api";
import { go } from "../App";

const HALF_DIAL = 6 * 3600;
/** 시계가 실제보다 몇 초 앞서 있는지. 12시간 다이얼이라 오전·오후는 가리지 않는다 (서버의 dial_offset과 같은 계산) */
const dialOffset = (shown: number, real: number) =>
  ((((shown - real + HALF_DIAL) % (2 * HALF_DIAL)) + 2 * HALF_DIAL) % (2 * HALF_DIAL)) - HALF_DIAL;

/** 사진으로 기록: 셔터를 누른 순간의 실제 시각은 서비스가 기억하고, 사용자는 멈춘 사진에서 시계 시각만 읽어 적는다. */
export function PhotoReading({ watchId, reset: startReset = false }: { watchId: string; reset?: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [shot, setShot] = useState<{ at: number; blob: Blob; url: string } | null>(null);
  const [h, setH] = useState("");
  const [m, setM] = useState("");
  const [s, setS] = useState("");
  const [reset, setReset] = useState(startReset);   // 시간 맞추기 화면에서 넘어오면 미리 체크돼 있다
  const [zoom, setZoom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastOffset, setLastOffset] = useState<number | null>(null);

  // 직전 기록과 비교해서, 시간을 다시 맞추고 체크를 잊은 경우를 알려 주기 위해 불러온다
  useEffect(() => {
    api.history(watchId).then((h) => setLastOffset(h.readings[h.readings.length - 1]?.offset_seconds ?? null), () => undefined);
  }, [watchId]);

  const stopCamera = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; };

  async function startCamera() {
    setError(""); setShot(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false,
      });
      if (video.current) video.current.srcObject = stream.current;
    } catch {
      setError("카메라를 사용할 수 없습니다. 브라우저 설정에서 카메라 권한을 허용해 주세요.");
    }
  }

  useEffect(() => { void startCamera(); return stopCamera; }, []);

  function shoot() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const at = Date.now();                      // 이 순간이 기준 시각이 된다
    const scale = Math.min(1, 1600 / v.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth * scale;
    canvas.height = v.videoHeight * scale;
    canvas.getContext("2d")!.drawImage(v, 0, 0, canvas.width, canvas.height);
    stopCamera();
    canvas.toBlob((blob) => {
      if (!blob) return setError("사진을 저장하지 못했습니다. 다시 찍어 주세요.");
      const t = new Date(at);
      setH(String(t.getHours())); setM(String(t.getMinutes())); setS(String(t.getSeconds()));
      setShot({ at, blob, url: URL.createObjectURL(blob) });
    }, "image/jpeg", 0.85);
  }

  const shown = (Number(h) * 3600 + Number(m) * 60 + Number(s)) % 86400;
  const real = shot ? (() => { const t = new Date(shot.at); return t.getHours() * 3600 + t.getMinutes() * 60 + t.getSeconds() + t.getMilliseconds() / 1000; })() : 0;
  const offset = shot ? dialOffset(shown, real) : 0;
  const implausible = Math.abs(offset) > 30 * 60;
  // 오차는 보통 0에서 멀어지는 쪽으로 쌓인다. 지난번보다 0에 확 가까워졌다면 그 사이에 시간을 맞췄을 가능성이 크다
  const looksReset = !reset && lastOffset != null && Math.abs(offset) + 10 < Math.abs(lastOffset);

  async function save() {
    if (!shot) return;
    setBusy(true); setError("");
    try {
      await api.addReading(watchId, {
        shown_seconds: shown, elapsed_ms: Date.now() - shot.at,
        tz_offset_minutes: new Date().getTimezoneOffset(), reset,
      }, shot.blob);
      go(`/watch/${watchId}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <header className="top">
        <button className="ghost" onClick={() => go(`/watch/${watchId}`)}>← 뒤로</button>
        <h1>사진으로 기록</h1>
      </header>

      {error && <p className="notice bad">{error}</p>}

      {!shot ? (
        <>
          <div className="finder">
            <video ref={video} autoPlay playsInline muted />
            <div className="finder-ring" aria-hidden="true" />
          </div>
          <p className="sub">초침이 또렷하게 보이도록 다이얼을 원 안에 맞추고 찍으세요. 찍는 순간의 실제 시각은 자동으로 기록됩니다.</p>
          <button className="primary wide" onClick={shoot}>찍기</button>
        </>
      ) : (
        <>
          <div className={zoom ? "frozen zoom" : "frozen"} onClick={() => setZoom(!zoom)}>
            <img src={shot.url} alt="방금 찍은 시계 사진" />
          </div>
          <p className="sub">사진을 누르면 확대됩니다. <b>사진 속 시계가 가리키는 시각</b>을 적어 주세요. 대개 초만 고치면 됩니다.</p>
          <div className="clock-input">
            <label>시<input id="read-h" type="number" inputMode="numeric" min="0" max="23" value={h} onChange={(e) => setH(e.target.value)} /></label>
            <label>분<input id="read-m" type="number" inputMode="numeric" min="0" max="59" value={m} onChange={(e) => setM(e.target.value)} /></label>
            <label>초<input id="read-s" type="number" inputMode="numeric" min="0" max="59" value={s} onChange={(e) => setS(e.target.value)} /></label>
          </div>
          <p className={implausible ? "notice bad" : "notice ok"} role="status">
            {implausible
              ? "실제 시각과 30분 넘게 차이 납니다. 시와 분을 다시 확인해 주세요."
              : `찍은 순간 시계는 실제보다 ${fmtRate(offset, 0)}초 ${offset >= 0 ? "앞서" : "늦게"} 있었습니다.`}
          </p>
          {looksReset && !implausible && (
            <p className="notice warn">
              지난 기록({fmtRate(lastOffset, 0)}초)보다 실제 시각에 가까워졌습니다. 그 사이에 시계를 다시 맞췄다면 아래를 체크해 주세요.
              체크하지 않으면 일오차가 크게 틀리게 계산됩니다.
            </p>
          )}
          <label className="check">
            <input id="read-reset" type="checkbox" checked={reset} onChange={(e) => setReset(e.target.checked)} />
            방금 시계 시간을 다시 맞췄어요 (여기서부터 새로 측정합니다)
          </label>
          <button className="primary wide" disabled={busy || implausible} onClick={save}>{busy ? "저장하는 중" : "저장"}</button>
          <button className="ghost wide" onClick={startCamera}>다시 찍기</button>
        </>
      )}
    </>
  );
}
