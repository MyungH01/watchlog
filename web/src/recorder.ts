// 시계 소리 녹음: 원본 PCM을 모으고, 째깍이 잡히는지 실시간으로 판정한다.
// 조건은 REQUIREMENTS.md 4.4 (아이폰 사파리 실측으로 확인한 값).

export const TARGET_SECONDS = 60; // 끊기지 않고 이만큼 잡히면 완료
export const MAX_SECONDS = 180; // 전체 한도
const LOST_AFTER_SECONDS = 3; // 이보다 오래 안 잡히면 처음부터 다시 모은다
const WINDOW_BINS = 2000; // 판정에 쓰는 최근 2초 (1ms 단위)
const MIN_LAG = 80;
const MAX_LAG = 260; // 째깍 간격 80~260ms
export const DETECT_THRESHOLD = 0.25;

export type RecorderState = {
  detected: boolean;
  score: number;
  beatsPerSecond: number;
  progress: number; // 0~1
  bins: number[]; // 화면용 최근 2초 포락선
};

export type Recorder = { cancel: () => void; done: Promise<Blob> };

/** 최근 2초 포락선에 일정한 박자가 있는지 (자기상관 최댓값과 그 간격) */
export function periodicity(bins: number[]): { score: number; lag: number } {
  const n = bins.length;
  if (n < MAX_LAG * 3) return { score: 0, lag: 0 };
  let mean = 0;
  for (const b of bins) mean += b;
  mean /= n;
  const v = bins.map((b) => b - mean);
  let r0 = 0;
  for (const x of v) r0 += x * x;
  let best = { score: 0, lag: 0 };
  for (let lag = MIN_LAG; lag <= MAX_LAG; lag++) {
    let r = 0;
    for (let i = 0; i + lag < n; i++) r += v[i] * v[i + lag];
    if (r / (r0 || 1) > best.score) best = { score: r / (r0 || 1), lag };
  }
  return best;
}

export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  const length = chunks.reduce((a, c) => a + c.length, 0);
  let peak = 1e-9;
  for (const c of chunks) for (let i = 0; i < c.length; i++) peak = Math.max(peak, Math.abs(c[i]));
  const view = new DataView(new ArrayBuffer(44 + length * 2));
  const text = (offset: number, s: string) => [...s].forEach((ch, i) => view.setUint8(offset + i, ch.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); text(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, length * 2, true);
  // 작은 소리가 16비트에서 뭉개지지 않게 최댓값 기준으로 키운다. 시점 정보는 그대로다.
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) view.setInt16(o, (c[i] / peak) * 0.9 * 32767, true);
  return new Blob([view], { type: "audio/wav" });
}

export async function startRecorder(onState: (s: RecorderState) => void): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
  });
  const ctx = new AudioContext();
  await ctx.resume();
  await ctx.audioWorklet.addModule("/tick-worklet.js");
  const node = new AudioWorkletNode(ctx, "tick-processor");
  const mute = ctx.createGain();
  mute.gain.value = 0; // 스피커로 되울리지 않게
  ctx.createMediaStreamSource(stream).connect(node).connect(mute).connect(ctx.destination);

  let chunks: Float32Array[] = [];
  let recent: number[] = [];
  let total = 0;
  let lostFor = 0;
  let messages = 0;
  let last = { score: 0, lag: 0 };
  let finished = false;

  const close = () => {
    finished = true;
    node.port.onmessage = null;
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
  };

  const done = new Promise<Blob>((resolve, reject) => {
    node.port.onmessage = (e: MessageEvent<{ raw: Float32Array; bins: number[] }>) => {
      if (finished) return;
      const seconds = e.data.raw.length / ctx.sampleRate;
      total += seconds;
      recent = recent.concat(e.data.bins).slice(-WINDOW_BINS);
      if (messages++ % 3 === 0) last = periodicity(recent); // 약 0.25초마다 판정
      const detected = last.score >= DETECT_THRESHOLD;
      lostFor = detected ? 0 : lostFor + seconds;
      if (lostFor > LOST_AFTER_SECONDS) chunks = []; // 끊긴 녹음은 이어 붙일 수 없으므로 버린다
      else chunks.push(e.data.raw);
      const kept = (chunks.length * e.data.raw.length) / ctx.sampleRate;
      onState({
        detected, score: last.score, beatsPerSecond: last.lag ? 1000 / last.lag : 0,
        progress: Math.min(1, kept / TARGET_SECONDS), bins: recent,
      });
      if (kept >= TARGET_SECONDS) {
        close();
        resolve(encodeWav(chunks, ctx.sampleRate));
      } else if (total >= MAX_SECONDS) {
        close();
        reject(new Error("timeout"));
      }
    };
  });

  return {
    done,
    cancel: () => {
      if (!finished) close();
    },
  };
}
