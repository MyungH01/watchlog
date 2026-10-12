import { useEffect, useRef, useState } from "react";
import { fmtRate, History } from "../api";

const W = 340, PAD = { l: 34, r: 10, t: 12, b: 22 };

/** 일오차 추이. 소리 측정은 황동색 점, 사진으로 잰 실제 착용 일오차는 흰 마름모. 반영하지 않은 측정은 그리지 않는다. */
export function Chart({ history }: { history: History }) {
  // 그래프가 놓인 칸의 가로세로 비율에 맞춰 그린다. 낮은 화면에서는 납작하게, 넓은 화면에서는 높게.
  const plot = useRef<HTMLDivElement>(null);
  const [H, setH] = useState(180);
  useEffect(() => {
    const el = plot.current;
    if (!el) return;
    const fit = () => el.clientWidth && setH(Math.max(70, Math.min(260, (W * el.clientHeight) / el.clientWidth)));
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const sound = history.measurements
    .filter((m) => m.rate != null && m.status === "done")
    .map((m) => ({ t: +new Date(m.created_at), rate: m.rate!, kind: "sound" }));
  const worn = history.worn_rates.map((w) => ({ t: +new Date(w.at), rate: w.rate, kind: "worn" }));
  const points = [...sound, ...worn].sort((a, b) => a.t - b.t);

  const t0 = points[0]?.t ?? 0, t1 = Math.max(points[points.length - 1]?.t ?? 0, t0 + 1);
  const span = Math.max(5, ...points.map((p) => Math.abs(p.rate))) * 1.15;   // 0을 가운데 두고 위아래 대칭
  const x = (t: number) => PAD.l + ((t - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (r: number) => PAD.t + ((span - r) / (2 * span)) * (H - PAD.t - PAD.b);
  const step = span > 30 ? 20 : span > 12 ? 10 : 5;
  const ticks: number[] = [];
  for (let v = -Math.floor(span / step) * step; v <= span; v += step) ticks.push(v);
  const line = sound.map((p) => `${x(p.t)},${y(p.rate)}`).join(" ");
  const day = (t: number) => new Date(t).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" });

  return (
    <figure className="chart">
      <div className="chart-plot" ref={plot}>
      {points.length === 0 ? <p className="chart-empty">측정하면 여기에 추이가 그려집니다.</p> : (
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="일오차 추이 그래프">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className={v === 0 ? "zero" : "grid"} />
            <text x={PAD.l - 6} y={y(v) + 3} textAnchor="end">{fmtRate(v, 0)}</text>
          </g>
        ))}
        <polyline points={line} className="trace" />
        {points.map((p, i) =>
          p.kind === "worn" ? (
            <rect key={i} x={x(p.t) - 3} y={y(p.rate) - 3} width="6" height="6" transform={`rotate(45 ${x(p.t)} ${y(p.rate)})`} className="worn" />
          ) : (
            <circle key={i} cx={x(p.t)} cy={y(p.rate)} r="3.2" className={p.kind} />
          ),
        )}
        <text x={PAD.l} y={H - 4}>{day(t0)}</text>
        {t1 - t0 > 86400000 && <text x={W - PAD.r} y={H - 4} textAnchor="end">{day(t1)}</text>}
      </svg>
      )}
      </div>
      <figcaption>
        <span><i className="key sound" /> 소리 측정</span>
        {worn.length > 0 && <span><i className="key worn" /> 실제 착용</span>}
        <span className="unit">초/일</span>
      </figcaption>
    </figure>
  );
}
