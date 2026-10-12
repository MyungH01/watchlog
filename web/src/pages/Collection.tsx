import { useEffect, useState } from "react";
import { ago, api, fmtRate, Me, Watch } from "../api";
import { go } from "../App";

export function Dial({ size = 64 }: { size?: number }) {
  // 사진이 없는 시계 자리에 놓는 다이얼. 12개의 눈금과 10시 10분의 바늘.
  return (
    <svg viewBox="-50 -50 100 100" width={size} height={size} className="dial" aria-hidden="true">
      <circle r="46" />
      {Array.from({ length: 12 }, (_, i) => (
        <line key={i} y1="-40" y2={i % 3 ? -36 : -32} transform={`rotate(${i * 30})`} />
      ))}
      <line className="hand" y2="-22" transform="rotate(-55)" />
      <line className="hand" y2="-32" transform="rotate(60)" />
    </svg>
  );
}

/** 컬렉션: 등록한 시계 목록 */
export function Collection({ me }: { me: Me }) {
  const [watches, setWatches] = useState<Watch[] | null>(null);
  useEffect(() => { api.watches().then(setWatches); }, []);

  if (watches === null) return <p className="loading">불러오는 중</p>;

  if (watches.length === 0) {
    return (
      <section className="panel empty">
        <Dial size={96} />
        <h2>아직 등록한 시계가 없습니다</h2>
        <p className="sub">시계를 등록하면 소리로 일오차를 측정하고 기록을 쌓을 수 있습니다.</p>
        <button className="primary wide" onClick={() => go("/new")}>시계 등록하기</button>
      </section>
    );
  }

  return (
    <>
      <ul className="collection">
        {watches.map((w, i) => (
          <li key={w.id} style={{ animationDelay: `${i * 60}ms` }}>
            <button className="card" onClick={() => go(`/watch/${w.id}`)}>
              {w.photo_url ? <img src={w.photo_url} alt="" /> : <Dial />}
              <span className="card-text">
                <strong>{w.name}</strong>
                <small>{[w.brand, w.model].filter(Boolean).join(" ") || ago(w.last_measured_at)}</small>
              </span>
              <span className="card-rate">
                <b>{fmtRate(w.representative_rate)}</b>
                <small>초/일</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <button className="primary wide" onClick={() => go("/new")}>시계 추가</button>
      {me.anonymous && (
        <p className="footnote">
          로그인하지 않은 상태입니다. 기록은 이 브라우저에만 연결돼 있어, 브라우저 데이터를 지우면 다시 볼 수 없습니다.{" "}
          <button className="link" onClick={() => go("/account")}>로그인하고 기록 보관하기</button>
        </p>
      )}
    </>
  );
}
