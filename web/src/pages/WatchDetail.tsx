import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, fmtRate, History, Measurement, Reading } from "../api";
import { go } from "../App";
import { Chart } from "./Chart";
import { Dial } from "./Collection";
import { Gauge } from "./Gauge";

const STATUS_LABEL: Record<string, string> = {
  queued: "분석 대기", processing: "분석 중", done: "", low_confidence: "미반영", failed: "측정 실패",
};
const TABS = [["chart", "추이"], ["gauge", "기준"], ["log", "기록"]] as const;
type Tab = (typeof TABS)[number][0];
type Row = { id: string; at: string; m?: Measurement; r?: Reading };

/** 한 화면에 들어오는 시계 상세: 사진, 일오차와 요약, 탭(추이·기준·기록), 측정 버튼. 스크롤은 기록 탭 안에서만 생긴다. */
export function WatchDetail({ watchId }: { watchId: string }) {
  const [h, setH] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("chart");

  const load = useCallback(() => api.history(watchId).then(setH, (e) => setError(e.message)), [watchId]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <><Back /><p className="notice bad">{error}</p></>;
  if (!h) return <p className="loading">불러오는 중</p>;
  const { watch: w, summary: sum } = h;
  const rows: Row[] = [
    ...h.measurements.map((m) => ({ id: m.id, at: m.created_at, m })),
    ...h.readings.map((r) => ({ id: r.id, at: r.taken_at, r })),
  ];
  rows.sort((a, b) => +new Date(b.at) - +new Date(a.at));   // 최근 것부터

  return (
    <>
      <header className="top">
        <Back />
        <button className="ghost" onClick={() => go(`/watch/${watchId}/edit`)}>수정</button>
      </header>

      {/* 올린 사진을 흐리게 해서 화면 전체의 배경으로 깔고, 같은 사진을 위쪽에 크게 놓는다 */}
      {w.photo_url && <div className="backdrop" style={{ backgroundImage: `url("${w.photo_url}")` }} />}
      <section className="hero">
        <div className="hero-art">
          {w.photo_url ? <img className="hero-photo" src={w.photo_url} alt={`${w.name} 사진`} /> : <Dial size={170} />}
        </div>
        <div className="hero-name">
          <h1>{w.name}</h1>
          <p className="sub">{[[w.brand, w.model].filter(Boolean).join(" "), w.bph && `${w.bph.toLocaleString()}회/시간`].filter(Boolean).join(" · ")}</p>
        </div>
      </section>

      <section className="sheet">
        {/* 소리 측정과 실제 착용은 재는 대상이 달라서(한 자세의 순간값 / 며칠간 찬 결과) 이름을 붙여 나란히 보여 준다 */}
        <div className="headline">
          <div>
            <p className="reading-label">소리 측정</p>
            <p className="reading-value">{fmtRate(sum.rate)}<small> 초/일{sum.rate != null && " (±2)"}</small></p>
          </div>
          <div className="worn">
            <p className="reading-label">실제 착용</p>
            <p className="worn-value">{fmtRate(sum.worn_rate)}<small> 초/일</small></p>
          </div>
        </div>
        <p className={`status ${sum.status}`}>{sum.sentence}</p>

        <nav className="tabs" role="tablist">
          {TABS.map(([key, label]) => (
            <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
              {label}{key === "log" && rows.length > 0 && ` ${rows.length}`}
            </button>
          ))}
        </nav>

        <div className={`tab-body ${tab}`} role="tabpanel">
          {tab === "chart" && <Chart history={h} />}

          {tab === "gauge" && (sum.rate == null ? (
            <p className="chart-empty">소리로 측정하면 기준과 비교해 보여 드립니다.</p>
          ) : (
            <>
              <Gauge rate={sum.rate} />
              <p className="footnote">
                소리 측정은 그 자세에서 측정한 순간값이고 핸드폰 자체의 시간 오차가 섞여 있습니다.
                {sum.spread != null && ` 최근 ${Math.min(5, sum.count)}회의 흔들림은 ±${sum.spread.toFixed(1)}초입니다.`}
                {sum.status === "trending" && " 변화 예상은 지금까지의 추세가 그대로 이어진다고 가정한 참고값입니다."}
              </p>
            </>
          ))}

          {tab === "log" && (rows.length === 0 ? (
            <p className="chart-empty">아직 기록이 없습니다.</p>
          ) : (
            <ul className="log">
              {rows.map(({ id, at, m, r }) => (
                <li key={id}>
                  <span className="log-when">{fmtDate(at)}<small>{m ? "소리" : "사진"}</small></span>
                  {m ? (
                    <span className="log-what">
                      {m.rate != null && m.status !== "failed" ? <b>{fmtRate(m.rate)} 초/일</b> : null}
                      {STATUS_LABEL[m.status] && <em className={m.status}>{STATUS_LABEL[m.status]}</em>}
                      {m.error_reason && <small>{m.error_reason}</small>}
                    </span>
                  ) : (
                    <span className="log-what">
                      <b>{fmtRate(r!.offset_seconds, 0)}초 {r!.offset_seconds >= 0 ? "앞섬" : "늦음"}</b>
                      {r!.reset && <em>시간 맞춤</em>}
                      {r!.photo_url && <a href={r!.photo_url} target="_blank" rel="noreferrer">사진 보기</a>}
                    </span>
                  )}
                  <button className="x" aria-label="기록 삭제" onClick={async () => {
                    if (!confirm("이 기록을 삭제할까요?")) return;
                    await (m ? api.deleteMeasurement(id) : api.deleteReading(id));
                    await load();
                  }}>×</button>
                </li>
              ))}
            </ul>
          ))}
        </div>
      </section>

      <div className="actions">
        <button className="primary" onClick={() => go(`/watch/${watchId}/measure`)}>소리로 측정</button>
        <button className="secondary" onClick={() => go(`/watch/${watchId}/photo`)}>사진으로 기록</button>
      </div>
    </>
  );
}

function Back() {
  return <button className="ghost" onClick={() => go("/watches")}>← 컬렉션</button>;
}
