import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, CalendarPlus, Check, Clock, MapPin, Sparkles, UserRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Empty, Field, Photo, Sheet, Skeleton, Tap, ease, itemV, listV, spring } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { ApiError, api, errorText } from "../services/api";
import { haptic, openLink, setBackButton } from "../services/telegram";
import type { Booking, Service, Slot } from "../types";
import { dur, fmtPhone, hdate, rub, today } from "../utils/format";
import { Calendar, shiftYm, type MonthData } from "./Calendar";

type Step = "service" | "master" | "date" | "time" | "contacts" | "confirm" | "done";

export function BookingFlow() {
  const { boot, intent, toast, go, setBoot } = useApp();
  const b = boot!;
  const resched = intent?.reschedule || null;
  const [step, setStep] = useState<Step>("service");
  const [dir, setDir] = useState(1);
  const [svc, setSvc] = useState<Service | null>(null);
  const [master, setMaster] = useState<number | null>(null); // null = любой мастер
  const [month, setMonth] = useState<MonthData | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [name, setName] = useState(b.user.name || b.user.first_name || "");
  const [phone, setPhone] = useState(b.user.phone || "");
  const [comment, setComment] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Booking | null>(null);
  const [subUrl, setSubUrl] = useState<string | null>(null);

  const mastersFor = useCallback((s: Service) => b.masters.filter((m) => s.master_ids.includes(m.id)), [b]);
  const steps: Step[] = useMemo(() => {
    if (resched) return ["date", "time", "confirm"];
    const withMaster = svc ? mastersFor(svc).length > 1 : b.masters.length > 1;
    return ["service", ...(withMaster ? ["master" as Step] : []), "date", "time", "contacts", "confirm"];
  }, [resched, svc, b.masters.length, mastersFor]);

  const query = (extra: string) => resched ? `resched=${resched.id}&${extra}` : `service=${svc!.id}&master=${master ?? "any"}&${extra}`;

  const loadMonth = useCallback(async (ym: string, auto = false) => {
    setMonth(null);
    try {
      const r = await api.get<Omit<MonthData, "ym">>(`/api/month?${query(`ym=${ym}`)}`);
      if (auto && !Object.values(r.days).includes("free") && ym < r.max) return loadMonth(shiftYm(ym, 1), false);
      setMonth({ ym, ...r });
    } catch (e) { toast(errorText(e)); }
  }, [svc, master, resched]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSlots = useCallback(async (d: string) => {
    setSlots(null);
    try { setSlots((await api.get<{ slots: Slot[] }>(`/api/slots?${query(`date=${d}`)}`)).slots); }
    catch (e) { toast(errorText(e)); setSlots([]); }
  }, [svc, master, resched]); // eslint-disable-line react-hooks/exhaustive-deps

  /* старт: из баннера, карточки услуги, «ближайшего окна» или переноса */
  useEffect(() => {
    setDone(null); setErr(null); setTime(null); setDate(null); setSlots(null); setMonth(null); setDir(1);
    if (intent?.reschedule) {
      const s = b.services.find((x) => x.id === intent.reschedule!.service_id) || null;
      setSvc(s || ({ id: intent.reschedule.service_id, title: intent.reschedule.service_title, price: intent.reschedule.price, price_from: intent.reschedule.price_from, duration: intent.reschedule.duration, photo: null, master_ids: [], category: "", description: "", active: true } as Service));
      setStep("date");
      return;
    }
    const s = intent?.serviceId ? b.services.find((x) => x.id === intent.serviceId) || null : null;
    setSvc(s);
    setMaster(intent?.masterId ?? null);
    if (!s) { setStep("service"); return; }
    if (intent?.date) { setDate(intent.date); setStep(intent.time ? "time" : "date"); if (intent.time) setTime(intent.time); return; }
    setStep(mastersFor(s).length > 1 ? "master" : "date");
  }, [intent]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if ((step === "date" || step === "time") && (svc || resched) && !month) {
      const ym = (date || today()).slice(0, 7);
      loadMonth(ym, !date);
    }
    if (step === "time" && date && !slots) loadSlots(date);
  }, [step, svc, resched, date]); // eslint-disable-line react-hooks/exhaustive-deps

  const idx = steps.indexOf(step);
  const goStep = (s: Step) => { setDir(steps.indexOf(s) >= idx ? 1 : -1); setStep(s); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const back = useCallback(() => {
    if (step === "done") return;
    if (idx <= 0) { go(resched ? "me" : "home"); return; }
    setDir(-1);
    setStep(steps[idx - 1]);
  }, [step, idx, steps, go, resched]);
  useEffect(() => { setBackButton(step === "done" ? null : back); return () => setBackButton(null); }, [back, step]);

  const pickService = (s: Service) => { haptic.tap(); setSvc(s); setMaster(null); setMonth(null); setDate(null); setTime(null); setSlots(null); setDir(1); setStep(mastersFor(s).length > 1 ? "master" : "date"); };
  const pickMaster = (id: number | null) => { haptic.tap(); setMaster(id); setMonth(null); setDate(null); setTime(null); setSlots(null); goStep("date"); };
  const pickDate = (d: string) => { setDate(d); setTime(null); setSlots(null); loadSlots(d); setDir(1); setStep("time"); };

  const submit = async () => {
    if (!svc || !date || !time) return;
    setBusy(true);
    try {
      const r = resched
        ? await api.post<{ booking: Booking }>("/api/reschedule", { id: resched.id, date, time })
        : await api.post<{ booking: Booking }>("/api/book", { service: svc.id, master, date, time, name, phone, comment });
      haptic.success();
      setDone(r.booking);
      setBoot((x) => ({ ...x, user: { ...x.user, name, phone: r.booking.phone || x.user.phone } }));
      setDir(1);
      setStep("done");
    } catch (e) {
      haptic.error();
      if (e instanceof ApiError && e.message === "subscribe") { setSubUrl(String(e.data.channel_url || "")); return; }
      if (e instanceof ApiError && e.message === "slot_taken") { toast(errorText(e)); setTime(null); loadSlots(date); goStep("time"); return; }
      if (e instanceof ApiError && e.message === "phone") { setErr(errorText(e)); goStep("contacts"); return; }
      toast(errorText(e));
    } finally { setBusy(false); }
  };

  const checkSub = async () => {
    try {
      const r = await api.post<{ subscribed: boolean }>("/api/sub");
      if (r.subscribed) { setSubUrl(null); toast("Спасибо за подписку!"); submit(); } else toast("Подписки пока нет");
    } catch (e) { toast(errorText(e)); }
  };

  const mName = (id: number | null | undefined) => b.masters.find((m) => m.id === id)?.name;
  const slotGroups = useMemo(() => {
    const g: Record<string, Slot[]> = { "Утро": [], "День": [], "Вечер": [] };
    (slots || []).forEach((s) => { const h = +s.time.slice(0, 2); g[h < 12 ? "Утро" : h < 17 ? "День" : "Вечер"].push(s); });
    return Object.entries(g).filter(([, v]) => v.length);
  }, [slots]);

  const title: Record<Step, string> = {
    service: "Выбери услугу", master: "Выбери мастера", date: resched ? "Новая дата" : "Выбери дату", time: "Свободное время",
    contacts: "Контакты", confirm: resched ? "Перенос записи" : "Проверь запись", done: "",
  };

  return (
    <div className="page">
      {step !== "done" && (
        <div className="mb-5">
          <div className="flex items-center gap-3">
            <Tap onClick={back} aria-label="Назад" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface shadow-card"><ArrowLeft size={18} /></Tap>
            <div className="eyebrow">{resched ? "Перенос" : "Онлайн-запись"} · шаг {idx + 1} из {steps.length}</div>
          </div>
          <div className="mt-4 flex gap-1.5">
            {steps.map((s, i) => (
              <div key={s} className="h-1 flex-1 overflow-hidden rounded-full bg-line">
                <motion.div className="h-full rounded-full bg-gradient-to-r from-primary to-accent" initial={false}
                  animate={{ width: i <= idx ? "100%" : "0%" }} transition={{ duration: 0.5, ease }} />
              </div>
            ))}
          </div>
          <motion.h1 key={step} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease }} className="h-display mt-5 text-[38px]">{title[step]}</motion.h1>
          {svc && step !== "service" && (
            <div className="mt-3 flex items-center gap-3 rounded-[22px] bg-soft p-2.5 pr-4">
              <Photo src={svc.photo} seed={svc.id} className="h-12 w-12 shrink-0 rounded-2xl" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] font-semibold">{svc.title}</div>
                <div className="truncate text-[12px] text-muted">{dur(svc.duration)}{master ? ` · ${mName(master)}` : ""}{date ? ` · ${hdate(date, false)}` : ""}{time ? ` в ${time}` : ""}</div>
              </div>
              <div className="font-display text-[19px] font-semibold">{rub(svc.price, svc.price_from)}</div>
            </div>
          )}
        </div>
      )}

      <AnimatePresence mode="wait" custom={dir} initial={false}>
        <motion.div key={step} custom={dir}
          initial={{ opacity: 0, x: dir * 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: dir * -28 }}
          transition={{ duration: 0.38, ease }}>

          {step === "service" && (
            <motion.div initial="hidden" animate="show" variants={listV}>
              {b.categories.filter((c) => c.count > 0).map((c) => (
                <section key={c.id} className="mb-6">
                  <div className="eyebrow mb-2.5">{c.title}</div>
                  <div className="flex flex-col gap-2.5">
                    {b.services.filter((s) => s.category === c.id).map((s) => (
                      <motion.div key={s.id} variants={itemV}>
                        <Tap onClick={() => pickService(s)} className="card flex w-full items-center gap-3.5 p-3">
                          <Photo src={s.photo} seed={s.id} className="h-16 w-16 shrink-0 rounded-[18px]" />
                          <div className="min-w-0 flex-1">
                            <div className="text-[15px] font-semibold leading-snug">{s.title}</div>
                            <div className="mt-0.5 flex items-center gap-1 text-[12px] text-muted"><Clock size={12} />{dur(s.duration)}</div>
                          </div>
                          <div className="font-display text-[20px] font-semibold">{rub(s.price, s.price_from)}</div>
                        </Tap>
                      </motion.div>
                    ))}
                  </div>
                </section>
              ))}
            </motion.div>
          )}

          {step === "master" && svc && (
            <motion.div initial="hidden" animate="show" variants={listV} className="flex flex-col gap-3">
              <motion.div variants={itemV}>
                <Tap onClick={() => pickMaster(null)} className={`card flex w-full items-center gap-4 p-4 ${master === null ? "ring-2 ring-primary" : ""}`}>
                  <div className="grid h-16 w-16 shrink-0 place-items-center rounded-[20px] bg-gradient-to-br from-secondary to-primary text-white"><Sparkles size={24} /></div>
                  <div><div className="h-display text-[23px]">Любой мастер</div><div className="text-[12.5px] text-muted">Покажем все свободные окна</div></div>
                </Tap>
              </motion.div>
              {mastersFor(svc).map((m, i) => (
                <motion.div key={m.id} variants={itemV}>
                  <Tap onClick={() => pickMaster(m.id)} className={`card flex w-full items-center gap-4 p-4 ${master === m.id ? "ring-2 ring-primary" : ""}`}>
                    <Photo src={m.photo} seed={i + 1} className="h-16 w-16 shrink-0 rounded-[20px]" />
                    <div className="min-w-0"><div className="h-display text-[23px]">{m.name}</div><div className="text-[12px] font-semibold text-primary">{m.role}</div>
                      <p className="line-clamp-1 text-[12.5px] text-muted">{m.bio}</p></div>
                  </Tap>
                </motion.div>
              ))}
            </motion.div>
          )}

          {step === "date" && (
            <Calendar month={month} selected={date} onSelect={pickDate} onMonth={(ym) => loadMonth(ym)} loading={false} />
          )}

          {step === "time" && (
            <div>
              {date && <div className="mb-4 flex items-center justify-between">
                <div className="text-[15px] font-semibold">{hdate(date)}</div>
                <button onClick={() => goStep("date")} className="text-[13px] font-semibold text-primary">Другая дата</button>
              </div>}
              {slots === null ? <div className="grid grid-cols-4 gap-2">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-12" />)}</div> :
                slots.length === 0 ? <Empty title="Окон не осталось" text="Выбери другой день — свободные отмечены точкой" action={<Button variant="soft" onClick={() => goStep("date")}>К календарю</Button>} /> :
                  slotGroups.map(([label, list]) => (
                    <section key={label} className="mb-5">
                      <div className="eyebrow mb-2.5">{label}</div>
                      <motion.div initial="hidden" animate="show" variants={listV} className="grid grid-cols-4 gap-2">
                        {list.map((s) => {
                          const on = time === s.time;
                          return (
                            <motion.button key={s.time} variants={itemV} whileTap={{ scale: 0.94 }}
                              onClick={() => { haptic.select(); setTime(s.time); }}
                              className={`relative h-12 rounded-2xl text-[15px] font-semibold tabular-nums transition-colors ${on ? "text-white dark:text-bg" : "bg-surface text-ink shadow-card"}`}>
                              {on && <motion.span layoutId="slot-sel" transition={spring} className="absolute inset-0 rounded-2xl bg-accent" />}
                              <span className="relative">{s.time}</span>
                            </motion.button>
                          );
                        })}
                      </motion.div>
                    </section>
                  ))}
              <AnimatePresence>
                {time && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }} className="sticky bottom-28 mt-4">
                    <Button size="lg" className="w-full" onClick={() => goStep(resched ? "confirm" : "contacts")}>Продолжить · {time}</Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {step === "contacts" && (
            <form onSubmit={(e) => {
              e.preventDefault();
              const p = fmtPhone(phone);
              const digits = p.replace(/\D/g, "");
              if (name.trim().length < 2) return setErr("Напиши, пожалуйста, имя");
              if (digits.length < 11 || digits.length > 15) return setErr("Проверь номер телефона");
              setPhone(p); setErr(null); goStep("confirm");
            }}>
              <Field label="Имя"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Как к тебе обращаться" autoComplete="given-name" maxLength={40} /></Field>
              <Field label="Телефон"><input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+7 900 123-45-67" inputMode="tel" autoComplete="tel" /></Field>
              <Field label="Комментарий" hint="Пожелания по дизайну, длине или форме"><textarea className="input min-h-[96px] resize-none" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} /></Field>
              {err && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-3 ml-1 text-[13px] text-danger">{err}</motion.p>}
              <Button size="lg" className="w-full" type="submit">Дальше</Button>
            </form>
          )}

          {step === "confirm" && svc && date && time && (
            <div>
              <div className="card overflow-hidden">
                <Photo src={svc.photo} seed={svc.id} className="h-40 w-full" />
                <div className="divide-y divide-line px-5">
                  <Row icon={<Sparkles size={17} />} k="Услуга" v={svc.title} />
                  <Row icon={<UserRound size={17} />} k="Мастер" v={master ? mName(master)! : resched?.master_name || "Любой свободный"} />
                  <Row icon={<CalendarPlus size={17} />} k="Дата и время" v={`${hdate(date)}, ${time}`} />
                  <Row icon={<Clock size={17} />} k="Длительность" v={dur(svc.duration)} />
                  <Row icon={<MapPin size={17} />} k="Адрес" v={b.studio.address} />
                  {!resched && <Row icon={<UserRound size={17} />} k="Контакты" v={`${name}, ${phone}`} />}
                </div>
                <div className="flex items-center justify-between bg-soft px-5 py-4">
                  <span className="text-[13px] font-semibold text-muted">Стоимость</span>
                  <span className="font-display text-[26px] font-semibold">{rub(svc.price, svc.price_from)}</span>
                </div>
              </div>
              <p className="mt-4 px-1 text-[12px] leading-relaxed text-muted">{b.studio.cancel_rules}</p>
              <Button size="lg" className="mt-5 w-full" disabled={busy} onClick={submit}>
                {busy ? "Записываю…" : resched ? "Перенести запись" : "Подтвердить запись"}
              </Button>
            </div>
          )}

          {step === "done" && done && <Success b={done} masterName={done.master_name || mName(done.master_id) || ""} address={b.studio.address} onMy={() => go("me")} onHome={() => go("home")} resched={!!resched} />}
        </motion.div>
      </AnimatePresence>

      <Sheet open={subUrl !== null} onClose={() => setSubUrl(null)} title="Маленькая просьба ♡">
        <p className="text-[14.5px] leading-relaxed text-ink/75">Подпишись на мой Telegram-канал, чтобы не пропускать свободные окошки, новые работы и специальные предложения. После подписки запись завершится автоматически.</p>
        {subUrl && <Button size="lg" className="mt-5 w-full" onClick={() => openLink(subUrl)}>Подписаться на канал</Button>}
        <Button size="lg" variant="ghost" className="mt-2.5 w-full" onClick={checkSub}>Я подписалась</Button>
      </Sheet>
    </div>
  );
}

