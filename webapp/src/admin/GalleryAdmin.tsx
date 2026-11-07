import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Chips, Photo, Skeleton } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Work } from "../types";
import { Select, useLoad } from "./shared";

export function GalleryAdmin() {
  const { toast } = useApp();
  const { data, reload } = useLoad<{ items: Work[]; sections: { id: string; title: string }[] }>("/api/admin/gallery");
  const [sec, setSec] = useState("all");
  const [target, setTarget] = useState("nude");
  const [busy, setBusy] = useState(0);
  const [confirm, setConfirm] = useState<number | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    const list = Array.from(files);
    setBusy(list.length);
    let ok = 0;
    for (const f of list) {
      try { const r = await api.upload(f); await api.post("/api/admin/gallery", { section: target, photo: r.value }); ok++; }
      catch (e) { toast(errorText(e)); }
      setBusy((n) => n - 1);
    }
    if (ok) toast(`Добавлено фото: ${ok}`);
    reload();
  };
  const del = async (id: number) => {
    if (confirm !== id) return setConfirm(id);
    try { await api.del(`/api/admin/gallery/${id}`); setConfirm(null); reload(); } catch (e) { toast(errorText(e)); }
  };
  const caption = async (id: number, text: string) => {
    try { await api.post(`/api/admin/gallery/${id}`, { caption: text }); } catch (e) { toast(errorText(e)); }
  };
  const move = async (id: number, section: string) => {
    try { await api.post(`/api/admin/gallery/${id}`, { section }); reload(); } catch (e) { toast(errorText(e)); }
  };

  const items = (data?.items || []).filter((w) => sec === "all" || w.section === sec);
  const sections = data?.sections || [];

  return (
    <div>
      <div className="mb-4"><div className="eyebrow">Портфолио</div><h1 className="h-display mt-1 text-[38px]">Галерея</h1></div>
      <div className="card mb-4 flex flex-wrap items-end gap-2 p-4">
        <div className="min-w-[160px] flex-1"><div className="mb-1.5 ml-1 text-[12px] font-semibold text-muted">Раздел для новых фото</div>
          <Select value={target} onChange={setTarget} options={sections.map((s) => ({ value: s.id, label: s.title }))} /></div>
        <button onClick={() => ref.current?.click()} disabled={busy > 0}
          className="flex h-[50px] items-center gap-2 rounded-2xl bg-accent px-5 text-[14px] font-semibold text-white disabled:opacity-60 dark:text-bg">
          {busy ? <><Loader2 size={17} className="animate-spin" />Осталось {busy}</> : <><ImagePlus size={17} />Загрузить фото</>}
        </button>
        <input ref={ref} type="file" accept="image/*" multiple hidden onChange={(e) => { upload(e.target.files); e.target.value = ""; }} />
        <p className="w-full text-[11.5px] text-muted">Можно выбрать сразу несколько фото. Они сохраняются в высоком качестве (до 2000 px).</p>
      </div>
      <Chips id="gsec" value={sec} onChange={setSec} items={[{ value: "all", label: `Все · ${data?.items.length ?? 0}` }, ...sections.map((s) => ({ value: s.id, label: `${s.title} · ${(data?.items || []).filter((w) => w.section === s.id).length}` }))]} />
      {!data ? <Skeleton className="mt-4 h-72" /> : items.length === 0 ? <p className="card mt-4 py-10 text-center text-muted">В разделе пока нет фото</p> : (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((w) => (
            <div key={w.id} className="card overflow-hidden">
              <div className="relative">
                <Photo src={w.src} className="aspect-[3/4] w-full" />
                <button onClick={() => del(w.id)} aria-label="Удалить"
                  className={`absolute right-2 top-2 flex h-9 items-center gap-1 rounded-full px-2.5 text-[12px] font-semibold ${confirm === w.id ? "bg-danger text-white" : "bg-white/90 text-danger"}`}>
                  <Trash2 size={14} />{confirm === w.id && "Удалить?"}
                </button>
              </div>
              <div className="p-2.5">
                <input defaultValue={w.caption} onBlur={(e) => e.target.value !== w.caption && caption(w.id, e.target.value)} placeholder="Подпись"
                  className="w-full rounded-xl bg-soft px-3 py-2 text-[12.5px] outline-none focus:ring-2 focus:ring-primary/30" />
                <select value={w.section} onChange={(e) => move(w.id, e.target.value)} className="mt-1.5 w-full rounded-xl bg-transparent px-1 py-1 text-[12px] text-muted outline-none">
                  {sections.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
