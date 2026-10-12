// 마이크 원본을 그대로 모으면서, 실시간 감지용으로 6kHz 이상만 남긴 포락선(1ms 단위)을 함께 만든다.
// 째깍 소리는 6kHz 이상에만 있어서, 걸러 내지 않으면 낮은 음역의 잡음에 묻힌다.
class TickProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.raw = new Float32Array(4096);
    this.n = 0;
    this.bins = [];
    this.binMax = 0;
    this.binCount = 0;
    this.binSize = Math.round(sampleRate / 1000);
    // 2차 고역 통과 필터 (RBJ 공식, 6kHz, Q=0.707)
    const w0 = (2 * Math.PI * 6000) / sampleRate;
    const cos = Math.cos(w0);
    const alpha = Math.sin(w0) / (2 * 0.707);
    const a0 = 1 + alpha;
    this.b0 = (1 + cos) / 2 / a0;
    this.b1 = -(1 + cos) / a0;
    this.a1 = (-2 * cos) / a0;
    this.a2 = (1 - alpha) / a0;
    this.x1 = this.x2 = this.y1 = this.y2 = 0;
  }

  process(inputs) {
    const x = inputs[0][0];
    if (!x) return true;
    for (let i = 0; i < x.length; i++) {
      const s = x[i];
      this.raw[this.n++] = s;
      const y = this.b0 * s + this.b1 * this.x1 + this.b0 * this.x2 - this.a1 * this.y1 - this.a2 * this.y2;
      this.x2 = this.x1; this.x1 = s; this.y2 = this.y1; this.y1 = y;
      const a = Math.abs(y);
      if (a > this.binMax) this.binMax = a;
      if (++this.binCount === this.binSize) {
        this.bins.push(this.binMax);
        this.binMax = 0;
        this.binCount = 0;
      }
      if (this.n === this.raw.length) {
        this.port.postMessage({ raw: this.raw.slice(), bins: this.bins });
        this.n = 0;
        this.bins = [];
      }
    }
    return true;
  }
}

registerProcessor("tick-processor", TickProcessor);
