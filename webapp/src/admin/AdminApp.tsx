import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, CalendarDays, ClipboardList, Images, LayoutDashboard, LogOut, Moon, Scissors, Settings, Sun, Timer, UsersRound, UserRoundCog } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Skeleton, ease } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { adminSession, api, ApiError } from "../services/api";
import { inTelegram } from "../services/telegram";
import { exitAdmin } from "../App";
import { BookingsAdmin } from "./Bookings";
import { CalendarAdmin } from "./CalendarAdmin";
import { ClientsAdmin } from "./Clients";
import { Dashboard } from "./Dashboard";
import { GalleryAdmin } from "./GalleryAdmin";
import { MastersAdmin } from "./Masters";
import { ScheduleAdmin } from "./Schedule";
import { ServicesAdmin } from "./ServicesAdmin";
import { SettingsAdmin } from "./SettingsAdmin";

export type Section = "dash" | "bookings" | "calendar" | "services" | "masters" | "schedule" | "clients" | "gallery" | "settings";
const NAV: { id: Section; label: string; Icon: typeof LayoutDashboard }[] = [
  { id: "dash", label: "Обзор", Icon: LayoutDashboard },
  { id: "bookings", label: "Записи", Icon: ClipboardList },
  { id: "calendar", label: "Календарь", Icon: CalendarDays },
  { id: "services", label: "Услуги", Icon: Scissors },
  { id: "masters", label: "Мастера", Icon: UserRoundCog },
  { id: "schedule", label: "Расписание", Icon: Timer },
  { id: "clients", label: "Клиенты", Icon: UsersRound },
  { id: "gallery", label: "Галерея", Icon: Images },
  { id: "settings", label: "Настройки", Icon: Settings },
];

type Auth = "checking" | "ok" | "denied";

export default function AdminApp() {
  const { theme, toggleTheme } = useApp();
  const [auth, setAuth] = useState<Auth>("checking");
  const [me, setMe] = useState<{ name: string; studio: string } | null>(null);
  const [section, setSection] = useState<Section>("dash");
  const [focus, setFocus] = useState<{ date?: string; client?: number } | null>(null);

  useEffect(() => {
    (async () => {
      const token = new URLSearchParams(location.search).get("token");
      if (token) {
        try {
          const r = await api.post<{ session: string }>("/api/admin/login", { token });
          adminSession.set(r.session);
        } catch { /* ссылка просрочена — покажем экран входа */ }
        history.replaceState(null, "", location.pathname);
      }
      try {
        setMe(await api.get<{ name: string; studio: string }>("/api/admin/me"));
        setAuth("ok");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) adminSession.clear();
        setAuth("denied");
      }
    })();
  }, []);

  const nav = (s: Section, f: { date?: string; client?: number } | null = null) => { setFocus(f); setSection(s); window.scrollTo({ top: 0 }); };

  if (auth === "checking") return <div className="page"><Skeleton className="mt-6 h-12 w-56" /><Skeleton className="mt-6 h-40" /></div>;
  if (auth === "denied") return (
    <div className="page flex min-h-[85vh] flex-col items-center justify-center text-center">
      <div className="grid h-16 w-16 place-items-center rounded-full bg-soft text-accent"><Settings /></div>
      <h1 className="h-display mt-5 text-[34px]">Админ-панель</h1>
      <p className="mt-2 max-w-[320px] text-[14px] text-muted">
        Вход только для мастера. Отправь боту команду <b className="text-ink">/panel</b> — он пришлёт кнопку для входа в Telegram и одноразовую ссылку для браузера.
      </p>
      {!inTelegram && <p className="mt-3 max-w-[320px] text-[12px] text-muted">Ссылка действует 10 минут, после входа сессия хранится 7 дней на этом устройстве.</p>}
      <Button variant="ghost" className="mt-6" onClick={exitAdmin}>На главную приложения</Button>
    </div>
  );

  const Page = {
    dash: <Dashboard nav={nav} />, bookings: <BookingsAdmin focus={focus} />, calendar: <CalendarAdmin focusDate={focus?.date} />,
    services: <ServicesAdmin />, masters: <MastersAdmin />, schedule: <ScheduleAdmin />, clients: <ClientsAdmin focus={focus?.client} />,
    gallery: <GalleryAdmin />, settings: <SettingsAdmin />,
  }[section];

  return (
    <div className="min-h-screen lg:flex">
      {/* боковое меню на широких экранах */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface px-4 py-6 lg:flex">
        <div className="px-3"><div className="eyebrow">Админ-панель</div><div className="h-display mt-1 text-[26px]">{me?.studio}</div></div>
        <nav className="mt-6 flex flex-col gap-1">
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => nav(id)} className={`relative flex h-11 items-center gap-3 rounded-2xl px-3 text-[14px] font-medium ${section === id ? "text-accent" : "text-ink/70"}`}>
              {section === id && <motion.span layoutId="side-pill" className="absolute inset-0 rounded-2xl bg-soft" />}
              <Icon size={18} className="relative" /><span className="relative">{label}</span>
            </button>
          ))}
        </nav>
        <div className="mt-auto flex gap-2 px-1">
          <button onClick={toggleTheme} className="grid h-10 w-10 place-items-center rounded-full bg-soft text-muted" aria-label="Тема">{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
          {!inTelegram && <button onClick={() => { adminSession.clear(); location.reload(); }} className="grid h-10 w-10 place-items-center rounded-full bg-soft text-muted" aria-label="Выйти"><LogOut size={16} /></button>}
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {/* верхняя панель на телефоне */}
        <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur-xl lg:hidden" style={{ paddingTop: "var(--safe-top)" }}>
          <div className="flex items-center justify-between px-4 pt-3">
            <div className="flex items-center gap-2">
              <button onClick={exitAdmin} aria-label="В приложение" className="grid h-9 w-9 place-items-center rounded-full bg-surface shadow-card"><ArrowLeft size={16} /></button>
              <div><div className="eyebrow !text-[10px]">Админ-панель</div><div className="h-display text-[20px] leading-none">{me?.studio}</div></div>
            </div>
            <button onClick={toggleTheme} className="grid h-9 w-9 place-items-center rounded-full bg-surface text-muted shadow-card" aria-label="Тема">{theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}</button>
          </div>
          <div className="mt-3 flex gap-1.5 overflow-x-auto px-4 pb-3 no-scrollbar">
            {NAV.map(({ id, label, Icon }) => (
              <button key={id} onClick={() => nav(id)} className={`relative flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium ${section === id ? "text-white dark:text-bg" : "text-ink/70"}`}>
                {section === id && <motion.span layoutId="top-pill" className="absolute inset-0 rounded-full bg-accent" />}
                <Icon size={15} className="relative" /><span className="relative">{label}</span>
              </button>
            ))}
          </div>
        </header>
        <AnimatePresence mode="wait">
          <motion.main key={section} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3, ease }}
            className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-5 lg:px-8 lg:pt-8">
            {Page}
          </motion.main>
        </AnimatePresence>
      </div>
    </div>
  );
}
