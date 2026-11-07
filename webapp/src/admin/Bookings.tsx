import { Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button, Chips, Field, Sheet, Skeleton, StatusBadge } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Booking, Master, Service, Slot } from "../types";
import { addDays, dur, hdate, rub, time, today } from "../utils/format";
import { BookingRow, Select, useLoad } from "./shared";

type Range = "today" | "week" | "upcoming" | "past" | "all";

export function BookingsAdmin({ focus }: { focus?: { date?: string } | null }) {
  const [q, setQ] = useState("");
  const [range, setRange] = useState<Range>(focus?.date ? "all" : "upcoming");
  const [status, setStatus] = useState("");
  const [master, setMaster] = useState("");
  const [open, setOpen] = useState<Booking | null>(null);
  const [create, setCreate] = useState<{ date?: string; time?: string; master?: number } | null>(null);
  const { data: md } = useLoad<{ masters: Master[] }>("/api/admin/masters");

  const t = today();
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (range === "today") { params.set("from", t); params.set("to", t); }
  if (range === "week") { params.set("from", t); params.set("to", addDays(t, 6)); }
  if (range === "upcoming") params.set("from", t);
  if (range === "past") { params.set("to", addDays(t, -1)); params.set("order", "desc"); }
  if (focus?.date && range === "all") { params.set("from", focus.date); params.set("to", focus.date); }
  if (status) params.set("status", status);
  if (master) params.set("master", master);
  const [debounced, setDebounced] = useState(params.toString());
  useEffect(() => { const id = setTimeout(() => setDebounced(params.toString()), 250); return () => clearTimeout(id); }, [params.toString()]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, reload } = useLoad<{ items: Booking[] }>(`/api/admin/bookings?${debounced}`);

  const groups = useMemo(() => {
    const g: Record<string, Booking[]> = {};
    (data?.items || []).forEach((b) => (g[b.date] ||= []).push(b));
    return Object.entries(g);
  }, [data]);

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div><div className="eyebrow">Управление</div><h1 className="h-display mt-1 text-[38px]">Записи</h1></div>
        <Button size="sm" onClick={() => setCreate({})}><Plus size={15} />Новая запись</Button>
      </div>
      <div className="relative">
        <Search size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по имени, телефону или услуге" className="input pl-11" type="search" />
      </div>
      <Chips id="range" className="mt-3" value={range} onChange={setRange} items={[
        { value: "upcoming", label: "Предстоящие" }, { value: "today", label: "Сегодня" }, { value: "week", label: "7 дней" },
        { value: "past", label: "Прошедшие" }, { value: "all", label: "Все" }]} />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Select value={status} onChange={setStatus} options={[{ value: "", label: "Все статусы" }, { value: "pending", label: "Ждут подтверждения" },
          { value: "confirmed", label: "Подтверждены" }, { value: "done", label: "Состоялись" }, { value: "cancelled", label: "Отменены" }]} />
        <Select value={master} onChange={setMaster} options={[{ value: "", label: "Все мастера" }, ...(md?.masters || []).map((m) => ({ value: String(m.id), label: m.name }))]} />
      </div>

      <div className="mt-5">
        {!data ? <Skeleton className="h-60" /> : groups.length === 0 ? <p className="card py-10 text-center text-[14px] text-muted">Записей не найдено</p> :
          groups.map(([date, list]) => (
            <section key={date} className="mb-4">
              <div className="mb-2 ml-1 text-[13px] font-semibold text-muted">{hdate(date)}</div>
              <div className="card divide-y divide-line px-4">{list.map((b) => (
                <div key={b.id} className="flex items-center gap-2">
                  <div className="min-w-0 flex-1"><BookingRow b={b} showDate={false} onClick={() => setOpen(b)} /></div>
                  <div className="hidden sm:block"><StatusBadge status={b.status} /></div>
                </div>
              ))}</div>
            </section>
          ))}
      </div>
      <BookingSheet b={open} onClose={() => setOpen(null)} onChanged={() => { reload(); }} masters={md?.masters || []} />
      <CreateSheet open={!!create} preset={create} onClose={() => setCreate(null)} onCreated={reload} masters={md?.masters || []} />
    </div>
  );
}

