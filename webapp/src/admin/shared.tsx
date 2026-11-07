import { motion } from "framer-motion";
import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Photo, ease } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import type { Booking } from "../types";
import { MONTHS_SHORT, rub, time } from "../utils/format";

/** Простой загрузчик данных с перезагрузкой. */
export function useLoad<T>(url: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    api.get<T>(url).then((d) => alive && (setData(d), setErr(null))).catch((e) => alive && setErr(errorText(e)));
    return () => { alive = false; };
  }, [url, tick, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err, reload: () => setTick((t) => t + 1), setData };
}

export function Kpi({ label, value, hint, accent = false }: { label: string; value: string | number; hint?: string; accent?: boolean }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}
      className={`rounded-[26px] p-4 ${accent ? "bg-gradient-to-br from-primary to-accent text-white shadow-lift" : "card"}`}>
      <div className={`text-[12px] font-medium ${accent ? "text-white/75" : "text-muted"}`}>{label}</div>
      <div className="mt-1.5 font-display text-[32px] font-semibold leading-none tabular-nums">{value}</div>
      {hint && <div className={`mt-1.5 text-[11.5px] ${accent ? "text-white/70" : "text-muted"}`}>{hint}</div>}
    </motion.div>
  );
}

/** Столбчатая диаграмма (SVG): значения подписаны, ось общая для всех столбцов. */
export function BarChart({ data, format = (v: number) => String(v), height = 170 }: {
  data: { label: string; value: number }[]; format?: (v: number) => string; height?: number;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const w = 100 / data.length;
  return (
    <div className="relative" style={{ height }}>
      <div className="absolute inset-x-0 top-0 flex h-[calc(100%-22px)] items-end">
        {data.map((d, i) => (
          <div key={d.label + i} className="flex h-full flex-col items-center justify-end" style={{ width: `${w}%` }}>
            <span className="mb-1 text-[10px] font-semibold tabular-nums text-muted">{d.value ? format(d.value) : ""}</span>
            <motion.div className="w-[62%] max-w-[34px] rounded-t-[10px] rounded-b-[4px] bg-gradient-to-t from-primary/70 to-accent"
              initial={{ height: 0 }} animate={{ height: `${Math.max(d.value ? 3 : 0, (d.value / max) * 82)}%` }}
              transition={{ duration: 0.8, delay: i * 0.04, ease }} />
          </div>
        ))}
      </div>
      <div className="absolute inset-x-0 bottom-0 flex">
        {data.map((d, i) => <span key={i} className="truncate text-center text-[10.5px] text-muted" style={{ width: `${w}%` }}>{d.label}</span>)}
      </div>
    </div>
  );
}

export const monthLabel = (ym: string) => MONTHS_SHORT[+ym.slice(5, 7) - 1];

export function Panel({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card min-w-0 p-4 ${className}`}>
      {(title || action) && <div className="mb-3 flex items-center justify-between gap-3">{title && <h3 className="h-display text-[22px]">{title}</h3>}{action}</div>}
      {children}
    </section>
  );
}

export function BookingRow({ b, onClick, showDate = true }: { b: Booking; onClick?: () => void; showDate?: boolean }) {
  const color = { pending: "bg-warn", confirmed: "bg-ok", done: "bg-muted", cancelled: "bg-danger", expired: "bg-muted" }[b.status] || "bg-muted";
  return (
    <button onClick={onClick} className="flex w-full items-center gap-3 py-3 text-left">
      <div className="w-14 shrink-0 text-center">
        <div className="text-[15px] font-semibold tabular-nums">{time(b.start)}</div>
        {showDate && <div className="text-[10.5px] text-muted">{+b.date.slice(8)} {MONTHS_SHORT[+b.date.slice(5, 7) - 1]}</div>}
      </div>
      <span className={`h-9 w-1 shrink-0 rounded-full ${color}`} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold">{b.name}</div>
        <div className="truncate text-[12px] text-muted">{b.service_title}{b.master_name ? ` · ${b.master_name}` : ""}</div>
      </div>
      <div className="shrink-0 text-[13px] font-semibold tabular-nums">{rub(b.price)}</div>
    </button>
  );
}

/** Загрузка фото: показывает превью, отдаёт значение для сохранения (upload:...). */
export function PhotoInput({ value, url, onChange, className = "h-40 w-full", label = "Загрузить фото" }: {
  value: string | null; url: string | null; onChange: (value: string | null, url: string | null) => void; className?: string; label?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const { toast } = useApp();
  const pick = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    try { const r = await api.upload(f); onChange(r.value, r.url); } catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <div className={`relative overflow-hidden rounded-[22px] border border-dashed border-primary/40 bg-soft ${className}`}>
      {url ? <Photo src={url} className="h-full w-full" /> : (
        <button type="button" onClick={() => ref.current?.click()} className="flex h-full w-full flex-col items-center justify-center gap-2 text-[13px] font-semibold text-accent">
          {busy ? <Loader2 className="animate-spin" /> : <ImagePlus size={22} />}{busy ? "Загружаю…" : label}
        </button>
      )}
      {url && (
        <div className="absolute bottom-2 right-2 flex gap-1.5">
          <button type="button" onClick={() => ref.current?.click()} className="rounded-full bg-white/90 px-3 py-1.5 text-[12px] font-semibold text-[#282326]">{busy ? "…" : "Заменить"}</button>
          <button type="button" onClick={() => onChange(null, null)} aria-label="Убрать фото" className="grid h-8 w-8 place-items-center rounded-full bg-white/90 text-danger"><Trash2 size={14} /></button>
        </div>
      )}
      <input ref={ref} type="file" accept="image/*" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      {value && !url && null}
    </div>
  );
}

export function Select({ value, onChange, options, className = "" }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={`input appearance-none bg-[length:16px] pr-10 ${className}`}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23A69A9D' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")", backgroundRepeat: "no-repeat", backgroundPosition: "right 14px center" }}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function DayToggles({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  return (
    <div className="flex gap-1.5">
      {names.map((n, i) => {
        const on = value.includes(i);
        return (
          <button key={n} type="button" onClick={() => onChange(on ? value.filter((x) => x !== i) : [...value, i].sort())}
            className={`h-10 flex-1 rounded-2xl text-[13px] font-semibold transition-colors ${on ? "bg-accent text-white dark:text-bg" : "bg-soft text-muted"}`}>{n}</button>
        );
      })}
    </div>
  );
}
