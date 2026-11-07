import { AnimatePresence, motion, type PanInfo } from "framer-motion";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { haptic, setBackButton } from "../services/telegram";
import type { Work } from "../types";

/** Полноэкранный просмотр: плавное увеличение из сетки (layoutId), свайп между фото, двойной тап — зум. */
export function Lightbox({ items, index, onClose, onIndex, layoutPrefix }: {
  items: Work[]; index: number | null; onClose: () => void; onIndex: (i: number) => void; layoutPrefix: string;
}) {
  const [dir, setDir] = useState(0);
  const [zoom, setZoom] = useState(false);
  const open = index !== null && !!items[index];

  useEffect(() => {
    if (!open) return;
    setBackButton(onClose);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = ""; setBackButton(null); };
  });

  const step = (d: number) => {
    if (index === null) return;
    haptic.select();
    setZoom(false);
    setDir(d);
    onIndex((index + d + items.length) % items.length);
  };
  const onDragEnd = (_: unknown, i: PanInfo) => {
    if (zoom) return;
    if (Math.abs(i.offset.x) > 70 && Math.abs(i.offset.x) > Math.abs(i.offset.y)) step(i.offset.x < 0 ? 1 : -1);
    else if (i.offset.y > 120) onClose();
  };
  const it = open ? items[index!] : null;

  return (
    <AnimatePresence>
      {open && it && (
        <motion.div className="fixed inset-0 z-[60] flex flex-col bg-[#120d10]" initial={{ backgroundColor: "rgba(18,13,16,0)" }}
          animate={{ backgroundColor: "rgba(18,13,16,1)" }} exit={{ backgroundColor: "rgba(18,13,16,0)" }} transition={{ duration: 0.3 }}>
          <div className="flex items-center justify-between px-4 text-white/80" style={{ paddingTop: "calc(14px + var(--safe-top))" }}>
            <span className="text-[13px] font-medium tabular-nums">{index! + 1} / {items.length}</span>
            <button onClick={onClose} aria-label="Закрыть" className="grid h-10 w-10 place-items-center rounded-full bg-white/10"><X size={18} /></button>
          </div>
          <div className="relative flex flex-1 items-center justify-center overflow-hidden">
            <AnimatePresence initial={false} custom={dir} mode="popLayout">
              <motion.img key={it.id} src={it.orig || it.src} alt={it.caption}
                layoutId={dir === 0 ? `${layoutPrefix}-${it.id}` : undefined}
                custom={dir}
                initial={dir === 0 ? false : { x: dir * 80, opacity: 0, scale: 0.96 }}
                animate={{ x: 0, opacity: 1, scale: zoom ? 2.2 : 1 }}
                exit={{ x: -dir * 80, opacity: 0, scale: 0.96 }}
                transition={{ type: "spring", stiffness: 300, damping: 32 }}
                drag={zoom ? true : "x"} dragElastic={zoom ? 0.2 : 0.7} dragConstraints={zoom ? { left: -220, right: 220, top: -320, bottom: 320 } : { left: 0, right: 0, top: 0, bottom: 0 }}
                onDragEnd={onDragEnd}
                onDoubleClick={() => setZoom((z) => !z)}
                onTap={(e) => { if ((e as PointerEvent).detail === 2) setZoom((z) => !z); }}
                className="max-h-full max-w-full select-none rounded-[22px] object-contain"
                style={{ touchAction: "none" }} draggable={false} />
            </AnimatePresence>
            {items.length > 1 && <>
              <button onClick={() => step(-1)} aria-label="Предыдущее" className="absolute left-3 hidden h-11 w-11 place-items-center rounded-full bg-white/10 text-white sm:grid"><ChevronLeft /></button>
              <button onClick={() => step(1)} aria-label="Следующее" className="absolute right-3 hidden h-11 w-11 place-items-center rounded-full bg-white/10 text-white sm:grid"><ChevronRight /></button>
            </>}
          </div>
          <div className="px-5 text-white" style={{ paddingBottom: "calc(20px + var(--safe-bottom))" }}>
            <motion.p key={it.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="h-display min-h-[28px] text-[22px] italic">{it.caption}</motion.p>
            <p className="mt-1 text-[12px] text-white/50">Двойной тап — увеличить · свайп — следующее фото</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