export function BookingSheet({ b, onClose, onChanged, masters }: { b: Booking | null; onClose: () => void; onChanged: () => void; masters: Master[] }) {
  const { toast } = useApp();
  const [mode, setMode] = useState<"view" | "move" | "cancel">("view");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [cur, setCur] = useState<Booking | null>(b);
  useEffect(() => { setCur(b); setMode("view"); setReason(""); }, [b]);

  const act = async (body: Record<string, unknown>, msg: string) => {
    if (!cur) return;
    setBusy(true);
    try { const r = await api.post<{ booking: Booking }>(`/api/admin/bookings/${cur.id}`, body); setCur(r.booking); setMode("view"); toast(msg); onChanged(); }
    catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  const x = cur;
  return (
    <Sheet open={!!b} onClose={onClose} title={x ? x.name : ""}>
      {x && mode === "view" && <>
        <div className="mb-4 flex items-center gap-2"><StatusBadge status={x.status} /><span className="text-[12px] text-muted">№{x.id} · {x.source === "admin" ? "записала мастер" : x.source === "webapp" ? "через приложение" : "через чат"}</span></div>
        <div className="card divide-y divide-line px-4 text-[14px]">
          {[["Услуга", x.service_title], ["Мастер", x.master_name || "—"], ["Когда", `${hdate(x.date)}, ${time(x.start)}–${time(x.end)}`],
            ["Длительность", dur(x.duration)], ["Стоимость", rub(x.price, x.price_from)], ["Телефон", x.phone || "—"], ["Комментарий", x.comment || "—"],
            ...(x.cancel_reason ? [["Причина отмены", x.cancel_reason]] : [])].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 py-3"><span className="text-muted">{k}</span><span className="text-right font-semibold">{v}</span></div>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          {x.status === "pending" && <Button disabled={busy} onClick={() => act({ action: "confirm" }, "Подтверждено, клиентка получила уведомление")}>Подтвердить</Button>}
          {x.status === "confirmed" && <Button disabled={busy} onClick={() => act({ action: "done" }, "Отмечено: визит состоялся")}>Визит состоялся</Button>}
          {["pending", "confirmed"].includes(x.status) && <Button variant="soft" onClick={() => setMode("move")}>Перенести</Button>}
          {["pending", "confirmed"].includes(x.status) && <Button variant="danger" onClick={() => setMode("cancel")}>Отменить</Button>}
          {x.user_id > 0 && <Button variant="ghost" onClick={() => window.open(`tg://user?id=${x.user_id}`)}>Написать</Button>}
        </div>
        <Field label="Сменить статус вручную">
          <Select value={x.status} onChange={(v) => act({ action: "status", status: v }, "Статус изменён")} options={[
            { value: "pending", label: "Ждёт подтверждения" }, { value: "confirmed", label: "Подтверждена" }, { value: "done", label: "Визит состоялся" }, { value: "cancelled", label: "Отменена" }]} />
        </Field>
      </>}
      {x && mode === "cancel" && <>
        <p className="text-[14px] text-muted">Клиентка получит уведомление об отмене.</p>
        <Field label="Причина (необязательно)"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: мастер заболела" /></Field>
        <Button variant="danger" className="w-full" size="lg" disabled={busy} onClick={() => act({ action: "cancel", reason }, "Запись отменена")}>Отменить запись</Button>
        <Button variant="plain" className="mt-1 w-full" onClick={() => setMode("view")}>Назад</Button>
      </>}
      {x && mode === "move" && <SlotPicker exclude={x.id} masters={masters} initialMaster={x.master_id}
        onPick={(date, t, m) => act({ action: "move", date, time: t, master: m }, "Запись перенесена, клиентка уведомлена")} onBack={() => setMode("view")} busy={busy} />}
    </Sheet>
  );
}

/** Выбор даты, мастера и свободного времени для переноса / ручной записи. */
function SlotPicker({ exclude, service, masters, initialMaster, initialDate, onPick, onBack, busy }: {
  exclude?: number; service?: number; masters: Master[]; initialMaster?: number; initialDate?: string;
  onPick: (date: string, time: string, master: number) => void; onBack?: () => void; busy: boolean;
}) {
  const [date, setDate] = useState(initialDate || today());
  const [master, setMaster] = useState(String(initialMaster || ""));
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [manual, setManual] = useState("");
  useEffect(() => {
    if (!exclude && !service) return;
    setSlots(null);
    const p = new URLSearchParams({ date, ...(exclude ? { exclude: String(exclude) } : { service: String(service) }), ...(master ? { master } : {}) });
    api.get<{ slots: Slot[] }>(`/api/admin/slots?${p}`).then((r) => setSlots(r.slots)).catch(() => setSlots([]));
  }, [date, master, exclude, service]);
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Дата"><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Мастер"><Select value={master} onChange={setMaster} options={[{ value: "", label: "Любой" }, ...masters.filter((m) => m.active).map((m) => ({ value: String(m.id), label: m.name }))]} /></Field>
      </div>
      <div className="mb-2 text-[12px] font-semibold text-muted">Свободное время</div>
      {slots === null ? <Skeleton className="h-24" /> : slots.length === 0 ? <p className="mb-3 text-[13px] text-muted">Свободных окон нет — можно указать время вручную ниже</p> : (
        <div className="mb-3 grid grid-cols-4 gap-2">
          {slots.map((s) => <button key={s.time} disabled={busy} onClick={() => onPick(date, s.time, master ? +master : s.masters[0])}
            className="h-11 rounded-2xl bg-surface text-[14px] font-semibold shadow-card active:bg-accent active:text-white">{s.time}</button>)}
        </div>
      )}
      {service && <div className="flex items-end gap-2">
        <Field label="Или любое время (вне графика)"><input type="time" className="input" value={manual} onChange={(e) => setManual(e.target.value)} /></Field>
        <Button className="mb-3.5" disabled={!manual || busy || !(master || masters[0])} onClick={() => onPick(date, manual, master ? +master : masters[0].id)}>Ок</Button>
      </div>}
      {onBack && <Button variant="plain" className="w-full" onClick={onBack}>Назад</Button>}
    </div>
  );
}

export function CreateSheet({ open, preset, onClose, onCreated, masters }: { open: boolean; preset: { date?: string; time?: string; master?: number } | null; onClose: () => void; onCreated: () => void; masters: Master[] }) {
  const { toast } = useApp();
  const { data } = useLoad<{ services: Service[] }>(open ? "/api/admin/services" : null);
  const [service, setService] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(""); setPhone(""); setComment(""); } }, [open]);
  const services = (data?.services || []).filter((s) => s.active);
  const sid = service || String(services[0]?.id || "");
  const create = async (date: string, time: string, master: number) => {
    if (name.trim().length < 2) return toast("Укажи имя клиентки");
    setBusy(true);
    try {
      await api.post("/api/admin/bookings", { service: +sid, master, date, time, name, phone, comment });
      toast("Запись создана"); onCreated(); onClose();
    } catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Новая запись">
      <Field label="Клиентка"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Имя" /></Field>
      <Field label="Телефон"><input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+7 900 000-00-00" inputMode="tel" /></Field>
      <Field label="Услуга"><Select value={sid} onChange={setService} options={services.map((s) => ({ value: String(s.id), label: `${s.title} · ${dur(s.duration)}` }))} /></Field>
      <Field label="Комментарий"><input className="input" value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      {sid && <SlotPicker key={sid} service={+sid} masters={masters} initialMaster={preset?.master} initialDate={preset?.date} onPick={create} busy={busy} />}
    </Sheet>
  );
}