function Row({ icon, k, v }: { icon: React.ReactNode; k: string; v: string }) {
  return (
    <div className="flex items-start gap-3 py-3.5">
      <span className="mt-0.5 text-primary">{icon}</span>
      <span className="w-28 shrink-0 text-[13px] text-muted">{k}</span>
      <span className="min-w-0 flex-1 text-right text-[14px] font-semibold">{v}</span>
    </div>
  );
}

function Success({ b, masterName, address, onMy, onHome, resched }: { b: Booking; masterName: string; address: string; onMy: () => void; onHome: () => void; resched: boolean }) {
  return (
    <div className="pt-6 text-center">
      <div className="relative mx-auto h-28 w-28">
        {Array.from({ length: 8 }, (_, i) => (
          <motion.span key={i} className="absolute left-1/2 top-1/2 h-2 w-2 rounded-full bg-primary"
            initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
            animate={{ x: Math.cos((i / 8) * Math.PI * 2) * 74, y: Math.sin((i / 8) * Math.PI * 2) * 74, opacity: [0, 1, 0], scale: [0.4, 1, 0.6] }}
            transition={{ duration: 1.3, delay: 0.35, ease }} />
        ))}
        <motion.div initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 260, damping: 16 }}
          className="grid h-28 w-28 place-items-center rounded-full bg-gradient-to-br from-primary to-accent text-white shadow-lift">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <motion.path d="M5 12.5l4.5 4.5L19 7.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, delay: 0.3, ease }} />
          </svg>
        </motion.div>
      </div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4, duration: 0.6, ease }}>
        <h1 className="h-display mt-6 text-[36px]">{resched ? "Запись перенесена 🤍" : "Вы успешно записаны! 🤍"}</h1>
        <p className="mt-2 text-[14px] text-muted">{b.status === "pending" ? "Мастер подтвердит запись — уведомление придёт в чат" : "Ждём вас в студии"}</p>
        <div className="card mt-6 divide-y divide-line px-5 text-left">
          <Row icon={<Sparkles size={17} />} k="Услуга" v={b.service_title} />
          {masterName && <Row icon={<UserRound size={17} />} k="Мастер" v={masterName} />}
          <Row icon={<CalendarPlus size={17} />} k="Дата" v={hdate(b.date)} />
          <Row icon={<Clock size={17} />} k="Время" v={b.start.slice(11, 16)} />
          <Row icon={<Check size={17} />} k="Стоимость" v={rub(b.price, b.price_from)} />
          <Row icon={<MapPin size={17} />} k="Адрес" v={address} />
        </div>
        <div className="mt-6 grid gap-2.5">
          {b.ics && <Button size="lg" variant="soft" onClick={() => openLink(b.ics!)}><CalendarPlus size={18} />Добавить в календарь</Button>}
          <Button size="lg" onClick={onMy}>Мои записи</Button>
          <Button size="lg" variant="plain" onClick={onHome}>На главную</Button>
        </div>
      </motion.div>
    </div>
  );
}
