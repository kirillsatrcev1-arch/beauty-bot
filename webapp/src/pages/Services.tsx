import { AnimatePresence, motion } from "framer-motion";
import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ServiceCard, ServiceSheet } from "../components/ServiceCard";
import { Chips, Empty, listV } from "../components/ui";
import { useApp } from "../hooks/useApp";
import type { Service } from "../types";

export function Services() {
  const { boot } = useApp();
  const b = boot!;
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Service | null>(null);

  const chips = useMemo(() => [
    { value: "all", label: "Все" },
    ...b.categories.filter((c) => c.count > 0).map((c) => ({ value: c.id, label: c.title })),
    ...(b.favorites.length ? [{ value: "fav", label: "♥ Избранное" }] : []),
  ], [b]);

  const list = useMemo(() => {
    let l = b.services;
    if (cat === "fav") l = l.filter((s) => b.favorites.includes(s.id));
    else if (cat !== "all") l = l.filter((s) => s.category === cat);
    const t = q.trim().toLowerCase();
    if (t) l = l.filter((s) => `${s.title} ${s.description}`.toLowerCase().includes(t));
    return l;
  }, [b, cat, q]);

  const grouped = cat === "all" && !q.trim()
    ? b.categories.map((c) => ({ c, items: list.filter((s) => s.category === c.id) })).filter((g) => g.items.length)
    : [{ c: null, items: list }];

  return (
    <div className="page">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="eyebrow mt-2">Прайс-лист</div>
        <h1 className="h-display mt-1 text-[42px]">Услуги</h1>
      </motion.div>
      <div className="relative mt-4">
        <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Найти услугу или дизайн" className="input pl-11 pr-10" type="search" />
        {q && <button onClick={() => setQ("")} aria-label="Очистить" className="absolute right-3 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full bg-soft text-muted"><X size={14} /></button>}
      </div>
      <Chips id="svc" className="mt-4" items={chips} value={cat} onChange={setCat} />

      <AnimatePresence mode="wait">
        <motion.div key={cat + q} initial="hidden" animate="show" exit={{ opacity: 0 }} variants={listV} className="mt-2">
          {list.length === 0 ? <div className="mt-6"><Empty title="Ничего не нашлось" text="Попробуй другое слово или категорию" /></div> :
            grouped.map(({ c, items }) => (
              <section key={c?.id || "list"}>
                {c && <h2 className="h-display mb-3 mt-7 text-[24px]">{c.title}</h2>}
                <div className={`flex flex-col gap-3 ${c ? "" : "mt-5"}`}>
                  {items.map((s) => <ServiceCard key={s.id} s={s} onOpen={setOpen} />)}
                </div>
              </section>
            ))}
        </motion.div>
      </AnimatePresence>
      <ServiceSheet s={open} onClose={() => setOpen(null)} />
    </div>
  );
}
