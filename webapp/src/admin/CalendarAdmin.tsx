import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Button, Segmented, Skeleton } from "../components/ui";
import type { Booking, Master } from "../types";
import { MONTHS_NOM, WD_SHORT, addDays, fromMin, hdate, isoOf, parseIso, toMin, today } from "../utils/format";
import { BookingSheet, CreateSheet } from "./Bookings";
import { Select, useLoad } from "./shared";

type View = "day" | "week" | "month";
interface CalDay { date: string; windows: Record<string, [number, number][]>; bookings: Booking[]; blocks: { id: number; master_id: number | null; start: string; end: string; reason: string | null }[] }

const H0 = 8 * 60, H1 = 22 * 60, PX = 1.1; // шкала: 8:00–22:00, 1.1 px на минуту

function weekStart(iso: string) { const d = parseIso(iso); return addDays(iso, -((d.getDay() + 6) % 7)); }
function range(view: View, anchor: string): [string, string] {
  if (view === "day") return [anchor, anchor];
  if (view === "week") { const s = weekStart(anchor); return [s, addDays(s, 6)]; }
  const d = parseIso(anchor);
  const first = isoOf(new Date(d.getFullYear(), d.getMonth(), 1));
  const last = isoOf(new Date(d.getFullYear(), d.getMonth() + 1, 0));
  return [weekStart(first), addDays(weekStart(last), 6)];
}

export function CalendarAdmin({ focusDate }: { focusDate?: string }) {
  const [view, setView] = useState<View>("day");
  const [anchor, setAnchor] = useState(focusDate || today());
  const [master, setMaster] = useState("");
  const [open, setOpen] = useState<Booking | null>(null);
  const [create, setCreate] = useState<{ date?: string; time?: string; master?: number } | null>(null);
  const [from, to] = range(view, anchor);
  const { data, reload } = useLoad<{ days: CalDay[]; masters: { id: number; name: string }[] }>(`/api/admin/calendar?from=${from}&to=${to}${master ? `&master=${master}` : ""}`);
  const { data: md } = useLoad<{ masters: Master[] }>("/api/admin/masters");
  const masters = (md?.masters || []).filter((m) => m.active);

  const shift = (n: number) => {
    if (view === "day") setAnchor(addDays(anchor, n));
    else if (view === "week") setAnchor(addDays(anchor, 7 * n));
    else { const d = parseIso(anchor); setAnchor(isoOf(new Date(d.getFullYear(), d.getMonth() + n, 1))); }
  };
  const title = view === "day" ? hdate(anchor) : view === "week" ? `${hdate(from, false)} — ${hdate(to, false)}` : `${MONTHS_NOM[parseIso(anchor).getMonth()]} ${parseIso(anchor).getFullYear()}`;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div><div className="eyebrow">Расписание</div><h1 className="h-display mt-1 text-[38px]">Календарь</h1></div>
        <Button size="sm" onClick={() => setCreate({ date: anchor })}><Plus size={15} />Записать</Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented id="calview" value={view} onChange={setView} items={[{ value: "day", label: "День" }, { value: "week", label: "Неделя" }, { value: "month", label: "Месяц" }]} />
        <div className="w-40"><Select value={master} onChange={setMaster} options={[{ value: "", label: "Все мастера" }, ...masters.map((m) => ({ value: String(m.id), label: m.name }))]} /></div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <button onClick={() => shift(-1)} className="grid h-10 w-10 place-items-center rounded-full bg-surface shadow-card" aria-label="Назад"><ChevronLeft size={18} /></button>
        <button onClick={() => setAnchor(today())} className="text-[15px] font-semibold">{title}</button>
        <button onClick={() => shift(1)} className="grid h-10 w-10 place-items-center rounded-full bg-surface shadow-card" aria-label="Вперёд"><ChevronRight size={18} /></button>
      </div>

      <div className="mt-4">
        {!data ? <Skeleton className="h-[520px]" /> :
          view === "day" ? <DayView day={data.days[0]} masters={data.masters} onOpen={setOpen} onEmpty={(t, m) => setCreate({ date: anchor, time: t, master: m })} /> :
          view === "week" ? <WeekView days={data.days} onDay={(d) => { setAnchor(d); setView("day"); }} onOpen={setOpen} /> :
          <MonthView days={data.days} anchor={anchor} onDay={(d) => { setAnchor(d); setView("day"); }} />}
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-[11.5px] text-muted">
        <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded bg-surface ring-1 ring-line" />рабочее время</span>
        <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded bg-soft" />нерабочее</span>
        <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded" style={{ background: "repeating-linear-gradient(45deg, rgb(var(--muted)/.35) 0 3px, transparent 3px 6px)" }} />заблокировано</span>
        <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded bg-primary/80" />запись</span>
      </div>
      <BookingSheet b={open} onClose={() => setOpen(null)} onChanged={reload} masters={md?.masters || []} />
      <CreateSheet open={!!create} preset={create} onClose={() => setCreate(null)} onCreated={reload} masters={md?.masters || []} />
    </div>
  );
}

