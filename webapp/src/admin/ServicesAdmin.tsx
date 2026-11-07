import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Field, Photo, Sheet, Skeleton, Toggle } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Service } from "../types";
import { dur, rub } from "../utils/format";
import { PhotoInput, Select, useLoad } from "./shared";

type Draft = { id?: number; title: string; category: string; description: string; price: string; price_from: boolean; duration: string; active: boolean; photo: string | null; photo_url: string | null };

export function ServicesAdmin() {
  const { toast } = useApp();
  const { data, reload } = useLoad<{ services: Service[]; categories: { id: string; title: string }[] }>("/api/admin/services");
  const [edit, setEdit] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => setConfirmDel(false), [edit?.id]);

  const open = (s?: Service) => setEdit(s ? {
    id: s.id, title: s.title, category: s.category, description: s.description, price: String(s.price), price_from: s.price_from,
    duration: String(s.duration), active: s.active, photo: null, photo_url: s.photo,
  } : { title: "", category: data?.categories[0]?.id || "mani", description: "", price: "", price_from: false, duration: "60", active: true, photo: null, photo_url: null });

  const save = async () => {
    if (!edit) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { ...edit, price: +edit.price, duration: +edit.duration };
      delete body.photo_url;
      if (edit.photo === null && edit.photo_url) delete body.photo; // фото не меняли
      if (edit.photo === null && !edit.photo_url) body.photo = null;
      await api.post("/api/admin/services", body);
      toast("Сохранено"); setEdit(null); reload();
    } catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  const quickToggle = async (s: Service) => {
    try { await api.post("/api/admin/services", { ...s, active: !s.active, photo: undefined }); reload(); } catch (e) { toast(errorText(e)); }
  };
  const del = async () => {
    if (!edit?.id) return;
    try { await api.del(`/api/admin/services/${edit.id}`); toast("Услуга удалена"); setEdit(null); reload(); } catch (e) { toast(errorText(e)); }
  };

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div><div className="eyebrow">Каталог</div><h1 className="h-display mt-1 text-[38px]">Услуги</h1></div>
        <Button size="sm" onClick={() => open()}><Plus size={15} />Добавить</Button>
      </div>
      {!data ? <Skeleton className="h-80" /> : data.categories.map((c) => {
        const list = data.services.filter((s) => s.category === c.id);
        if (!list.length) return null;
        return (
          <section key={c.id} className="mb-5">
            <h2 className="h-display mb-2 text-[22px]">{c.title}</h2>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {list.map((s) => (
                <div key={s.id} className={`card flex items-center gap-3 p-3 ${s.active ? "" : "opacity-55"}`}>
                  <button onClick={() => open(s)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                    <Photo src={s.photo} seed={s.id} className="h-16 w-16 shrink-0 rounded-[18px]" />
                    <div className="min-w-0"><div className="truncate text-[14.5px] font-semibold">{s.title}</div>
                      <div className="text-[12.5px] text-muted">{rub(s.price, s.price_from)} · {dur(s.duration)}</div></div>
                  </button>
                  <div className="w-14"><Toggle on={s.active} onChange={() => quickToggle(s)} label="" /></div>
                </div>
              ))}
            </div>
          </section>
        );
      })}

      <Sheet open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Услуга" : "Новая услуга"}>
        {edit && <>
          <PhotoInput value={edit.photo} url={edit.photo_url} onChange={(v, u) => setEdit({ ...edit, photo: v, photo_url: u })} className="mb-4 h-44 w-full" />
          <Field label="Название"><input className="input" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
          <Field label="Категория"><Select value={edit.category} onChange={(v) => setEdit({ ...edit, category: v })} options={(data?.categories || []).map((c) => ({ value: c.id, label: c.title }))} /></Field>
          <Field label="Описание"><textarea className="input min-h-[90px] resize-none" value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Цена, ₽"><input className="input" inputMode="numeric" value={edit.price} onChange={(e) => setEdit({ ...edit, price: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Длительность, мин"><input className="input" inputMode="numeric" value={edit.duration} onChange={(e) => setEdit({ ...edit, duration: e.target.value.replace(/\D/g, "") })} /></Field>
          </div>
          <div className="card mb-4 divide-y divide-line px-4">
            <Toggle on={edit.price_from} onChange={(v) => setEdit({ ...edit, price_from: v })} label="Цена «от»" />
            <Toggle on={edit.active} onChange={(v) => setEdit({ ...edit, active: v })} label="Показывать клиентам" />
          </div>
          <Button size="lg" className="w-full" disabled={busy} onClick={save}>{busy ? "Сохраняю…" : "Сохранить"}</Button>
          {edit.id && (confirmDel
            ? <Button size="lg" variant="danger" className="mt-2 w-full" onClick={del}>Точно удалить? История записей сохранится</Button>
            : <Button variant="plain" className="mt-2 w-full !text-danger" onClick={() => setConfirmDel(true)}>Удалить услугу</Button>)}
        </>}
      </Sheet>
    </div>
  );
}
