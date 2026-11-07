import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Skeleton, spring } from "../components/ui";
import { haptic } from "../services/telegram";
import type { DayState } from "../types";
import { MONTHS_NOM, WD_SHORT, pad } from "../utils/format";

export interface MonthData { ym: string; days: Record<string, DayState>; min: string; max: string }

export const shiftYm = (ym: string, d: number) => {
  let [y, m] = ym.split("-").map(Number);
  m += d;
  if (m > 12) { m = 1; y++; }
  if (m < 1) { m = 12; y--; }
  return `${y}-${pad(m)}`;
};

export function Calendar({ month, selected, onSelect, onMonth, loading }: {
  month: MonthData | null; selected: string | null; onSelect: (iso: string) => void; onMonth: (ym: string) => void; loading: boolean;
}) {
  if (!month) return <Skeleton className="h-[340px] w-full rounded-[28px]" />;
  const [y, m] = month.ym.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const days = new Date(y, m, 0).getDate();
  const lead = (first.getDay() + 6) % 7;
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between px-1">
        <button disabled={month.ym <= month.min} onClick={() => onMonth(shiftYm(month.ym, -1))} aria-label="Предыдущий месяц"
          className="grid h-9 w-9 place-items-center rounded-full bg-soft text-ink disabled:opacity-30"><ChevronLeft size={18} /></button>
        <motion.div key={month.ym} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="h-display text-[24px]">
          {MONTHS_NOM[m - 1]} <span className="text-muted">{y}</span>
        </motion.div>
        <button disabled={month.ym >= month.max} onClick={() => onMonth(shiftYm(month.ym, 1))} aria-label="Следующий месяц"
          className="grid h-9 w-9 place-items-center rounded-full bg-soft text-ink disabled:opacity-30"><ChevronRight size={18} /></button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center">
        {WD_SHORT.map((w) => <div key={w} className="pb-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted">{w}</div>)}
        {Array.from({ length: lead }, (_, i) => <span key={`e${i}`} />)}
        {Array.from({ length: days }, (_, i) => {
          const d = i + 1;
          const iso = `${month.ym}-${pad(d)}`;
          const st = month.days[String(d)] || "past";
          const sel = selected === iso;
          const free = st === "free";
          return (
            <button key={iso} disabled={!free || loading} onClick={() => { haptic.select(); onSelect(iso); }}
              aria-label={`${d}`} aria-pressed={sel}
              className={`relative mx-auto grid aspect-square w-full max-w-[46px] place-items-center rounded-2xl text-[14.5px] transition-colors
                ${free ? "font-semibold text-ink" : st === "busy" ? "text-muted/70 line-through decoration-primary/40" : "text-muted/35"}`}>
              {sel && <motion.span layoutId="day-sel" transition={spring} className="absolute inset-0 rounded-2xl bg-accent shadow-[0_8px_18px_-8px_rgb(var(--accent)/.8)]" />}
              <span className={`relative ${sel ? "text-white dark:text-bg" : ""}`}>{d}</span>
              {free && !sel && <span className="absolute bottom-1.5 h-1 w-1 rounded-full bg-primary" />}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex justify-center gap-4 text-[11px] text-muted">
        <span className="flex items-center gap-1.5"><i className="h-1.5 w-1.5 rounded-full bg-primary" />есть окна</span>
        <span className="flex items-center gap-1.5"><i className="h-px w-3 bg-primary/50" />занято</span>
        <span className="flex items-center gap-1.5 opacity-60">выходной</span>
      </div>
    </div>
  );
}
