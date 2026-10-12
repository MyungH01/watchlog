import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { go } from "../App";

const BPH = [18000, 21600, 25200, 28800, 36000];

export function WatchForm({ watchId }: { watchId?: string }) {
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [bph, setBph] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!watchId) return;
    api.history(watchId).then(({ watch: w }) => {
      setName(w.name); setBrand(w.brand ?? ""); setModel(w.model ?? ""); setBph(w.bph ? String(w.bph) : "");
    });
  }, [watchId]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    const body = { name: name.trim(), brand: brand.trim() || null, model: model.trim() || null, bph: bph ? Number(bph) : null };
    try {
      const watch = watchId ? await api.updateWatch(watchId, body) : await api.createWatch(body);
      if (photo) await api.uploadPhoto(watch.id, photo);
      go(`/watch/${watch.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  async function remove() {
    if (!watchId || !confirm("이 시계와 모든 기록을 삭제할까요? 되돌릴 수 없습니다.")) return;
    await api.deleteWatch(watchId);
    go("/watches");
  }

  return (
    <>
      <header className="top">
        <button className="ghost" onClick={() => history.back()}>← 뒤로</button>
        <h1>{watchId ? "시계 정보 수정" : "시계 등록"}</h1>
      </header>
      <form className="form" onSubmit={save}>
        <label>이름
          <input id="watch-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} placeholder="예: 까레라" />
        </label>
        <label>브랜드 <span className="optional">선택</span>
          <input id="watch-brand" value={brand} onChange={(e) => setBrand(e.target.value)} maxLength={100} />
        </label>
        <label>모델 <span className="optional">선택</span>
          <input id="watch-model" value={model} onChange={(e) => setModel(e.target.value)} maxLength={100} />
        </label>
        {/* 등록할 때는 묻지 않는다(첫 측정에서 자동 판별). 판별이 틀렸을 때 고칠 수 있도록 수정 화면에만 둔다 */}
        {watchId && (
          <label>박자 <span className="optional">자동으로 알아낸 값이 틀렸을 때만 바꾸세요</span>
            <select id="watch-bph" value={bph} onChange={(e) => setBph(e.target.value)}>
              <option value="">다음 측정에서 다시 알아내기</option>
              {BPH.map((b) => <option key={b} value={b}>{b.toLocaleString()}회/시간</option>)}
            </select>
          </label>
        )}
        <label>사진 <span className="optional">선택 · 직접 찍은 사진</span>
          <input id="watch-photo" type="file" accept="image/*" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          <span className="footnote">정면에서, 시계가 화면 가운데에 가득 차게 찍으면 가장 보기 좋습니다. 가운데를 원형으로 잘라 보여 줍니다.</span>
        </label>
        {error && <p className="notice bad">{error}</p>}
        <button className="primary wide" disabled={busy}>{busy ? "저장하는 중" : "저장"}</button>
        {watchId && <button type="button" className="danger wide" onClick={remove}>시계 삭제</button>}
      </form>
    </>
  );
}