function DayView({ day, masters, onOpen, onEmpty }: { day: CalDay; masters: { id: number; name: string }[]; onOpen: (b: Booking) => void; onEmpty: (t: string, m: number) => void }) {
  const hours = useMemo(() => Array.from({ length: (H1 - H0) / 60 + 1 }, (_, i) => H0 + i * 60), []);
  const y = (m: number) => (Math.min(Math.max(m, H0), H1) - H0) * PX;
  return (
    <div className="card overflow-x-auto p-3">
      <div className="flex min-w-fit">
        <div className="relative w-11 shrink-0" style={{ height: (H1 - H0) * PX + 28 }}>
          {hours.map((h) => <div key={h} className="absolute right-2 text-[10.5px] tabular-nums text-muted" style={{ top: y(h) + 22 }}>{fromMin(h)}</div>)}
        </div>
        {masters.map((m) => {
          const win = day.windows[String(m.id)] || [];
          const bks = day.bookings.filter((b) => b.master_id === m.id);
          const blocks = day.blocks.filter((x) => x.master_id === null || x.master_id === m.id);
          return (
            <div key={m.id} className="min-w-[150px] flex-1 px-1">
              <div className="mb-2 h-5 truncate text-center text-[12.5px] font-semibold">{m.name}</div>
              <div className="relative rounded-2xl bg-soft" style={{ height: (H1 - H0) * PX }}
                onClick={(e) => {
                  const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                  const mins = Math.round(((e.clientY - rect.top) / PX + H0) / 30) * 30;
                  if (win.some(([s, en]) => mins >= s && mins < en)) onEmpty(fromMin(mins), m.id);
                }}>
                {hours.map((h) => <div key={h} className="absolute inset-x-0 border-t border-line/70" style={{ top: y(h) }} />)}
                {win.map(([s, e]) => <div key={s} className="absolute inset-x-0 bg-surface" style={{ top: y(s), height: y(e) - y(s) }} />)}
                {blocks.map((x) => <div key={x.id} className="absolute inset-x-1 rounded-xl" title={x.reason || "Заблокировано"}
                  style={{ top: y(toMin(x.start)), height: y(toMin(x.end)) - y(toMin(x.start)), background: "repeating-linear-gradient(45deg, rgb(var(--muted)/.3) 0 4px, transparent 4px 8px)" }} />)}
                {bks.map((b) => {
                  const s = toMin(b.start.slice(11)), e = toMin(b.end.slice(11));
                  const tone = b.status === "pending" ? "bg-warn/85" : b.status === "done" ? "bg-muted/70" : "bg-primary/90";
                  return (
                    <button key={b.id} onClick={(ev) => { ev.stopPropagation(); onOpen(b); }}
                      className={`absolute inset-x-1 overflow-hidden rounded-xl px-2 py-1 text-left text-white shadow-card ${tone}`}
                      style={{ top: y(s) + 1, height: Math.max(26, y(e) - y(s) - 2) }}>
                      <div className="text-[11.5px] font-semibold tabular-nums">{b.start.slice(11, 16)}–{b.end.slice(11, 16)}</div>
                      <div className="truncate text-[12px] font-semibold">{b.name}</div>
                      <div className="truncate text-[11px] opacity-85">{b.service_title}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-center text-[11.5px] text-muted">Нажми на свободное время в колонке мастера, чтобы записать клиентку</p>
    </div>
  );
}

function WeekView({ days, onDay, onOpen }: { days: CalDay[]; onDay: (d: string) => void; onOpen: (b: Booking) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-7">
      {days.map((d, i) => {
        const work = Object.values(d.windows).some((w) => w.length);
        const isToday = d.date === today();
        return (
          <div key={d.date} className={`card p-3 ${!work ? "opacity-60" : ""}`}>
            <button onClick={() => onDay(d.date)} className="mb-2 flex w-full items-baseline justify-between">
              <span className="text-[12px] font-semibold text-muted">{WD_SHORT[i]}</span>
              <span className={`grid h-8 w-8 place-items-center rounded-full text-[15px] font-semibold ${isToday ? "bg-accent text-white dark:text-bg" : ""}`}>{+d.date.slice(8)}</span>
            </button>
            {!work && <div className="text-[11.5px] text-muted">Выходной</div>}
            <div className="flex flex-col gap-1.5">
              {d.bookings.map((b) => (
                <button key={b.id} onClick={() => onOpen(b)} className={`rounded-xl px-2 py-1.5 text-left text-[11.5px] ${b.status === "pending" ? "bg-warn/15" : "bg-soft"}`}>
                  <b className="tabular-nums">{b.start.slice(11, 16)}</b> {b.name}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MonthView({ days, anchor, onDay }: { days: CalDay[]; anchor: string; onDay: (d: string) => void }) {
  const m = parseIso(anchor).getMonth();
  return (
    <div className="card p-3">
      <div className="grid grid-cols-7 gap-1 text-center">
        {WD_SHORT.map((w) => <div key={w} className="pb-2 text-[11px] font-semibold text-muted">{w}</div>)}
        {days.map((d) => {
          const inMonth = parseIso(d.date).getMonth() === m;
          const work = Object.values(d.windows).some((w) => w.length);
          const n = d.bookings.length;
          const pending = d.bookings.some((b) => b.status === "pending");
          return (
            <button key={d.date} onClick={() => onDay(d.date)}
              className={`flex aspect-square flex-col items-center justify-center rounded-2xl text-[14px] transition-colors ${!inMonth ? "opacity-25" : ""} ${work ? "bg-surface ring-1 ring-line" : "bg-soft text-muted"} ${d.date === today() ? "ring-2 ring-accent" : ""}`}>
              <span className="font-semibold">{+d.date.slice(8)}</span>
              {n > 0 && <span className={`mt-0.5 rounded-full px-1.5 text-[10px] font-semibold ${pending ? "bg-warn/20 text-warn" : "bg-primary/15 text-accent"}`}>{n}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
