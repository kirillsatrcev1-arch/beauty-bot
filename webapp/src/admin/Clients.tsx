import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar, Button, Sheet, Skeleton, StatusBadge } from "../components/ui";
import { openLink } from "../services/telegram";
import type { Booking } from "../types";
import { hdate, plural, rub, time } from "../utils/format";
import { useLoad } from "./shared";

interface Client { id: number; name: string | null; first_name: string | null; username: string | null; phone: string | null; created_at: string; last_seen: string; visits: number; spent: number; last_visit: string | null; blocked: number }

export function ClientsAdmin({ focus }: { focus?: number }) {
  const [q, setQ] = useState("");
  const [deb, setDeb] = useState("");
  useEffect(() => { const t = setTimeout(() => setDeb(q), 250); return () => clearTimeout(t); }, [q]);
  const { data } = useLoad<{ items: Client[] }>(`/api/admin/clients?q=${encodeURIComponent(deb)}`);
  const [open, setOpen] = useState<number | null>(focus ?? null);
  const { data: detail } = useLoad<{ user: Client; bookings: Booking[]; favorites: string[] }>(open ? `/api/admin/clients/${open}` : null);
  const nm = (c: Client) => c.name || c.first_name || `ID ${c.id}`;
  const d = detail && detail.user.id === open ? detail : null;

  return (
    <div>
      <div className="mb-4"><div className="eyebrow">База</div><h1 className="h-display mt-1 text-[38px]">Клиенты</h1></div>
      <div className="relative">
        <Search size={17} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Имя, телефон, @username или Telegram ID" className="input pl-11" type="search" />
      </div>
      <div className="mt-4">
        {!data ? <Skeleton className="h-72" /> : data.items.length === 0 ? <p className="card py-10 text-center text-muted">Никого не нашли</p> : (
          <div className="card divide-y divide-line px-4">
            {data.items.map((c) => (
              <button key={c.id} onClick={() => setOpen(c.id)} className="flex w-full items-center gap-3 py-3 text-left">
                <Avatar name={nm(c)} size={42} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14.5px] font-semibold">{nm(c)}{c.username ? <span className="font-normal text-muted"> @{c.username}</span> : null}</div>
                  <div className="truncate text-[12px] text-muted">{c.phone || "без телефона"} · ID {c.id}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-[13.5px] font-semibold tabular-nums">{rub(c.spent)}</div>
                  <div className="text-[11.5px] text-muted">{c.visits} {plural(c.visits, "визит", "визита", "визитов")}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <Sheet open={open !== null} onClose={() => setOpen(null)}>
        {!d ? <Skeleton className="h-60" /> : <>
          <div className="flex items-center gap-4">
            <Avatar name={nm(d.user)} size={64} />
            <div className="min-w-0">
              <div className="h-display truncate text-[30px]">{nm(d.user)}</div>
              <div className="text-[12.5px] text-muted">{d.user.username ? `@${d.user.username} · ` : ""}ID {d.user.id}{d.user.blocked ? " · заблокировала бота" : ""}</div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            {[[String(d.bookings.filter((b) => b.status === "done").length), "визитов"], [rub(d.bookings.filter((b) => b.status === "done").reduce((a, b) => a + b.price, 0)), "потрачено"],
              [String(d.bookings.filter((b) => b.status === "cancelled").length), "отмен"]].map(([v, l]) => (
              <div key={l} className="card px-2 py-3"><div className="font-display text-[22px] font-semibold leading-none">{v}</div><div className="mt-1 text-[11px] text-muted">{l}</div></div>
            ))}
          </div>
          <div className="card mt-3 divide-y divide-line px-4 text-[14px]">
            <div className="flex justify-between py-3"><span className="text-muted">Телефон</span><span className="select-all font-semibold">{d.user.phone || "—"}</span></div>
            <div className="flex justify-between py-3"><span className="text-muted">С нами с</span><span className="font-semibold">{hdate(d.user.created_at.slice(0, 10), false)}</span></div>
            {d.favorites.length > 0 && <div className="flex justify-between gap-4 py-3"><span className="text-muted">Избранное</span><span className="text-right font-semibold">{d.favorites.join(", ")}</span></div>}
          </div>
          <div className="mt-3 flex gap-2">
            {d.user.username && <Button size="sm" variant="soft" onClick={() => openLink(`https://t.me/${d.user.username}`)}>Написать в Telegram</Button>}
            {d.user.phone && <Button size="sm" variant="ghost" onClick={() => window.open(`tel:${d.user.phone!.replace(/[^\d+]/g, "")}`)}>Позвонить</Button>}
          </div>
          <div className="mb-2 mt-5 text-[12px] font-semibold text-muted">История записей</div>
          <div className="card divide-y divide-line px-4">
            {d.bookings.length === 0 ? <p className="py-5 text-center text-[13px] text-muted">Записей ещё не было</p> : d.bookings.map((b) => (
              <div key={b.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0"><div className="truncate text-[14px] font-semibold">{b.service_title}</div><div className="text-[12px] text-muted">{hdate(b.date, false)}, {time(b.start)}{b.master_name ? ` · ${b.master_name}` : ""}</div></div>
                <StatusBadge status={b.status} />
              </div>
            ))}
          </div>
        </>}
      </Sheet>
    </div>
  );
}
