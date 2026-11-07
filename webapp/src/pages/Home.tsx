import { motion } from "framer-motion";
import { ArrowUpRight, CalendarClock, Coffee, Gem, MapPin, MessageCircle, Moon, ShieldCheck, Sparkles, Star, Sun } from "lucide-react";
import { useMemo, useState } from "react";
import { Lightbox } from "../components/Lightbox";
import { Avatar, Button, Photo, SectionTitle, Skeleton, Tap, ease, itemV, listV } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { useWorks } from "../hooks/useWorks";
import { openLink } from "../services/telegram";
import { plural, relDay, rub } from "../utils/format";

const WHY_ICONS = [ShieldCheck, Gem, CalendarClock, Coffee, Sparkles, Star];

export function Home() {
  const { boot, startBooking, go, theme, toggleTheme, setGallerySection } = useApp();
  const works = useWorks("all");
  const [lb, setLb] = useState<number | null>(null);
  const b = boot!;
  const st = b.studio;
  const firstName = (b.user.first_name || b.user.name || "").split(" ")[0];
  const hero = st.hero_photo || works?.[0]?.src || null;

  const cats = useMemo(() => b.categories.filter((c) => c.count > 0).map((c) => ({
    ...c, photo: c.photo || b.services.find((s) => s.category === c.id && s.photo)?.photo || null,
    from: Math.min(...b.services.filter((s) => s.category === c.id).map((s) => s.price)),
  })), [b]);
  const designs = (works || []).filter((w) => ["design", "french", "red", "nude"].includes(w.section)).slice(0, 8);
  const latest = (works || []).slice(0, 4);
  const nearestSvc = b.nearest && b.services.find((s) => s.id === b.nearest!.service_id);

  return (
    <motion.div className="page" initial="hidden" animate="show" variants={listV}>
      {/* верх: студия, приветствие, аватар */}
      <motion.header variants={itemV} className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {st.logo ? <img src={st.logo} alt="" className="h-9 w-9 rounded-full object-cover" /> :
            <div className="grid h-9 w-9 place-items-center rounded-full border border-primary/40 font-display text-[18px] italic text-accent">{(st.name || "N").charAt(0)}</div>}
          <span className="text-[12px] font-semibold uppercase tracking-[0.2em] text-ink/70">{st.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Tap onClick={toggleTheme} aria-label="Сменить тему" className="grid h-10 w-10 place-items-center rounded-full bg-surface text-muted shadow-card">
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </Tap>
          <Tap onClick={() => go("me")} aria-label="Профиль"><Avatar src={b.user.photo_url} name={firstName || "Я"} size={40} /></Tap>
        </div>
      </motion.header>

      <motion.div variants={itemV} className="mt-7">
        <div className="text-[14px] text-muted">Добро пожаловать 🤍</div>
        <h1 className="h-display mt-1 text-[40px]">{firstName ? <>{firstName}<span className="text-primary">.</span></> : <>Рады видеть<span className="text-primary">.</span></>}</h1>
      </motion.div>

      {/* главный баннер */}
      <motion.section variants={itemV} className="relative mt-5 overflow-hidden rounded-[32px] shadow-lift">
        <motion.div initial={{ scale: 1.08 }} animate={{ scale: 1 }} transition={{ duration: 1.6, ease }}>
          <Photo src={hero} className="h-[440px] w-full" seed={2} />
        </motion.div>
        <div className="absolute inset-0 bg-gradient-to-t from-[#2a1820]/85 via-[#2a1820]/20 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 p-6 text-white">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.8, ease }}>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/70">Nail studio</div>
            <h2 className="h-display text-[38px] leading-[0.98]">Твоя красота начинается с&nbsp;деталей</h2>
            <p className="mt-2.5 text-[14px] text-white/80">Время позаботиться о себе</p>
            <Button variant="light" size="lg" className="mt-5 px-7" onClick={() => startBooking()}>Записаться <ArrowUpRight size={18} /></Button>
          </motion.div>
        </div>
      </motion.section>

      {/* ближайшее окно */}
      {b.nearest && nearestSvc && (
        <motion.div variants={itemV}>
          <Tap onClick={() => startBooking({ serviceId: nearestSvc.id, date: b.nearest!.date, time: b.nearest!.time })}
            className="card mt-4 flex w-full items-center gap-4 p-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-soft text-accent"><CalendarClock size={22} strokeWidth={1.7} /></div>
            <div className="min-w-0 flex-1">
              <div className="text-[12px] font-medium text-muted">Ближайшее свободное окно</div>
              <div className="mt-0.5 text-[15.5px] font-semibold">{relDay(b.nearest.date)} в {b.nearest.time}</div>
              <div className="truncate text-[12.5px] text-muted">{nearestSvc.title}</div>
            </div>
            <span className="shrink-0 rounded-full bg-accent px-3.5 py-2 text-[12.5px] font-semibold text-white dark:text-bg">Занять</span>
          </Tap>
        </motion.div>
      )}

      {/* услуги */}
      <SectionTitle eyebrow="Прайс" title="Наши услуги" action="Все" onAction={() => go("services")} />
      <div className="hscroll pb-2">
        {cats.map((c, i) => (
          <Tap key={c.id} onClick={() => go("services")} className="w-[156px] shrink-0" style={{ scrollSnapAlign: "start" }}>
            <Photo src={c.photo} seed={i} className="h-[196px] w-full rounded-[26px] shadow-card" />
            <div className="mt-2.5 px-1">
              <div className="text-[14.5px] font-semibold leading-tight">{c.title}</div>
              <div className="mt-0.5 text-[12px] text-muted">{c.count} {plural(c.count, "услуга", "услуги", "услуг")} · от {rub(c.from)}</div>
            </div>
          </Tap>
        ))}
      </div>

      {/* популярные дизайны */}
      <SectionTitle eyebrow="Вдохновение" title="Популярные дизайны" action="Галерея" onAction={() => go("gallery")} />
      {works === null ? <div className="flex gap-3"><Skeleton className="h-64 w-48" /><Skeleton className="h-64 w-48" /></div> :
        designs.length ? (
          <div className="hscroll pb-2">
            {designs.map((w, i) => (
              <Tap key={w.id} onClick={() => setLb(works!.indexOf(w))} className="relative w-[210px] shrink-0" style={{ scrollSnapAlign: "start" }}>
                <motion.div layoutId={`home-${w.id}`} className="overflow-hidden rounded-[28px]">
                  <Photo src={w.src} seed={i} className="h-[280px] w-full" />
                </motion.div>
                {w.caption && <div className="absolute inset-x-3 bottom-3 rounded-2xl bg-white/80 px-3 py-2 text-[12.5px] font-medium text-[#282326] backdrop-blur-md">{w.caption}</div>}
              </Tap>
            ))}
          </div>
        ) : <p className="text-[13.5px] text-muted">Скоро здесь появятся работы</p>}

      {/* последние работы */}
      {latest.length > 0 && <>
        <SectionTitle eyebrow="Портфолио" title="Последние работы" action="Смотреть все" onAction={() => { setGallerySection("all"); go("gallery"); }} />
        <div className="grid grid-cols-2 gap-3">
          {latest.map((w, i) => (
            <Tap key={w.id} onClick={() => setLb(works!.indexOf(w))} className={i === 0 ? "row-span-2" : ""}>
              <motion.div layoutId={`home-${w.id}`} className="h-full overflow-hidden rounded-[24px]">
                <Photo src={w.src} seed={i} className={`w-full ${i === 0 ? "h-full min-h-[300px]" : "h-[144px]"}`} />
              </motion.div>
            </Tap>
          ))}
        </div>
      </>}

      {/* почему мы */}
      {st.why_us.length > 0 && <>
        <SectionTitle eyebrow="Студия" title="Почему выбирают нас" />
        <div className="grid grid-cols-2 gap-3">
          {st.why_us.slice(0, 6).map((t, i) => {
            const Icon = WHY_ICONS[i % WHY_ICONS.length];
            return (
              <motion.div key={t} variants={itemV} className="card p-4">
                <div className="mb-3 grid h-10 w-10 place-items-center rounded-2xl bg-soft text-accent"><Icon size={19} strokeWidth={1.7} /></div>
                <div className="text-[14px] font-semibold leading-snug">{t}</div>
              </motion.div>
            );
          })}
        </div>
      </>}

      {/* мастера */}
      {b.masters.length > 0 && <>
        <SectionTitle eyebrow="Команда" title={b.masters.length > 1 ? "Мастера" : "Ваш мастер"} />
        <div className="hscroll pb-2">
          {b.masters.map((m, i) => (
            <div key={m.id} className={`card flex shrink-0 items-center gap-4 p-4 ${b.masters.length > 1 ? "w-[300px]" : "w-full"}`} style={{ scrollSnapAlign: "start" }}>
              <Photo src={m.photo || (i === 0 ? st.about_photo : null)} seed={i + 1} className="h-20 w-20 shrink-0 rounded-[22px]" />
              <div className="min-w-0">
                <div className="h-display text-[24px]">{m.name}</div>
                <div className="text-[12px] font-semibold text-primary">{m.role}</div>
                <p className="mt-1 line-clamp-2 text-[12.5px] text-muted">{m.bio}</p>
              </div>
            </div>
          ))}
        </div>
      </>}

      {/* отзывы */}
      {b.reviews.length > 0 && <>
        <SectionTitle eyebrow={`${b.reviews.length} ${plural(b.reviews.length, "отзыв", "отзыва", "отзывов")}`} title="Нас любят" />
        <div className="hscroll pb-2">
          {b.reviews.map((r, i) => (
            <div key={i} className="card w-[280px] shrink-0 p-5" style={{ scrollSnapAlign: "start" }}>
              <div className="flex gap-0.5 text-primary">{Array.from({ length: 5 }, (_, k) => <Star key={k} size={13} fill={k < r.rating ? "currentColor" : "none"} />)}</div>
              <p className="h-display mt-3 text-[19px] italic leading-snug">«{r.text || "Всё прекрасно"}»</p>
              <div className="mt-3 text-[12.5px] font-semibold text-muted">{r.name}</div>
            </div>
          ))}
        </div>
      </>}

      {/* студия */}
      <SectionTitle eyebrow="Контакты" title="Студия" />
      <div className="card divide-y divide-line overflow-hidden">
        <Tap onClick={() => st.map_url && openLink(st.map_url)} className="flex w-full items-center gap-4 p-4">
          <MapPin size={20} strokeWidth={1.7} className="shrink-0 text-primary" />
          <div className="min-w-0 flex-1"><div className="text-[14.5px] font-semibold">{st.address}</div><div className="text-[12.5px] text-muted">{st.address_hint}</div></div>
        </Tap>
        <Tap onClick={() => st.contact_username ? openLink(`https://t.me/${st.contact_username}`) : undefined} className="flex w-full items-center gap-4 p-4">
          <MessageCircle size={20} strokeWidth={1.7} className="shrink-0 text-primary" />
          <div className="min-w-0 flex-1"><div className="text-[14.5px] font-semibold">Написать мастеру</div><div className="text-[12.5px] text-muted">{st.contact_phone || "Отвечаю в Telegram"}</div></div>
        </Tap>
      </div>
      {(st.instagram_url || st.vk_url || st.channel_url) && (
        <div className="mt-3 flex gap-2">
          {st.channel_url && <Button variant="ghost" size="sm" onClick={() => openLink(st.channel_url)}>Telegram-канал</Button>}
          {st.instagram_url && <Button variant="ghost" size="sm" onClick={() => openLink(st.instagram_url)}>Instagram</Button>}
          {st.vk_url && <Button variant="ghost" size="sm" onClick={() => openLink(st.vk_url)}>ВКонтакте</Button>}
        </div>
      )}
      <p className="mt-8 text-center text-[11.5px] text-muted">{st.name} · онлайн-запись 24/7</p>

      <Lightbox items={works || []} index={lb} onIndex={setLb} onClose={() => setLb(null)} layoutPrefix="home" />
    </motion.div>
  );
}
