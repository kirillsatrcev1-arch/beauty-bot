import { Plus } from "lucide-react";
import { useState } from "react";
import { Button, Field, Photo, Sheet, Skeleton, Toggle } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Master, Service } from "../types";
import { DayToggles, PhotoInput, useLoad } from "./shared";

type Draft = Omit<Master, "work_days" | "photo"> & { work_days: number[]; custom: boolean; photo_value: string | null; photo: string | null };
const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function MastersAdmin() {
  const { toast } = useApp();
  const { data, reload } = useLoad<{ masters: Master[] }>("/api/admin/masters");
  const { data: sd } = useLoad<{ services: Service[] }>("/api/admin/services");
  const [edit, setEdit] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);

  const open = (m?: Master) => setEdit(m ? {
    ...m, work_days: (m.work_days ?? "0,1,2,3,4,5").split(",").filter(Boolean).map(Number), custom: !!(m.work_days || m.work_start), photo_value: null,
  } : { id: 0, name: "", role: "Мастер", bio: "", photo: null, photo_value: null, active: true, service_ids: [], work_days: [0, 1, 2, 3, 4], custom: true,
    work_start: "10:00", work_end: "19:00", break_start: null, break_end: null });

  const save = async () => {
    if (!edit) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        id: edit.id || undefined, name: edit.name, role: edit.role, bio: edit.bio, active: edit.active, service_ids: edit.service_ids,
        work_days: edit.custom ? edit.work_days : null, work_start: edit.custom ? edit.work_start : null, work_end: edit.custom ? edit.work_end : null,
        break_start: edit.break_start || null, break_end: edit.break_end || null,
      };
      if (edit.photo_value || (!edit.photo && edit.id)) body.photo = edit.photo_value;
      await api.post("/api/admin/masters", body);
      toast("Сохранено"); setEdit(null); reload();
    } catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  const disable = async () => {
    if (!edit?.id) return;
    try { await api.del(`/api/admin/masters/${edit.id}`); toast("Мастер отключён"); setEdit(null); reload(); } catch (e) { toast(errorText(e)); }
  };
  const toggleSvc = (id: number) => edit && setEdit({ ...edit, service_ids: edit.service_ids.includes(id) ? edit.service_ids.filter((x) => x !== id) : [...edit.service_ids, id] });

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div><div className="eyebrow">Команда</div><h1 className="h-display mt-1 text-[38px]">Мастера</h1></div>
        <Button size="sm" onClick={() => open()}><Plus size={15} />Добавить</Button>
      </div>
      {!data ? <Skeleton className="h-60" /> : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.masters.map((m, i) => (
            <button key={m.id} onClick={() => open(m)} className={`card flex items-center gap-4 p-4 text-left ${m.active ? "" : "opacity-50"}`}>
              <Photo src={m.photo} seed={i + 1} className="h-20 w-20 shrink-0 rounded-[22px]" />
              <div className="min-w-0">
                <div className="h-display text-[24px]">{m.name}</div>
                <div className="text-[12px] font-semibold text-primary">{m.role}{!m.active && " · отключён"}</div>
                <div className="mt-1 text-[12px] text-muted">
                  {m.work_days ? m.work_days.split(",").filter(Boolean).map((d) => DAYS[+d]).join(" ") : "общий график"}{m.work_start ? ` · ${m.work_start}–${m.work_end}` : ""}
                </div>
                <div className="text-[12px] text-muted">{m.service_ids.length ? `${m.service_ids.length} услуг` : "все услуги"}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      <Sheet open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? edit.name : "Новый мастер"}>
        {edit && <>
          <PhotoInput value={edit.photo_value} url={edit.photo} onChange={(v, u) => setEdit({ ...edit, photo_value: v, photo: u })} className="mx-auto mb-4 h-36 w-36 !rounded-full" label="Фото" />
          <Field label="Имя"><input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Должность"><input className="input" value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })} placeholder="Топ-мастер" /></Field>
          <Field label="О мастере"><textarea className="input min-h-[80px] resize-none" value={edit.bio} onChange={(e) => setEdit({ ...edit, bio: e.target.value })} /></Field>

          <div className="mb-2 mt-5 text-[12px] font-semibold text-muted">График работы</div>
          <div className="card mb-3 px-4"><Toggle on={edit.custom} onChange={(v) => setEdit({ ...edit, custom: v })} label="Индивидуальный график" /></div>
          {edit.custom && <>
            <DayToggles value={edit.work_days} onChange={(v) => setEdit({ ...edit, work_days: v })} />
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="Начало"><input type="time" className="input" value={edit.work_start || ""} onChange={(e) => setEdit({ ...edit, work_start: e.target.value })} /></Field>
              <Field label="Конец"><input type="time" className="input" value={edit.work_end || ""} onChange={(e) => setEdit({ ...edit, work_end: e.target.value })} /></Field>
            </div>
          </>}
          <div className="grid grid-cols-2 gap-2">
            <Field label="Перерыв с"><input type="time" className="input" value={edit.break_start || ""} onChange={(e) => setEdit({ ...edit, break_start: e.target.value })} /></Field>
            <Field label="до"><input type="time" className="input" value={edit.break_end || ""} onChange={(e) => setEdit({ ...edit, break_end: e.target.value })} /></Field>
          </div>

          <div className="mb-2 mt-3 text-[12px] font-semibold text-muted">Услуги мастера {edit.service_ids.length === 0 && "· сейчас все"}</div>
          <div className="mb-4 flex flex-wrap gap-1.5">
            {(sd?.services || []).map((s) => {
              const on = edit.service_ids.includes(s.id);
              return <button key={s.id} type="button" onClick={() => toggleSvc(s.id)}
                className={`rounded-full px-3 py-2 text-[12.5px] font-medium ${on ? "bg-accent text-white dark:text-bg" : "bg-soft text-ink/70"}`}>{s.title}</button>;
            })}
          </div>
          <div className="card mb-4 px-4"><Toggle on={edit.active} onChange={(v) => setEdit({ ...edit, active: v })} label="Принимает записи" /></div>
          <Button size="lg" className="w-full" disabled={busy} onClick={save}>{busy ? "Сохраняю…" : "Сохранить"}</Button>
          {edit.id > 0 && edit.active && <Button variant="plain" className="mt-2 w-full !text-danger" onClick={disable}>Отключить мастера</Button>}
        </>}
      </Sheet>
    </div>
  );
}
