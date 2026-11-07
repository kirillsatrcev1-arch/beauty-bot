import { motion } from "framer-motion";
import { Clock, Heart } from "lucide-react";
import { useApp } from "../hooks/useApp";
import { api } from "../services/api";
import { haptic } from "../services/telegram";
import type { Service } from "../types";
import { dur, rub } from "../utils/format";
import { Button, Photo, Sheet, itemV } from "./ui";

export function ServiceCard({ s, onOpen, compact = false }: { s: Service; onOpen: (s: Service) => void; compact?: boolean }) {
  const { startBooking } = useApp();
  return (
    <motion.div variants={itemV} layout className="card flex gap-3.5 p-3">
      <button onClick={() => onOpen(s)} className="shrink-0" aria-label={s.title}>
        <Photo src={s.photo} seed={s.id} className={`${compact ? "h-[76px] w-[76px]" : "h-[104px] w-[92px]"} rounded-[20px]`} />
      </button>
      <div className="flex min-w-0 flex-1 flex-col">
        <button onClick={() => onOpen(s)} className="text-left">
          <div className="text-[15px] font-semibold leading-snug">{s.title}</div>
          {!compact && <p className="mt-1 line-clamp-2 text-[12.5px] leading-snug text-muted">{s.description}</p>}
        </button>
        <div className="mt-auto flex items-end justify-between gap-2 pt-2">
          <div>
            <div className="font-display text-[21px] font-semibold leading-none">{rub(s.price, s.price_from)}</div>
            <div className="mt-1 flex items-center gap-1 text-[11.5px] text-muted"><Clock size={12} />{dur(s.duration)}</div>
          </div>
          <Button size="sm" onClick={() => startBooking({ serviceId: s.id })}>Выбрать</Button>
        </div>
      </div>
    </motion.div>
  );
}

export function ServiceSheet({ s, onClose }: { s: Service | null; onClose: () => void }) {
  const { boot, setBoot, startBooking, toast } = useApp();
  const fav = !!s && !!boot?.favorites.includes(s.id);
  const masters = boot?.masters.filter((m) => s?.master_ids.includes(m.id)) || [];
  const toggleFav = async () => {
    if (!s) return;
    haptic.tap();
    try {
      const r = await api.post<{ favorite: boolean }>("/api/favorite", { service: s.id });
      setBoot((b) => ({ ...b, favorites: r.favorite ? [...b.favorites, s.id] : b.favorites.filter((x) => x !== s.id) }));
      toast(r.favorite ? "Добавлено в избранное" : "Убрано из избранного");
    } catch { toast("Не получилось"); }
  };
  return (
    <Sheet open={!!s} onClose={onClose}>
      {s && (
        <div>
          <Photo src={s.photo} seed={s.id} className="mb-5 h-56 w-full rounded-[26px]" />
          <h3 className="h-display text-[32px]">{s.title}</h3>
          <p className="mt-2 text-[14.5px] leading-relaxed text-ink/75">{s.description}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="rounded-full bg-soft px-3.5 py-2 text-[13px] font-semibold text-accent">{rub(s.price, s.price_from)}</span>
            <span className="rounded-full bg-soft px-3.5 py-2 text-[13px] font-medium text-ink/70">{dur(s.duration)}</span>
            {masters.length > 0 && <span className="rounded-full bg-soft px-3.5 py-2 text-[13px] font-medium text-ink/70">{masters.map((m) => m.name).join(", ")}</span>}
          </div>
          <div className="mt-6 flex gap-2.5">
            <Button size="lg" className="flex-1" onClick={() => { onClose(); startBooking({ serviceId: s.id }); }}>Записаться</Button>
            <motion.button whileTap={{ scale: 0.9 }} onClick={toggleFav} aria-label="В избранное"
              className={`grid h-14 w-14 place-items-center rounded-full border transition-colors ${fav ? "border-transparent bg-primary text-white" : "border-line bg-surface text-muted"}`}>
              <motion.span key={String(fav)} initial={{ scale: 0.5 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 15 }}>
                <Heart size={20} fill={fav ? "currentColor" : "none"} />
              </motion.span>
            </motion.button>
          </div>
        </div>
      )}
    </Sheet>
  );
}
