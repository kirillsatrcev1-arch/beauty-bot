import { AnimatePresence, motion } from "framer-motion";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../services/api";
import { initTelegram, tg } from "../services/telegram";
import type { Boot, Booking } from "../types";

export type Tab = "home" | "services" | "book" | "gallery" | "me";
export interface BookingIntent { serviceId?: number; masterId?: number | null; date?: string; time?: string; reschedule?: Booking }
type Theme = "light" | "dark";

interface AppCtx {
  boot: Boot | null;
  error: string | null;
  reload: () => Promise<void>;
  setBoot: (fn: (b: Boot) => Boot) => void;
  tab: Tab;
  go: (t: Tab) => void;
  intent: BookingIntent | null;
  startBooking: (i?: BookingIntent) => void;
  toast: (text: string) => void;
  theme: Theme;
  toggleTheme: () => void;
  gallerySection: string;
  setGallerySection: (s: string) => void;
}

const Ctx = createContext<AppCtx>(null as unknown as AppCtx);
export const useApp = () => useContext(Ctx);

const THEME_KEY = "ns-theme";
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* */ }
  return "light"; // фирменная светлая тема по умолчанию; тёмная — по переключателю
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  const bg = t === "dark" ? "#161214" : "#FAF7F5";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
  initTelegram(bg);
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [boot, setBootState] = useState<Boot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(location.search).get("tab") as Tab) || "home");
  const [intent, setIntent] = useState<BookingIntent | null>(null);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [toastText, setToastText] = useState<string | null>(null);
  const [gallerySection, setGallerySection] = useState("all");
  const timer = useRef<number>();

  useEffect(() => { applyTheme(theme); try { localStorage.setItem(THEME_KEY, theme); } catch { /* */ } }, [theme]);

  const reload = useCallback(async () => {
    try {
      setBootState(await api.get<Boot>("/api/bootstrap"));
      setError(null);
    } catch (e) {
      setError(tg?.initData ? "Не удалось загрузить данные" : "Открой приложение из Telegram-бота");
    }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const toast = useCallback((text: string) => {
    setToastText(text);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastText(null), 2600);
  }, []);

  const go = useCallback((t: Tab) => { setTab(t); window.scrollTo({ top: 0 }); }, []);
  const startBooking = useCallback((i?: BookingIntent) => { setIntent({ ...(i || {}) }); setTab("book"); window.scrollTo({ top: 0 }); }, []);

  const value = useMemo<AppCtx>(() => ({
    boot, error, reload, setBoot: (fn) => setBootState((b) => (b ? fn(b) : b)), tab, go, intent, startBooking, toast,
    theme, toggleTheme: () => setTheme((t) => (t === "light" ? "dark" : "light")), gallerySection, setGallerySection,
  }), [boot, error, reload, tab, go, intent, startBooking, toast, theme, gallerySection]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <AnimatePresence>
        {toastText && (
          <motion.div key={toastText} role="status"
            initial={{ opacity: 0, y: -24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -16 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            className="fixed left-1/2 top-3 z-[70] -translate-x-1/2 rounded-full bg-ink px-5 py-3 text-[13.5px] font-semibold text-bg shadow-lift"
            style={{ marginTop: "var(--safe-top)", maxWidth: "calc(100vw - 32px)" }}>
            {toastText}
          </motion.div>
        )}
      </AnimatePresence>
    </Ctx.Provider>
  );
}
