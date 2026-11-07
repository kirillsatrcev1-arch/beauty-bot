import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Work } from "../types";

const cache = new Map<string, Work[]>();

/** Работы из галереи (с кэшем, чтобы вкладки открывались мгновенно). */
export function useWorks(section = "all") {
  const [items, setItems] = useState<Work[] | null>(cache.get(section) ?? null);
  useEffect(() => {
    let alive = true;
    const q = section === "all" ? "" : `?s=${section}`;
    api.get<{ items: Work[] }>(`/api/portfolio${q}`)
      .then((r) => { cache.set(section, r.items); if (alive) setItems(r.items); })
      .catch(() => alive && setItems([]));
    return () => { alive = false; };
  }, [section]);
  return items;
}
