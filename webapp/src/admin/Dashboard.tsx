import { Skeleton } from "../components/ui";
import type { Booking } from "../types";
import { plural, rub } from "../utils/format";
import type { Section } from "./AdminApp";
import { BarChart, BookingRow, Kpi, Panel, monthLabel, useLoad } from "./shared";

interface Dash {
  today: number; week: number; new_clients: number; revenue_month: number; revenue_total: number; expected: number; pending: number;
  upcoming: Booking[]; months: { month: string; bookings: number; revenue: number }[]; days: { date: string; bookings: number }[];
  top: { title: string; n: number }[];
}

const short = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(".0", "")}к` : String(n);

export function Dashboard({ nav }: { nav: (s: Section, f?: { date?: string; client?: number } | null) => void }) {
  const { data: d } = useLoad<Dash>("/api/admin/dashboard");
  if (!d) return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28" />)}<Skeleton className="h-60 sm:col-span-2" /></div>;
  const topMax = Math.max(1, ...d.top.map((t) => t.n));
  return (
    <div>
      <div className="mb-5 flex items-end justify-between gap-3">
        <div><div className="eyebrow">Обзор</div><h1 className="h-display mt-1 text-[38px]">Добрый день</h1></div>
        {d.pending > 0 && <button onClick={() => nav("bookings")} className="rounded-full bg-warn/15 px-4 py-2 text-[13px] font-semibold text-warn">{d.pending} {plural(d.pending, "заявка ждёт", "заявки ждут", "заявок ждут")}</button>}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Записей сегодня" value={d.today} accent />
        <Kpi label="За неделю" value={d.week} />
        <Kpi label="Новых клиентов" value={d.new_clients} hint="за 30 дней" />
        <Kpi label="Выручка за месяц" value={rub(d.revenue_month)} hint={`всего ${rub(d.revenue_total)} · впереди ${rub(d.expected)}`} />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-5">
        <Panel title="Ближайшие записи" className="lg:col-span-3" action={<button onClick={() => nav("calendar")} className="text-[13px] font-semibold text-primary">Календарь</button>}>
          {d.upcoming.length ? <div className="divide-y divide-line">{d.upcoming.map((b) => <BookingRow key={b.id} b={b} onClick={() => nav("bookings")} />)}</div>
            : <p className="py-6 text-center text-[13.5px] text-muted">Пока нет записей</p>}
        </Panel>
        <Panel title="Популярные услуги" className="lg:col-span-2">
          {d.top.length ? d.top.map((t) => (
            <div key={t.title} className="mb-3">
              <div className="mb-1 flex justify-between text-[13px]"><span className="truncate pr-2 font-medium">{t.title}</span><span className="text-muted tabular-nums">{t.n}</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-soft"><div className="h-full rounded-full bg-gradient-to-r from-primary to-accent" style={{ width: `${(t.n / topMax) * 100}%` }} /></div>
            </div>
          )) : <p className="py-6 text-center text-[13.5px] text-muted">Данные появятся после первых записей</p>}
        </Panel>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Panel title="Выручка по месяцам">
          <BarChart data={d.months.map((m) => ({ label: monthLabel(m.month), value: m.revenue }))} format={short} />
        </Panel>
        <Panel title="Записи по месяцам">
          <BarChart data={d.months.map((m) => ({ label: monthLabel(m.month), value: m.bookings }))} />
        </Panel>
        <Panel title="Последние 14 дней" className="lg:col-span-2">
          <BarChart height={140} data={d.days.map((x) => ({ label: String(+x.date.slice(8)), value: x.bookings }))} />
        </Panel>
      </div>
    </div>
  );
}
