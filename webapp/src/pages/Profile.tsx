import { motion } from "framer-motion";
import { CalendarPlus, Clock, Crown, MapPin, MessageCircle, Moon, Phone, RotateCcw, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar, Button, Empty, Photo, SectionTitle, Sheet, Skeleton, StatusBadge, Tap, itemV, listV } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import { openLink } from "../services/telegram";
import type { Booking } from "../types";
import { MONTHS_SHORT, WD, hdate, parseIso, plural, relDay, rub, time } from "../utils/format";

export function Profile() {
  const { boot, startBooking, toast, theme, toggleTheme } = useApp();
  const b = boot!;
  const [data, setData] = useState<{ active: Booking[]; history: Booking[] } | null>(null);
  const [cancel, setCancel] = useState<Booking | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get<{ active: Booking[]; history: Booking[] }>("/api/my").then(setData).catch((e) => { toast(errorText(e)); setData({ active: [], history: [] }); });
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const doCancel = async () => {
    if (!cancel) return;
    setBusy(true);
    try { await api.post("/api/cancel", { id: cancel.id }); toast("Запись отменена"); setCancel(null); load(); }
    catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };

  const next = data?.active[0];
  const done = data?.history.filter((x) => x.status === "done") || [];
  const spent = done.reduce((a, x) => a + x.price, 0);
  const master = next ? b.masters.find((m) => m.id === next.master_id) : b.masters[0];
  const st = b.studio;
  const name = b.user.name || b.user.first_name || "Гостья";

  return (
    <motion.div className="page" initial="hidden" animate="show" variants={listV}>
      <motion.div variants={itemV} className="mt-2 flex items-center gap-4">
        <Avatar src={b.user.photo_url} name={name} size={64} />
        <div className="min-w-0 flex-1">
          <h1 className="h-display truncate text-[34px]">{name}</h1>
          <div className="text-[13px] text-muted">{b.user.phone || "Телефон появится после первой записи"}</div>
        </div>
        <Tap onClick={toggleTheme} aria-label="Сменить тему" className="grid h-10 w-10 place-items-center rounded-full bg-surface text-muted shadow-card">
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </Tap>
      </motion.div>

      <motion.div variants={itemV} className="mt-5 grid grid-cols-3 gap-2.5">
        {[[String(done.length), plural(done.length, "визит", "визита", "визитов")], [String(data?.active.length ?? "–"), "впереди"], [spent ? rub(spent) : "–", "вложено в себя"]].map(([v, l]) => (
          <div key={l} className="card px-3 py-3.5 text-center">
            <div className="font-display text-[22px] font-semibold leading-none">{v}</div>
            <div className="mt-1 text-[11px] text-muted">{l}</div>
          </div>
        ))}
      </motion.div>

      {/* ближайшая запись */}
      <SectionTitle title="Ближайшая запись" />
      {data === null ? <Skeleton className="h-56" /> : next ? (
        <motion.div variants={itemV} className="relative overflow-hidden rounded-[30px] bg-gradient-to-br from-primary to-accent p-5 text-white shadow-lift">
          <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
          <div className="relative flex items-start justify-between gap-3">
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-white/70">{relDay(next.date)}</div>
              <div className="h-display mt-1 text-[44px] leading-none">{time(next.start)}</div>
              <div className="mt-1 text-[14px] text-white/85">{parseIso(next.date).getDate()} {MONTHS_SHORT[parseIso(next.date).getMonth()]}, {WD[parseIso(next.date).getDay()]}</div>
            </div>
            <span className="rounded-full bg-white/20 px-3 py-1.5 text-[11.5px] font-semibold backdrop-blur">{next.status === "confirmed" ? "Подтверждена" : "Ждёт подтверждения"}</span>
          </div>
          <div className="relative mt-5 rounded-2xl bg-white/15 p-3.5 backdrop-blur">
            <div className="text-[15px] font-semibold">{next.service_title}</div>
            <div className="mt-0.5 text-[12.5px] text-white/80">{next.master_name ? `Мастер ${next.master_name} · ` : ""}{rub(next.price, next.price_from)}</div>
          </div>
          <div className="relative mt-4 grid grid-cols-3 gap-2 [&>button]:px-2">
            <Button variant="light" size="sm" onClick={() => startBooking({ reschedule: next })}>Перенести</Button>
            <Button variant="light" size="sm" onClick={() => next.ics && openLink(next.ics)}><CalendarPlus size={14} />Календарь</Button>
            <Button variant="light" size="sm" className="!text-danger" onClick={() => setCancel(next)}>Отменить</Button>
          </div>
        </motion.div>
      ) : (
        <Empty title="Пока нет записей" text="Самое время позаботиться о себе" action={<Button onClick={() => startBooking()}>Записаться</Button>} />
      )}

      {data && data.active.length > 1 && (
        <div className="mt-3 flex flex-col gap-2.5">
          {data.active.slice(1).map((x) => (
            <motion.div key={x.id} variants={itemV} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div><div className="text-[15px] font-semibold">{hdate(x.date)}, {time(x.start)}</div><div className="text-[12.5px] text-muted">{x.service_title}{x.master_name ? ` · ${x.master_name}` : ""}</div></div>
                <StatusBadge status={x.status} />
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="soft" onClick={() => startBooking({ reschedule: x })}>Перенести</Button>
                <Button size="sm" variant="ghost" onClick={() => setCancel(x)}>Отменить</Button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* мастер */}
      {master && <>
        <SectionTitle title="Ваш мастер" />
        <motion.div variants={itemV} className="card flex items-center gap-4 p-4">
          <Photo src={master.photo || st.about_photo} seed={1} className="h-20 w-20 shrink-0 rounded-[22px]" />
          <div className="min-w-0">
            <div className="h-display text-[24px]">{master.name}</div>
            <div className="text-[12px] font-semibold text-primary">{master.role}</div>
            <p className="mt-1 line-clamp-2 text-[12.5px] text-muted">{master.bio}</p>
          </div>
        </motion.div>
      </>}

      {/* история */}
      <SectionTitle title="История" />
      {data === null ? <Skeleton className="h-32" /> : data.history.length === 0 ? <p className="text-[13.5px] text-muted">Здесь появятся прошедшие визиты</p> : (
        <div className="card divide-y divide-line px-4">
          {data.history.slice(0, 20).map((x) => {
            const again = x.status === "done" && b.services.some((s) => s.id === x.service_id);
            return (
              <div key={x.id} className="flex items-center gap-3 py-3.5">
                <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-soft text-center leading-none">
                  <div><div className="text-[15px] font-semibold">{parseIso(x.date).getDate()}</div><div className="text-[10px] text-muted">{MONTHS_SHORT[parseIso(x.date).getMonth()]}</div></div>
                </div>
                <div className="min-w-0 flex-1"><div className="truncate text-[14px] font-semibold">{x.service_title}</div><div className="text-[12px] text-muted">{x.status === "done" ? rub(x.price) : x.status === "cancelled" ? "Отменена" : "Не состоялась"}</div></div>
                {again && <Tap onClick={() => startBooking({ serviceId: x.service_id!, masterId: x.master_id })} className="flex items-center gap-1 rounded-full bg-soft px-3 py-2 text-[12px] font-semibold text-accent"><RotateCcw size={13} />Повторить</Tap>}
              </div>
            );
          })}
        </div>
      )}

      {/* контакты */}
      <SectionTitle title="Контакты" />
      <div className="card divide-y divide-line overflow-hidden">
        <Tap onClick={() => st.map_url && openLink(st.map_url)} className="flex w-full items-center gap-4 p-4"><MapPin size={19} className="text-primary" /><div><div className="text-[14px] font-semibold">{st.address}</div><div className="text-[12px] text-muted">{st.address_hint}</div></div></Tap>
        {st.contact_username && <Tap onClick={() => openLink(`https://t.me/${st.contact_username}`)} className="flex w-full items-center gap-4 p-4"><MessageCircle size={19} className="text-primary" /><div className="text-[14px] font-semibold">Написать в Telegram</div></Tap>}
        {st.contact_phone && <div className="flex items-center gap-4 p-4"><Phone size={19} className="text-primary" /><div className="select-all text-[14px] font-semibold">{st.contact_phone}</div></div>}
        <div className="flex items-start gap-4 p-4"><Clock size={19} className="mt-0.5 shrink-0 text-primary" /><div className="text-[12.5px] leading-relaxed text-muted">{st.cancel_rules}</div></div>
      </div>

      {b.user.is_admin && (
        <Tap onClick={() => { if (import.meta.env.MODE === "demo") location.hash = "admin"; else location.href = "/admin"; }}
          className="mt-6 flex w-full items-center gap-4 rounded-[26px] bg-ink p-5 text-bg">
          <Crown size={22} /><div><div className="text-[15px] font-semibold">Админ-панель</div><div className="text-[12px] opacity-70">Записи, календарь, услуги и статистика</div></div>
        </Tap>
      )}

      <Sheet open={!!cancel} onClose={() => setCancel(null)} title="Отменить запись?">
        {cancel && <>
          <p className="text-[14.5px] text-ink/75">{cancel.service_title}, {hdate(cancel.date)} в {time(cancel.start)}. Окно освободится для других — может, лучше перенести?</p>
          <Button size="lg" className="mt-5 w-full" onClick={() => { const c = cancel; setCancel(null); startBooking({ reschedule: c }); }}>Перенести</Button>
          <Button size="lg" variant="danger" className="mt-2.5 w-full" disabled={busy} onClick={doCancel}>{busy ? "Отменяю…" : "Да, отменить"}</Button>
        </>}
      </Sheet>
    </motion.div>
  );
}
