import { motion } from "framer-motion";
import { useState } from "react";
import { Lightbox } from "../components/Lightbox";
import { Chips, Empty, Photo, Skeleton, Tap, ease } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { useWorks } from "../hooks/useWorks";

export function Gallery() {
  const { boot, gallerySection, setGallerySection, startBooking } = useApp();
  const items = useWorks(gallerySection);
  const [lb, setLb] = useState<number | null>(null);
  const total = boot!.portfolio.reduce((a, s) => a + s.count, 0);
  const chips = [{ value: "all", label: `Все · ${total}` },
    ...boot!.portfolio.filter((s) => s.count > 0).map((s) => ({ value: s.id, label: `${s.title} · ${s.count}` }))];

  // две колонки «кирпичиком»: высоты чередуются, чтобы сетка дышала
  const cols: { w: NonNullable<typeof items>[number]; i: number }[][] = [[], []];
  (items || []).forEach((w, i) => cols[i % 2].push({ w, i }));
  const h = (i: number) => ["h-[250px]", "h-[190px]", "h-[220px]", "h-[270px]"][i % 4];

  return (
    <div className="page">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="eyebrow mt-2">Портфолио</div>
        <h1 className="h-display mt-1 text-[42px]">Галерея работ</h1>
        <p className="mt-1 text-[14px] text-muted">Нажми на фото, чтобы рассмотреть детали</p>
      </motion.div>
      <Chips id="gal" className="mt-5" items={chips} value={gallerySection} onChange={setGallerySection} />

      {items === null ? (
        <div className="mt-5 grid grid-cols-2 gap-3"><Skeleton className="h-60" /><Skeleton className="h-48" /><Skeleton className="h-52" /><Skeleton className="h-64" /></div>
      ) : items.length === 0 ? (
        <div className="mt-6"><Empty title="Скоро здесь будут работы" text="Мастер добавит фото в этот раздел" /></div>
      ) : (
        <div className="mt-5 grid grid-cols-2 gap-3">
          {cols.map((col, ci) => (
            <div key={ci} className={`flex flex-col gap-3 ${ci === 1 ? "pt-8" : ""}`}>
              {col.map(({ w, i }) => (
                <motion.div key={`${gallerySection}-${w.id}`} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, ease, delay: Math.min(i, 10) * 0.04 }}>
                  <Tap onClick={() => setLb(i)} className="block w-full">
                    <motion.div layoutId={`gal-${w.id}`} className="overflow-hidden rounded-[24px] shadow-card">
                      <Photo src={w.src} seed={i} className={`w-full ${h(i)}`} />
                    </motion.div>
                    {w.caption && <div className="mt-1.5 px-1 text-[12px] font-medium text-muted">{w.caption}</div>}
                  </Tap>
                </motion.div>
              ))}
            </div>
          ))}
        </div>
      )}
      {items && items.length > 0 && (
        <div className="card mt-8 p-6 text-center">
          <div className="h-display text-[26px]">Понравился дизайн?</div>
          <p className="mt-1 text-[13.5px] text-muted">Покажи фото на записи — повторю или сделаю в твоём стиле</p>
          <button onClick={() => startBooking()} className="mt-4 h-12 rounded-full bg-accent px-6 text-[14.5px] font-semibold text-white dark:text-bg">Записаться</button>
        </div>
      )}
      <Lightbox items={items || []} index={lb} onIndex={setLb} onClose={() => setLb(null)} layoutPrefix="gal" />
    </div>
  );
}
