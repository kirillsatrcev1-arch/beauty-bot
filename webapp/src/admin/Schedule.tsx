import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Chips, Field, Skeleton } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Master } from "../types";
import { hdate, today } from "../utils/format";
import { DayToggles, Panel, Select, useLoad } from "./shared";

interface Sched {
  defaults: Record<string, string>;
  vacations: { id: number; master_id: number; date_from: string; date_to: string; note: string | null }[];
  blocks: { id: number; master_id: number | null; date: string; start: string; end: string; reason: string | null }[];
  windows: { id: number; master_id: number | null; date: string; start: string; end: string }[];
  studio_days: { date: string; closed: number; start: string | null; end: string | null }[];
  master_days: { master_id: number; date: string; closed: number; start: string | null; end: string | null }[];
}
type Kind = "vacation" | "block" | "day" | "window";

export function ScheduleAdmin() {
  const { toast } = useApp();
  const { data, reload } = useLoad<Sched>("/api/admin/schedule");
  const { data: md } = useLoad<{ masters: Master[] }>("/api/admin/masters");
  const masters = (md?.masters || []).filter((m) => m.active);
  const mName = (id: number | null) => (id ? masters.find((m) => m.id === id)?.name || "Мастер" : "Вся студия");
  const [kind, setKind] = useState<Kind>("vacation");
  const [form, setForm] = useState({ master_id: "", date: today(), date_to: today(), start: "13:00", end: "14:00", closed: true, reason: "" });
  const [def, setDef] = useState<Record<string, string> | null>(null);
  useEffect(() => { if (data) setDef(data.defaults); }, [data]);

  const add = async () => {
    const mid = form.master_id || (kind === "vacation" ? String(masters[0]?.id || "") : "");
    const body: Record<string, unknown> = { master_id: mid || null };
    if (kind === "vacation") Object.assign(body, { date_from: form.date, date_to: form.date_to, note: form.reason });
    if (kind === "block" || kind === "window") Object.assign(body, { date: form.date, start: form.start, end: form.end, reason: form.reason });
    if (kind === "day") Object.assign(body, { date: form.date, closed: form.closed, start: form.start, end: form.end });
    if (kind === "vacation" && !mid) return toast("Выбери мастера");
    try { await api.post(`/api/admin/schedule/${kind}`, body); toast("Добавлено"); reload(); } catch (e) { toast(errorText(e)); }
  };
  const remove = async (k: Kind, id: string | number) => {
    try { await api.del(`/api/admin/schedule/${k}/${id}`); reload(); } catch (e) { toast(errorText(e)); }
  };
  const saveDefaults = async () => {
    if (!def) return;
    try { await api.post("/api/admin/settings", def); toast("График студии сохранён"); } catch (e) { toast(errorText(e)); }
  };

  const items: { k: Kind; id: string | number; title: string; sub: string }[] = data ? [
    ...data.vacations.map((v) => ({ k: "vacation" as Kind, id: v.id, title: `Отпуск · ${mName(v.master_id)}`, sub: `${hdate(v.date_from, false)} — ${hdate(v.date_to, false)}${v.note ? ` · ${v.note}` : ""}` })),
    ...data.studio_days.map((d) => ({ k: "day" as Kind, id: d.date, title: d.closed ? "Студия закрыта" : `Особые часы студии`, sub: `${hdate(d.date)}${d.closed ? "" : ` · ${d.start}–${d.end}`}` })),
    ...data.master_days.map((d) => ({ k: "day" as Kind, id: `${d.master_id}_${d.date}`, title: `${d.closed ? "Выходной" : "Особые часы"} · ${mName(d.master_id)}`, sub: `${hdate(d.date)}${d.closed ? "" : ` · ${d.start}–${d.end}`}` })),
    ...data.blocks.map((x) => ({ k: "block" as Kind, id: x.id, title: `Блокировка · ${mName(x.master_id)}`, sub: `${hdate(x.date, false)}, ${x.start}–${x.end}${x.reason ? ` · ${x.reason}` : ""}` })),
    ...data.windows.map((x) => ({ k: "window" as Kind, id: x.id, title: `Доп. окно · ${mName(x.master_id)}`, sub: `${hdate(x.date, false)}, ${x.start}–${x.end}` })),
  ] : [];

  return (
    <div>
      <div className="mb-4"><div className="eyebrow">Рабочее время</div><h1 className="h-display mt-1 text-[38px]">Расписание</h1></div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="График студии по умолчанию">
          {!def ? <Skeleton className="h-40" /> : <>
            <p className="mb-3 text-[12.5px] text-muted">Используется для мастеров без индивидуального графика.</p>
            <DayToggles value={def.work_days.split(",").filter(Boolean).map(Number)} onChange={(v) => setDef({ ...def, work_days: v.join(",") })} />
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="Начало"><input type="time" className="input" value={def.work_start} onChange={(e) => setDef({ ...def, work_start: e.target.value })} /></Field>
              <Field label="Конец"><input type="time" className="input" value={def.work_end} onChange={(e) => setDef({ ...def, work_end: e.target.value })} /></Field>
              <Field label="Шаг сетки, мин"><input className="input" inputMode="numeric" value={def.slot_step} onChange={(e) => setDef({ ...def, slot_step: e.target.value.replace(/\D/g, "") })} /></Field>
              <Field label="Запись на дней вперёд"><input className="input" inputMode="numeric" value={def.horizon_days} onChange={(e) => setDef({ ...def, horizon_days: e.target.value.replace(/\D/g, "") })} /></Field>
            </div>
            <Field label="Минимум минут до записи"><input className="input" inputMode="numeric" value={def.min_lead_min} onChange={(e) => setDef({ ...def, min_lead_min: e.target.value.replace(/\D/g, "") })} /></Field>
            <Button className="w-full" onClick={saveDefaults}>Сохранить график</Button>
          </>}
        </Panel>

        <Panel title="Добавить исключение">
          <Chips id="sk" value={kind} onChange={setKind} items={[{ value: "vacation", label: "Отпуск" }, { value: "day", label: "Выходной / часы" }, { value: "block", label: "Блокировка" }, { value: "window", label: "Доп. окно" }]} />
          <div className="mt-3">
            <Field label="Для кого">
              <Select value={form.master_id} onChange={(v) => setForm({ ...form, master_id: v })}
                options={[...(kind === "vacation" ? [] : [{ value: "", label: "Вся студия" }]), ...masters.map((m) => ({ value: String(m.id), label: m.name }))]} />
            </Field>
            {kind === "vacation" ? (
              <div className="grid grid-cols-2 gap-2">
                <Field label="С"><input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
                <Field label="По"><input type="date" className="input" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} /></Field>
              </div>
            ) : <Field label="Дата"><input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>}
            {kind === "day" && (
              <div className="mb-3 flex gap-2">
                <Button size="sm" variant={form.closed ? "primary" : "ghost"} onClick={() => setForm({ ...form, closed: true })}>Выходной</Button>
                <Button size="sm" variant={!form.closed ? "primary" : "ghost"} onClick={() => setForm({ ...form, closed: false })}>Особые часы</Button>
              </div>
            )}
            {(kind === "block" || kind === "window" || (kind === "day" && !form.closed)) && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="С"><input type="time" className="input" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
                <Field label="До"><input type="time" className="input" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
              </div>
            )}
            {(kind === "block" || kind === "vacation") && <Field label="Комментарий"><input className="input" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder={kind === "block" ? "Например: обед, учёба" : "Например: отпуск в Сочи"} /></Field>}
            <Button className="w-full" onClick={add}>Добавить</Button>
          </div>
        </Panel>
      </div>

      <Panel title="Ближайшие исключения" className="mt-3">
        {!data ? <Skeleton className="h-24" /> : items.length === 0 ? <p className="py-4 text-center text-[13.5px] text-muted">Нет отпусков, блокировок и особых дней</p> : (
          <div className="divide-y divide-line">
            {items.map((it) => (
              <div key={`${it.k}-${it.id}`} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1"><div className="text-[14px] font-semibold">{it.title}</div><div className="text-[12.5px] text-muted">{it.sub}</div></div>
                <button onClick={() => remove(it.k, it.id)} aria-label="Удалить" className="grid h-9 w-9 place-items-center rounded-full bg-soft text-danger"><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
