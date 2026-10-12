import { useEffect, useState } from "react";
import { go } from "../App";
import { Gauge } from "./Gauge";

const R = 96, CIRC = 2 * Math.PI * R;

/** 살아 있는 다이얼. 초침이 실제 28,800회 시계처럼 1초에 8번 끊어 움직인다. */
function LiveDial() {
  return (
    <svg viewBox="-120 -120 240 240" className="livedial" role="img" aria-label="초침이 1초에 8번씩 움직이는 시계 다이얼">
      <circle r="116" className="case" />
      <circle r="106" className="face" />
      {Array.from({ length: 60 }, (_, i) => (
        <line key={i} y1="-100" y2={i % 5 ? -95 : -86} transform={`rotate(${i * 6})`} className={i % 5 ? "minute" : "hour"} />
      ))}
      <text y="-46" textAnchor="middle" className="brand">watchlog</text>
      <text y="56" textAnchor="middle" className="spec">28,800 A/h</text>
      <line y2="-52" className="hand h" transform="rotate(-52)" />
      <line y2="-78" className="hand m" transform="rotate(48)" />
      <g className="seconds">
        <line y1="22" y2="-92" />
        <circle r="3.5" />
      </g>
    </svg>
  );
}

// 측정 한 번을 13초로 줄인 시연. 실제 동작(recorder.ts)과 같게 그린다:
// 감지 전 → 감지되어 채워짐 → 소리가 끊기면 처음부터 다시 → 끊김 없이 60초 → 완료.
// 끊긴 녹음은 이어 붙여 분석할 수 없어서, 멈췄다가 이어 가는 것이 아니라 0초로 돌아간다.
const LOOP_MS = 13000;
function demoAt(t: number): { seconds: number; state: "off" | "on" | "reset" | "done" } {
  if (t < 1500) return { seconds: 0, state: "off" };
  if (t < 4000) return { seconds: ((t - 1500) / 2500) * 18, state: "on" };
  if (t < 6200) return { seconds: 0, state: "reset" };
  if (t < 11500) return { seconds: ((t - 6200) / 5300) * 60, state: "on" };
  return { seconds: 60, state: "done" };
}
const DEMO_TEXT = {
  off: "시계를 마이크에 더 가까이 대 주세요",
  on: "째깍 감지됨, 초당 약 8회",
  reset: "소리가 끊겨 처음부터 다시 측정합니다",
  done: "측정 완료, 분석을 시작합니다",
};

/** 실제 측정 화면의 진행 원이 어떻게 움직이는지 보여 주는 시연 */
function RingDemo() {
  const [demo, setDemo] = useState(() => demoAt(9000));
  useEffect(() => {
    // 움직임을 줄이도록 설정한 사용자에게는 감지 중인 한 장면만 보여 준다
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const start = Date.now();
    const timer = setInterval(() => setDemo(demoAt((Date.now() - start) % LOOP_MS)), 100);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="l-demo" aria-hidden="true">
      <div className="ring">
        <svg viewBox="-110 -110 220 220">
          {Array.from({ length: 60 }, (_, i) => (
            <line key={i} y1="-108" y2={i % 5 ? -104 : -100} transform={`rotate(${i * 6})`} className="tick" />
          ))}
          <circle r={R} className="ring-bg" />
          <circle r={R} className="ring-fg" transform="rotate(-90)" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - demo.seconds / 60)} />
        </svg>
        <div className="ring-center">
          <b>{Math.floor(demo.seconds)}</b>
          <small>/ 60초</small>
        </div>
      </div>
      <p className={`detect ${demo.state === "on" || demo.state === "done" ? "on" : "off"}`}>{DEMO_TEXT[demo.state]}</p>
    </div>
  );
}

const STEPS = [
  ["시계를 마이크에 가까이", "조용한 곳에서 시계 뒷면을 핸드폰 하단의 마이크에 밀착시켜 주세요."],
  ["1분간 측정", "째깍 소리가 감지되는 동안 진행 원이 채워집니다. 소리가 3초 넘게 끊기면 처음부터 다시 측정합니다."],
  ["결과 확인", "일오차와 박자 균형을 확인할 수 있습니다. 측정 기록이 쌓이면 변화 추세도 함께 표시됩니다."],
];

/** 첫 방문용 소개. 시계를 아직 등록하지 않은 사람에게 컬렉션 대신 보여 준다. */
export function Landing() {
  const start = () => go("/new");
  return (
    <div className="landing">
      <section className="l-hero">
        <div className="l-copy">
          <h2>기계식 시계 일오차,<br />1분이면 측정됩니다</h2>
          <p className="lead">
            핸드폰 마이크로 소리를 분석해 일오차를 계산해 드립니다.
          </p>
          <button className="primary" onClick={start}>시계 등록하기</button>
        </div>
        <LiveDial />
      </section>

      <section className="l-method">
        <div>
          <h3>측정 방법</h3>
          <ol className="l-steps">
            {STEPS.map(([title, body], i) => (
              <li key={title}>
                <span className="num">{i + 1}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <RingDemo />
      </section>

      <section>
        <h3>두 가지 측정 방식</h3>
        <div className="l-pair">
          <article>
            <p className="tag">1분</p>
            <h4>소리로 측정</h4>
            <p>시계 소리를 분석해 지금의 일오차와 박자 균형을 확인합니다. 자성이 의심될 때 바로 확인할 수 있고, 측정이 쌓이면 오버홀 시기를 가늠할 수 있습니다.</p>
          </article>
          <article>
            <p className="tag">하루 이상</p>
            <h4>사진으로 기록</h4>
            <p>시계를 찍고 사진 속 초침 위치를 입력합니다. 다음 날 다시 찍으면 실제 착용 일오차가 계산됩니다. 시계를 정확히 맞춰 둘 필요가 없습니다.</p>
          </article>
        </div>
      </section>

      <section>
        <h3>결과 화면 <small>예시</small></h3>
        <div className="l-sample">
          <div className="headline">
            <div>
              <p className="reading-label">소리 측정</p>
              <p className="reading-value">+7.1<small> 초/일 (±2)</small></p>
            </div>
            <div className="worn">
              <p className="reading-label">실제 착용</p>
              <p className="worn-value">+5.4<small> 초/일</small></p>
            </div>
          </div>
          <Gauge rate={7.1} />
          <p className="status steady">일오차 +7.1초, 비트 에러 0.3ms로 박자가 고릅니다.</p>
        </div>
      </section>

      <section className="l-final">
        <h3>지금 차고 있는 시계부터 측정해 보세요</h3>
        <button className="primary" onClick={start}>시계 등록하기</button>
      </section>
    </div>
  );
}
