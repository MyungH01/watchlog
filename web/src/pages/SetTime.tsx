import { useEffect, useState } from "react";
import { api, ClockSync, syncClock, Watch } from "../api";
import { go } from "../App";

const R = 96, CIRC = 2 * Math.PI * R;
const ZONES_KEY = "wl_zones";
/** 세계시간 후보. GMT 시계의 두 번째 시간대로 자주 맞추는 곳들 */
const CITIES: [tz: string, name: string][] = [
  ["UTC", "협정 세계시 (UTC)"], ["Asia/Seoul", "서울"], ["Asia/Tokyo", "도쿄"], ["Asia/Shanghai", "베이징"],
  ["Asia/Hong_Kong", "홍콩"], ["Asia/Singapore", "싱가포르"], ["Asia/Bangkok", "방콕"], ["Asia/Dubai", "두바이"],
  ["Europe/Zurich", "취리히"], ["Europe/Paris", "파리"], ["Europe/London", "런던"], ["America/New_York", "뉴욕"],
  ["America/Chicago", "시카고"], ["America/Los_Angeles", "로스앤젤레스"], ["Pacific/Honolulu", "호놀룰루"],
  ["Australia/Sydney", "시드니"],
];

const clock = (ms: number, timeZone?: string) =>
  new Intl.DateTimeFormat("ko-KR", { timeZone, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(ms);
const day = (ms: number, timeZone?: string) =>
  new Intl.DateTimeFormat("ko-KR", { timeZone, month: "short", day: "numeric", weekday: "short" }).format(ms);

// 고른 도시는 이 브라우저에만 둔다. 사라져도 다시 고르면 되는 값이라 서버에 저장하지 않는다
function loadZones(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(ZONES_KEY) ?? "");
    if (Array.isArray(saved)) return saved.filter((z) => CITIES.some(([tz]) => tz === z));
  } catch { /* 저장된 값이 없거나 저장소를 쓸 수 없는 브라우저 */ }
  return ["UTC"];
}

/** 시간 맞추기: 핸드폰 시계가 아니라 서버 시계(사진 기록과 같은 기준)의 현재 시각을 보여 준다. */
export function SetTime() {
  const [sync, setSync] = useState<ClockSync | null>(null);
  const [failed, setFailed] = useState(false);
  const [zones, setZones] = useState(loadZones);
  const [watches, setWatches] = useState<Watch[]>([]);
  const [, setBeat] = useState(0);

  // 화면으로 돌아올 때마다 다시 맞춘다. 잠들어 있던 사이 기기 시계가 보정됐을 수 있다
  useEffect(() => {
    const run = () => {
      if (!document.hidden) syncClock().then((s) => { setSync(s); setFailed(false); }, () => setFailed(true));
    };
    run();
    document.addEventListener("visibilitychange", run);
    return () => document.removeEventListener("visibilitychange", run);
  }, []);

  // 초가 바뀌는 순간에 맞춰 다시 그린다
  useEffect(() => {
    const offset = sync?.offsetMs ?? 0;
    let timer = 0;
    const tick = () => { setBeat((b) => b + 1); timer = window.setTimeout(tick, 1000 - ((Date.now() + offset) % 1000)); };
    tick();
    return () => clearTimeout(timer);
  }, [sync]);

  useEffect(() => { api.watches().then(setWatches, () => undefined); }, []);

  function saveZones(next: string[]) {
    setZones(next);
    try { localStorage.setItem(ZONES_KEY, JSON.stringify(next)); } catch { /* 저장하지 못해도 이번 화면에서는 보인다 */ }
  }

  const now = Date.now() + (sync?.offsetMs ?? 0);
  const sec = Math.floor(now / 1000) % 60;
  const nextMinute = (Math.floor(now / 60000) + 1) * 60000;
  const behind = sync ? sync.offsetMs / 1000 : 0;   // 양수면 이 기기 시계가 느리다
  const rest = CITIES.filter(([tz]) => !zones.includes(tz));

  return (
    <>
      <div className="meter">
        <div className="ring">
          <svg viewBox="-110 -110 220 220" aria-hidden="true">
            <circle r={R} className="ring-bg" />
            <circle r={R} className="ring-fg" transform="rotate(-90)" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - sec / 60)} />
          </svg>
          <div className="ring-center">
            <b className="now">{clock(now)}</b>
            <small>{day(now)}</small>
          </div>
        </div>
        <p className="detect on">{60 - sec}초 뒤 {clock(nextMinute)}</p>
      </div>

      {failed ? (
        <p className="notice warn">서버 시각을 가져오지 못해 이 기기의 시계로 표시합니다.</p>
      ) : sync && (
        <p className="sub" role="status">
          {Math.abs(behind) < 0.1
            ? "이 기기의 시계와 0.1초 안에서 일치합니다."
            : `이 기기의 시계는 ${Math.abs(behind).toFixed(1)}초 ${behind > 0 ? "느립니다" : "빠릅니다"}.`}
          {" "}위 시각은 서버 시계 기준이고 오차는 약 ±{(Math.max(sync.errorMs, 10) / 1000).toFixed(2)}초입니다.
        </p>
      )}

      <section className="panel">
        <h2>맞추는 방법</h2>
        <ol className="steps">
          <li>초침이 12시에 올 때 용두를 뽑아 초침을 멈춥니다.</li>
          <li>분침을 위에 표시된 <b>다음 분</b>에 맞춥니다.</li>
          <li>남은 초가 0이 되는 순간 용두를 누릅니다.</li>
        </ol>
      </section>

      <section className="panel">
        <h2>세계시간</h2>
        <ul className="zones">
          {zones.map((tz) => {
            const name = CITIES.find(([z]) => z === tz)![1];
            return (
              <li key={tz}>
                <span>{name}<small>{day(now, tz)}</small></span>
                <b>{clock(now, tz)}</b>
                <button className="x" aria-label={`${name} 빼기`} onClick={() => saveZones(zones.filter((z) => z !== tz))}>×</button>
              </li>
            );
          })}
        </ul>
        {rest.length > 0 && (
          <select aria-label="도시 추가" value="" onChange={(e) => e.target.value && saveZones([...zones, e.target.value])}>
            <option value="">도시 추가</option>
            {rest.map(([tz, name]) => <option key={tz} value={tz}>{name}</option>)}
          </select>
        )}
      </section>

      {watches.length > 0 && (
        <section className="panel">
          <h2>시간을 맞췄다면</h2>
          <p className="sub">맞춘 직후의 시계를 사진으로 기록해 두면, 여기서부터 실제 착용 일오차를 새로 계산합니다.</p>
          {watches.map((w) => (
            <button key={w.id} className="ghost wide" onClick={() => go(`/watch/${w.id}/photo/reset`)}>{w.name} 기록하기</button>
          ))}
        </section>
      )}
    </>
  );
}
