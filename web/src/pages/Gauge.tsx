import { fmtRate } from "../api";

const W = 340, H = 62, PAD = 14, Y = 30;
const CHRONOMETER: [number, number] = [-4, 6];   // 크로노미터 인증 기준 (초/일)
const OVERHAUL = 20;                             // 점검 기준
const UNCERTAINTY = 2;                           // 한 번의 측정이 흔들리는 폭

/** 일오차가 기준들 사이 어디쯤인지 보여 주는 눈금. "좋음" 같은 판정 대신 위치를 보여 준다. */
export function Gauge({ rate }: { rate: number }) {
  const limit = Math.abs(rate) > 28 ? 60 : 30;   // 범위를 벗어난 시계는 눈금을 넓힌다
  const x = (v: number) => PAD + ((Math.max(-limit, Math.min(limit, v)) + limit) / (2 * limit)) * (W - 2 * PAD);
  const step = limit / 6;
  const ticks = Array.from({ length: 13 }, (_, i) => -limit + i * step);

  return (
    <figure className="gauge">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`일오차 ${fmtRate(rate)}초. 점검 기준은 ±${OVERHAUL}초`}>
        <rect x={x(CHRONOMETER[0])} width={x(CHRONOMETER[1]) - x(CHRONOMETER[0])} y={Y - 9} height="18" className="band" />
        <line x1={x(-limit)} x2={x(limit)} y1={Y} y2={Y} className="axis" />
        {ticks.map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1={Y - (v % (step * 2) ? 3 : 6)} y2={Y + (v % (step * 2) ? 3 : 6)} className="axis" />
            {v % (step * 2) === 0 && <text x={x(v)} y={H - 4} textAnchor="middle">{fmtRate(v, 0)}</text>}
          </g>
        ))}
        {[-OVERHAUL, OVERHAUL].map((v) => <line key={v} x1={x(v)} x2={x(v)} y1={Y - 14} y2={Y + 14} className="limit" />)}
        <line x1={x(rate - UNCERTAINTY)} x2={x(rate + UNCERTAINTY)} y1={Y} y2={Y} className="range" />
        <path d={`M${x(rate)},${Y - 7} l5,-9 h-10 z`} className="marker" />
      </svg>
      <figcaption>
        <span><i className="key band" /> 크로노미터 기준</span>
        <span><i className="key limit" /> 점검 기준 ±{OVERHAUL}초</span>
        <span><i className="key range" /> 측정 오차 범위</span>
      </figcaption>
    </figure>
  );
}
