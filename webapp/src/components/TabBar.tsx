import { motion } from "framer-motion";
import { CalendarPlus, Home, Images, Sparkles, UserRound } from "lucide-react";
import { useApp, type Tab } from "../hooks/useApp";
import { haptic } from "../services/telegram";
import { spring } from "./ui";

const TABS: { id: Tab; label: string; Icon: typeof Home }[] = [
  { id: "home", label: "Главная", Icon: Home },
  { id: "services", label: "Услуги", Icon: Sparkles },
  { id: "book", label: "Запись", Icon: CalendarPlus },
  { id: "gallery", label: "Галерея", Icon: Images },
  { id: "me", label: "Профиль", Icon: UserRound },
];

export function TabBar() {
  const { tab, go, startBooking } = useApp();
  return (
    <nav className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4"
      style={{ paddingBottom: "calc(12px + var(--safe-bottom))" }}>
      <div className="pointer-events-auto flex w-full max-w-[420px] items-center justify-between rounded-[30px] border border-white/60 bg-surface/85 px-2 py-2 shadow-tab backdrop-blur-xl dark:border-white/5">
        {TABS.map(({ id, label, Icon }) => {
          const on = tab === id;
          if (id === "book") {
            return (
              <motion.button key={id} whileTap={{ scale: 0.92 }} transition={spring} aria-label={label}
                onClick={() => { haptic.tap(); tab === "book" ? go("book") : startBooking(); }}
                className="relative -mt-7 grid h-[60px] w-[60px] place-items-center rounded-full bg-gradient-to-br from-primary to-accent text-white shadow-[0_14px_30px_-10px_rgb(var(--accent)/.75)] ring-4 ring-bg">
                <Icon size={24} strokeWidth={1.8} />
              </motion.button>
            );
          }
          return (
            <button key={id} onClick={() => { haptic.select(); go(id); }} aria-label={label} aria-current={on ? "page" : undefined}
              className="relative flex h-12 w-[64px] flex-col items-center justify-center gap-0.5">
              {on && <motion.span layoutId="tab-pill" transition={spring} className="absolute inset-0 rounded-[18px] bg-soft" />}
              <Icon size={21} strokeWidth={on ? 2 : 1.6} className={`relative transition-colors ${on ? "text-accent" : "text-muted"}`} />
              <span className={`relative text-[10px] font-semibold transition-colors ${on ? "text-accent" : "text-muted"}`}>{label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
