import { AnimatePresence, motion, useReducedMotion, type HTMLMotionProps } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { haptic, setBackButton } from "../services/telegram";

export const ease = [0.22, 0.8, 0.24, 1] as const;
export const spring = { type: "spring", stiffness: 420, damping: 34, mass: 0.8 } as const;

/* ---------- кнопки ---------- */
type BtnVariant = "primary" | "soft" | "ghost" | "light" | "danger" | "plain";
const btnCls: Record<BtnVariant, string> = {
  primary: "bg-accent text-white shadow-[0_12px_28px_-12px_rgb(var(--accent)/.7)] dark:text-bg",
  soft: "bg-secondary/70 text-accent",
  ghost: "bg-surface text-ink border border-line",
  light: "bg-white/95 text-[#282326] backdrop-blur",
  danger: "bg-surface text-danger border border-line",
  plain: "text-accent",
};
export function Button({ variant = "primary", size = "md", className = "", children, onClick, ...rest }:
  { variant?: BtnVariant; size?: "sm" | "md" | "lg" } & HTMLMotionProps<"button">) {
  const sz = size === "lg" ? "h-14 px-6 text-[15.5px]" : size === "sm" ? "h-9 px-4 text-[13px]" : "h-12 px-5 text-[14.5px]";
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      transition={spring}
      onClick={(e) => { haptic.tap(); onClick?.(e); }}
      className={`inline-flex items-center justify-center gap-2 rounded-full font-semibold tracking-[-0.005em] transition-colors disabled:opacity-40 disabled:pointer-events-none ${sz} ${btnCls[variant]} ${className}`}
      {...rest}
    >{children}</motion.button>
  );
}

export function Tap({ className = "", onClick, children, ...rest }: HTMLMotionProps<"button">) {
  return (
    <motion.button whileTap={{ scale: 0.975 }} transition={spring} onClick={(e) => { haptic.tap(); onClick?.(e); }}
      className={`text-left ${className}`} {...rest}>{children}</motion.button>
  );
}

