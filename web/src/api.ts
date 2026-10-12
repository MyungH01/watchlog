export type Watch = {
  id: string; name: string; brand: string | null; model: string | null; bph: number | null;
  photo_url: string | null; representative_rate: number | null; last_measured_at: string | null;
};
export type Measurement = {
  id: string; status: "pending" | "queued" | "processing" | "done" | "low_confidence" | "failed";
  rate: number | null; rate_first_half: number | null; rate_second_half: number | null;
  beat_error_ms: number | null; quality: number | null; detected_bph: number | null;
  error_reason: string | null; created_at: string;
};
export type Reading = { id: string; taken_at: string; offset_seconds: number; reset: boolean; photo_url: string | null };
export type History = {
  watch: Watch; measurements: Measurement[]; readings: Reading[]; worn_rates: { at: string; rate: number }[];
  summary: {
    status: "empty" | "collecting" | "steady" | "trending" | "overhaul" | "magnetized";
    sentence: string; rate: number | null; worn_rate: number | null; beat_error_ms: number | null; spread: number | null; count: number;
  };
};
export type Me = { anonymous: boolean; email: string | null; google_enabled: boolean };
type UploadForm = { url: string; fields: Record<string, string> };

async function call<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && retry && path !== "/api/session") {
    await call("POST", "/api/session"); // 쿠키가 없거나 만료됐으면 익명 세션을 새로 연다
    return call(method, path, body, false);
  }
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new Error(typeof detail === "string" ? detail : "요청을 처리하지 못했습니다");
  }
  return res.json();
}

async function uploadTo(form: UploadForm, file: Blob): Promise<void> {
  const data = new FormData();
  Object.entries(form.fields).forEach(([k, v]) => data.append(k, v));
  data.append("file", file); // S3 규칙: 파일은 맨 마지막 필드여야 한다
  const res = await fetch(form.url, { method: "POST", body: data });
  if (!res.ok) throw new Error("파일을 올리지 못했습니다");
}

/** 핸드폰 사진은 수 MB라서, 가운데를 정사각형으로 잘라 1200px JPEG로 줄여 올린다. 원형 틀에 맞고 로딩도 빠르다. */
async function squareJpeg(file: File, size = 1200): Promise<Blob> {
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  const side = Math.min(bmp.width, bmp.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = Math.min(size, side);
  canvas.getContext("2d")!.drawImage(bmp, (bmp.width - side) / 2, (bmp.height - side) / 2, side, side, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("사진을 처리하지 못했습니다"))), "image/jpeg", 0.88));
}

export const api = {
  session: () => call<Me>("POST", "/api/session"),
  watches: () => call<Watch[]>("GET", "/api/watches"),
  createWatch: (w: Partial<Watch>) => call<Watch>("POST", "/api/watches", w),
  updateWatch: (id: string, w: Partial<Watch> & { photo_key?: string }) => call<Watch>("PATCH", `/api/watches/${id}`, w),
  deleteWatch: (id: string) => call("DELETE", `/api/watches/${id}`),
  history: (id: string) => call<History>("GET", `/api/watches/${id}/history`),
  deleteReading: (id: string) => call("DELETE", `/api/readings/${id}`),
  deleteMeasurement: (id: string) => call("DELETE", `/api/measurements/${id}`),
  measurement: (id: string) => call<Measurement>("GET", `/api/measurements/${id}`),
  deleteMe: () => call("DELETE", "/api/me"),
  logout: () => call("POST", "/api/auth/logout"),

  async uploadPhoto(watchId: string, file: File): Promise<void> {
    const photo = await squareJpeg(file);
    const { photo_key, upload } = await call<{ photo_key: string; upload: UploadForm }>(
      "POST", `/api/watches/${watchId}/photo-url`, { content_type: "image/jpeg" });
    await uploadTo(upload, photo);
    await api.updateWatch(watchId, { photo_key });
  },

  /** 사진 기록 저장. 촬영 시각은 서버가 "지금부터 elapsed_ms 전"으로 계산한다. */
  async addReading(watchId: string, body: { shown_seconds: number; elapsed_ms: number; tz_offset_minutes: number; reset: boolean },
                   photo: Blob): Promise<void> {
    const { upload } = await call<{ upload: UploadForm | null }>("POST", `/api/watches/${watchId}/readings`, body);
    // 기록은 이미 저장됐다. 사진은 나중에 다시 보기 위한 것이라 올리지 못해도 기록을 실패로 보지 않는다
    if (upload) await uploadTo(upload, photo).catch(() => undefined);
  },

  async submitRecording(watchId: string, wav: Blob): Promise<string> {
    const { id, upload } = await call<{ id: string; upload: UploadForm }>("POST", `/api/watches/${watchId}/measurements`);
    await uploadTo(upload, new Blob([wav], { type: "audio/wav" }));
    await call("POST", `/api/measurements/${id}/uploaded`);
    return id;
  },
};

export const fmtRate = (r: number | null | undefined, digits = 1) =>
  r == null ? "-" : `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(digits)}`;

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function ago(iso: string | null): string {
  if (!iso) return "측정 기록 없음";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return days <= 0 ? "오늘 측정" : days < 30 ? `${days}일 전 측정` : `${Math.floor(days / 30)}달 전 측정`;
}