/* ---------- чипсы с плавающим индикатором ---------- */
export function Chips<T extends string>({ items, value, onChange, id, className = "" }:
  { items: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; id: string; className?: string }) {
  return (
    <div className={`hscroll ${className}`} role="tablist">
      {items.map((it) => {
        const on = it.value === value;
        return (
          <button key={it.value} role="tab" aria-selected={on} onClick={() => { haptic.select(); onChange(it.value); }}
            className={`relative h-10 shrink-0 rounded-full px-4 text-[13.5px] font-medium transition-colors ${on ? "text-white dark:text-bg" : "text-ink/70 bg-surface border border-line"}`}>
            {on && <motion.span layoutId={`chip-${id}`} transition={spring} className="absolute inset-0 rounded-full bg-accent" />}
            <span className="relative z-10 whitespace-nowrap">{it.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------- сегментированный переключатель ---------- */
export function Segmented<T extends string>({ items, value, onChange, id }:
  { items: { value: T; label: string }[]; value: T; onChange: (v: T) => void; id: string }) {
  return (
    <div className="inline-flex rounded-full bg-soft p-1">
      {items.map((it) => (
        <button key={it.value} onClick={() => { haptic.select(); onChange(it.value); }}
          className={`relative h-8 rounded-full px-3.5 text-[12.5px] font-semibold transition-colors ${it.value === value ? "text-ink" : "text-muted"}`}>
          {it.value === value && <motion.span layoutId={`seg-${id}`} transition={spring} className="absolute inset-0 rounded-full bg-surface shadow-card" />}
          <span className="relative z-10">{it.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ---------- заголовок секции ---------- */
export function SectionTitle({ title, action, onAction, eyebrow }: { title: string; action?: string; onAction?: () => void; eyebrow?: string }) {
  return (
    <div className="mb-3.5 mt-9 flex items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h2 className="h-display text-[28px]">{title}</h2>
      </div>
      {action && <button onClick={onAction} className="pb-1 text-[13px] font-semibold text-primary">{action}</button>}
    </div>
  );
}

/* ---------- фото с мягким появлением и красивой заглушкой ---------- */
export function NailArt({ seed = 0, className = "" }: { seed?: number; className?: string }) {
  const tones = [["#F3E3E6", "#E2C2CA"], ["#F6ECE6", "#E8D2C6"], ["#EFE2EA", "#D6B7C6"], ["#F5E9E4", "#E3C9BE"]][seed % 4];
  return (
    <div className={`relative overflow-hidden ${className}`} style={{ background: `linear-gradient(150deg, ${tones[0]}, ${tones[1]})` }}>
      <svg viewBox="0 0 120 120" className="absolute inset-0 m-auto h-[62%] w-[62%] opacity-80" fill="none" stroke="#B9828F" strokeWidth="1.2">
        <path d="M60 14c13 14 22 34 22 52a22 22 0 0 1-44 0c0-18 9-38 22-52Z" />
        <path d="M60 22c9 11 15 27 15 42" opacity=".5" />
        <path d="M44 92c5 6 10 9 16 9s11-3 16-9" opacity=".4" />
        <circle cx="92" cy="28" r="2" fill="#B9828F" stroke="none" opacity=".6" />
        <circle cx="26" cy="40" r="1.4" fill="#B9828F" stroke="none" opacity=".5" />
      </svg>
    </div>
  );
}

export function Photo({ src, alt = "", className = "", seed = 0, imgClass = "" }: { src?: string | null; alt?: string; className?: string; seed?: number; imgClass?: string }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!src || failed) return <NailArt seed={seed} className={className} />;
  return (
    <div className={`relative overflow-hidden bg-soft ${className}`}>
      <img src={src} alt={alt} loading="lazy" decoding="async" onLoad={() => setLoaded(true)} onError={() => setFailed(true)}
        className={`h-full w-full object-cover transition-[opacity,transform] duration-700 ease-soft ${loaded ? "opacity-100 scale-100" : "opacity-0 scale-[1.03]"} ${imgClass}`} />
    </div>
  );
}

/* ---------- аватар ---------- */
export function Avatar({ src, name, size = 44 }: { src?: string | null; name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  return src && !failed ? (
    <img src={src} alt="" onError={() => setFailed(true)} style={{ width: size, height: size }} className="rounded-full object-cover ring-2 ring-surface" />
  ) : (
    <div style={{ width: size, height: size }} className="grid place-items-center rounded-full bg-gradient-to-br from-secondary to-primary font-display text-[18px] font-semibold text-white ring-2 ring-surface">
      {(name || "♡").trim().charAt(0).toUpperCase()}
    </div>
  );
}

/* ---------- скелетоны ---------- */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

/* ---------- статус ---------- */
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    pending: ["bg-warn/15 text-warn", "Ждёт подтверждения"],
    confirmed: ["bg-ok/15 text-ok", "Подтверждена"],
    done: ["bg-soft text-muted", "Состоялась"],
    cancelled: ["bg-danger/10 text-danger", "Отменена"],
    expired: ["bg-soft text-muted", "Не подтверждена"],
  };
  const [cls, label] = map[status] || map.done;
  return <span className={`inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[11.5px] font-semibold ${cls}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</span>;
}

/* ---------- нижняя шторка ---------- */
export function Sheet({ open, onClose, children, title }: { open: boolean; onClose: () => void; children: ReactNode; title?: string }) {
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!open) return;
    setBackButton(onClose);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); setBackButton(null); };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div key="veil" className="fixed inset-0 z-40 bg-[#1a1216]/40 backdrop-blur-[2px]" onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} />
          <motion.div key="sheet" role="dialog" aria-modal="true"
            className="fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[90vh] w-full max-w-[560px] overflow-y-auto rounded-t-[32px] bg-bg px-5 pt-3 no-scrollbar"
            style={{ paddingBottom: "calc(24px + var(--safe-bottom))" }}
            initial={reduce ? { opacity: 0 } : { y: "100%" }} animate={reduce ? { opacity: 1 } : { y: 0 }} exit={reduce ? { opacity: 0 } : { y: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            drag="y" dragConstraints={{ top: 0, bottom: 0 }} dragElastic={{ top: 0, bottom: 0.6 }} dragSnapToOrigin
            onDragEnd={(_, i) => { if (i.offset.y > 110 || i.velocity.y > 600) onClose(); }}>
            <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line" />
            <div className="mb-3 flex items-start justify-between gap-4">
              {title ? <h3 className="h-display text-[28px]">{title}</h3> : <span />}
              <button onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface text-muted shadow-card"><X size={16} /></button>
            </div>
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/* ---------- появление списком ---------- */
export const listV = { hidden: {}, show: { transition: { staggerChildren: 0.055, delayChildren: 0.04 } } };
export const itemV = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.55, ease } } };

export function Empty({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center px-6 py-10 text-center">
      <NailArt className="mb-4 h-20 w-20 rounded-full" />
      <div className="h-display text-[24px]">{title}</div>
      {text && <p className="mt-1.5 max-w-[260px] text-[13.5px] text-muted">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="mb-3.5 block min-w-0">
      <span className="mb-1.5 ml-1 block text-[12px] font-semibold text-muted">{label}</span>
      {children}
      {hint && <span className="ml-1 mt-1 block text-[11.5px] text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button role="switch" aria-checked={on} onClick={() => { haptic.select(); onChange(!on); }} className="flex w-full items-center justify-between gap-4 py-3 text-left text-[14.5px]">
      <span>{label}</span>
      <span className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${on ? "bg-accent" : "bg-line"}`}>
        <motion.span layout transition={spring} className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow ${on ? "right-1" : "left-1"}`} />
      </span>
    </button>
  );
}
