// @ts-nocheck — демо-заглушка API, в рабочую сборку не входит
/* ДЕМО-РЕЖИМ (только `npm run build:demo`): имитация API прямо в браузере для предпросмотра без сервера.
   В рабочей сборке этот файл не используется — там все данные идут из Python-бэкенда. */
import { ApiError, useMock } from "./api";

type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const KEY = "ns-demo-v3";
const P = (n: string) => `photos/${n}.jpg`;
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hm = (m: number) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const toMin = (s: string) => +s.slice(0, 2) * 60 + +s.slice(3, 5);
const addDays = (d: string, n: number) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() + n); return iso(x); };
const nowStr = () => new Date().toISOString().slice(0, 19).replace("T", " ");

const CATS = [["mani", "Маникюр"], ["cover", "Маникюр + покрытие"], ["removal", "Снятие покрытия"], ["strong", "Укрепление"], ["ext", "Наращивание"], ["design", "Дизайн"], ["pedi", "Педикюр"]];
const SVCS: [string, string, string, number, number, string][] = [
  ["cover", "Маникюр с покрытием", "Аппаратный маникюр, выравнивание и стойкое покрытие гель-лаком. Носка 3–4 недели.", 2000, 120, "rose_cat"],
  ["mani", "Маникюр без покрытия", "Бережная обработка кутикулы, форма, уход и масло. Для натуральной ухоженности.", 1000, 60, "cherry"],
  ["mani", "Японский маникюр", "Восстанавливающий уход с минеральной пастой и пудрой — естественный блеск.", 1500, 60, "nude_long"],
  ["cover", "Френч", "Классический или цветной френч на все ногти, тонкая линия улыбки.", 2400, 135, "pink_french"],
  ["removal", "Снятие + маникюр", "Снятие старого покрытия и аккуратный маникюр без покрытия.", 1300, 75, "beige_cat"],
  ["strong", "Укрепление ногтей", "Укрепление базой или гелем для тонких и ломких ногтей.", 2400, 140, "nude_long"],
  ["ext", "Наращивание", "Наращивание на верхние формы любой длины и формы.", 3200, 180, "silver_cat"],
  ["ext", "Коррекция наращивания", "Коррекция отросших ногтей и новое покрытие.", 2600, 150, "pink_french"],
  ["design", "Дизайн ногтей", "Втирка, роспись, стемпинг, слайдеры — стоимость зависит от сложности.", 300, 30, "blue_art"],
  ["design", "Кошачий глаз", "Магнитная втирка с глубиной и переливом.", 400, 20, "beige_cat"],
  ["pedi", "Педикюр с покрытием", "Аппаратный педикюр пальчиков и стоп, покрытие гель-лаком.", 2500, 120, "stripes"],
];
const WORKS: [string, string, string][] = [
  ["beige_cat", "nude", "Нюдовая кошачья втирка"], ["cherry", "red", "Вишнёвый глянец"], ["rose_cat", "nude", "Розовая втирка"],
  ["silver_cat", "ext", "Серебряная втирка"], ["pink_french", "french", "Розовый френч с серебром"], ["blue_art", "design", "Молочный с синей росписью"],
  ["stripes", "design", "Френч в полоску"], ["nude_long", "ext", "Длинный нюдовый квадрат"],
];
const SECTIONS = [["nude", "Нюдовый", "🤍"], ["french", "Французский", "🕊"], ["red", "Красный", "🍒"], ["design", "Дизайн", "🎨"], ["ext", "Наращивание", "💎"], ["pedi", "Педикюр", "🦶"], ["ba", "До/После", "✨"]];

function seed() {
  const t = iso(new Date());
  const services = SVCS.map(([category, title, description, price, duration, ph], i) => ({ id: i + 1, category, title, description, price, price_from: i === 8, duration, photo: P(ph), active: true }));
  const masters = [
    { id: 1, name: "Алина", role: "Топ-мастер", bio: "6 лет в nail-индустрии. Аппаратный маникюр, архитектура и тонкий дизайн.", photo: P("rose_cat"), active: true, service_ids: [], work_days: "0,1,2,3,4,5", work_start: "10:00", work_end: "20:00", break_start: "14:00", break_end: "14:30" },
    { id: 2, name: "Вероника", role: "Мастер-дизайнер", bio: "Френч, втирки и сложные дизайны. Работаю с длиной.", photo: P("pink_french"), active: true, service_ids: [1, 4, 7, 8, 9, 10], work_days: "1,2,3,4,5,6", work_start: "11:00", work_end: "21:00", break_start: null, break_end: null },
  ];
  const names = ["Софья", "Дарья", "Ева", "Полина", "Ксения", "Алёна", "Катя", "Мила"];
  const bookings: Row[] = [];
  let id = 1;
  for (let i = 0; i < 16; i++) {
    const d = addDays(t, Math.floor(i / 3) + 1);
    const s = services[(i * 3) % services.length];
    const m = masters[i % 2 && s.id !== 2 && s.id !== 3 ? 1 : 0];
    const st = [600, 780, 960][i % 3] + (m.id === 2 ? 60 : 0);
    bookings.push({ id: id++, user_id: 5000 + i, service_id: s.id, service_title: s.title, price: s.price, price_from: false, duration: s.duration, date: d,
      start: `${d} ${hm(st)}`, end: `${d} ${hm(st + s.duration)}`, status: i % 3 ? "confirmed" : "pending", name: names[i % names.length],
      phone: `+7 900 000-00-${pad(i)}`, comment: i === 1 ? "Хочу как на фото с втиркой" : null, client_confirmed: 0, master_id: m.id, master_name: m.name, source: "webapp", created_at: nowStr() });
  }
  for (let i = 0; i < 22; i++) {
    const d = addDays(t, -(i * 7 + 2));
    const s = services[i % services.length];
    bookings.push({ id: id++, user_id: 5000 + (i % 8), service_id: s.id, service_title: s.title, price: s.price, price_from: false, duration: s.duration, date: d,
      start: `${d} 12:00`, end: `${d} ${hm(720 + s.duration)}`, status: i % 7 === 3 ? "cancelled" : "done", name: names[i % 8], phone: `+7 900 000-00-${pad(i % 8)}`,
      comment: null, client_confirmed: 0, master_id: (i % 2) + 1, master_name: masters[i % 2].name, source: "webapp", created_at: nowStr() });
  }
  const done1 = addDays(t, -21);
  bookings.push({ id: id++, user_id: 1, service_id: 1, service_title: "Маникюр с покрытием", price: 2000, price_from: false, duration: 120, date: done1, start: `${done1} 12:00`, end: `${done1} 14:00`,
    status: "done", name: "Гостья", phone: "", comment: null, client_confirmed: 0, master_id: 1, master_name: "Алина", source: "webapp", created_at: nowStr() });
  const users = [{ id: 1, name: "", first_name: "Гостья", username: null, phone: "", created_at: nowStr(), last_seen: nowStr(), blocked: 0 },
    ...names.map((n, i) => ({ id: 5000 + i, name: n, first_name: n, username: null, phone: `+7 900 000-00-${pad(i)}`, created_at: addDays(t, -i * 9) + " 10:00:00", last_seen: nowStr(), blocked: 0 }))];
  return {
    nextId: 1000, services, masters, bookings, users, favorites: [] as number[], subscribed: false,
    works: WORKS.map(([ph, section, caption], i) => ({ id: i + 1, section, src: P(ph), orig: P(ph), caption })),
    vacations: [] as Row[], blocks: [] as Row[], windows: [] as Row[], studio_days: [] as Row[], master_days: [] as Row[],
    settings: {
      studio_name: "Lumière Nails", master_name: "Алина", about_text: "Привет! Я Алина — мастер маникюра с 6-летним опытом.", address_text: "Москва, Малая Бронная, 24",
      address_hint: "Вход со двора, домофон 12. Рядом парковка", map_url: "", contact_text: "Пиши по любым вопросам", contact_username: "lumiere_nails", contact_phone: "+7 900 123-45-67",
      channel_id: "@lumiere_nails", channel_url: "https://t.me/telegram", sub_required: "1", instagram_url: "", vk_url: "",
      cancel_rules: "Отменить или перенести запись можно не позднее чем за 3 часа до визита. Если опаздываешь — напиши мне ♡", cancel_min_hours: "3",
      auto_confirm: "0", remind_24: "1", remind_2: "1", notify_new_clients: "1", why_us: "Стерильность в 3 этапа|Премиальные материалы|Носка от 3 недель|Уютная студия и кофе",
      work_start: "10:00", work_end: "20:00", work_days: "0,1,2,3,4,5", slot_step: "30", horizon_days: "45", min_lead_min: "120", logo: "", photo_about: "", photo_welcome: "",
    } as Record<string, string>,
  };
}

let S: any; // eslint-disable-line @typescript-eslint/no-explicit-any
try { S = JSON.parse(localStorage.getItem(KEY) || "null") || seed(); } catch { S = seed(); }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch { /* */ } };
const fail = (status: number, code: string, extra: Row = {}) => { throw new ApiError(code, status, { ok: false, error: code, ...extra }); };
(window as any).__demoReset = () => { localStorage.removeItem(KEY); location.reload(); }; // eslint-disable-line @typescript-eslint/no-explicit-any

/* ---------- расписание (та же логика, что на сервере, упрощённо) ---------- */
const mastersFor = (sid: number | null) => S.masters.filter((m) => m.active && (!m.service_ids.length || (sid != null && m.service_ids.includes(sid)))).map((m) => m.id);
function windows(d: string, mid: number): [number, number][] {
  const m = S.masters.find((x) => x.id === mid)!;
  if (S.vacations.some((v) => v.master_id === mid && v.date_from <= d && v.date_to >= d)) return [];
  const studio = S.studio_days.find((x) => x.date === d), own = S.master_days.find((x) => x.master_id === mid && x.date === d);
  let w: [number, number][] = [];
  if (!(studio?.closed || own?.closed)) {
    if (own?.start) w = [[toMin(own.start), toMin(own.end)]];
    else if (studio?.start) w = [[toMin(studio.start), toMin(studio.end)]];
    else {
      const days = (m.work_days ?? S.settings.work_days).split(",").map(Number);
      if (days.includes((new Date(d + "T12:00:00").getDay() + 6) % 7)) w = [[toMin(m.work_start || S.settings.work_start), toMin(m.work_end || S.settings.work_end)]];
    }
  }
  S.windows.filter((x) => x.date === d && (!x.master_id || x.master_id === mid)).forEach((x) => w.push([toMin(x.start), toMin(x.end)]));
  const cuts: [number, number][] = S.blocks.filter((x) => x.date === d && (!x.master_id || x.master_id === mid)).map((x) => [toMin(x.start), toMin(x.end)]);
  if (m.break_start && m.break_end) cuts.push([toMin(m.break_start), toMin(m.break_end)]);
  for (const [cs, ce] of cuts) w = w.flatMap(([s, e]) => (ce <= s || cs >= e ? [[s, e]] : [...(s < cs ? [[s, cs]] : []), ...(ce < e ? [[ce, e]] : [])]) as [number, number][]);
  return w.sort((a, b) => a[0] - b[0]);
}
function free(d: string, dur: number, mid: number, exclude?: number, ignoreLead = false): number[] {
  const now = new Date(), t = iso(now);
  const lim = addDays(t, +S.settings.horizon_days);
  if (!ignoreLead && (d < t || d > lim)) return [];
  const earliest = now.getTime() + (ignoreLead ? 0 : +S.settings.min_lead_min * 60000);
  const busy = S.bookings.filter((b) => b.date === d && b.master_id === mid && ["pending", "confirmed"].includes(b.status) && b.id !== exclude).map((b) => [toMin(b.start.slice(11)), toMin(b.end.slice(11))]);
  const out: number[] = [];
  for (const [ws, we] of windows(d, mid)) for (let x = ws; x + dur <= we; x += +S.settings.slot_step) {
    if (new Date(`${d}T${hm(x)}:00`).getTime() >= earliest && busy.every(([bs, be]) => x + dur <= bs || x >= be)) out.push(x);
  }
  return out;
}
function slotsBy(d: string, dur: number, masters: number[], exclude?: number, ignoreLead = false) {
  const map = new Map<number, number[]>();
  masters.forEach((m) => free(d, dur, m, exclude, ignoreLead).forEach((x) => map.set(x, [...(map.get(x) || []), m])));
  return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([x, ms]) => ({ time: hm(x), masters: ms }));
}
function monthMap(ym: string, dur: number, masters: number[], exclude?: number) {
  const [y, m] = ym.split("-").map(Number), t = iso(new Date()), lim = addDays(t, +S.settings.horizon_days);
  const days: Record<string, string> = {};
  for (let d = 1; d <= new Date(y, m, 0).getDate(); d++) {
    const ds = `${ym}-${pad(d)}`;
    days[d] = ds < t || ds > lim ? "past" : !masters.some((mid) => windows(ds, mid).length) ? "off" : slotsBy(ds, dur, masters, exclude).length ? "free" : "busy";
  }
  return { days, min: t.slice(0, 7), max: lim.slice(0, 7) };
}
function target(q: URLSearchParams) {
  if (q.get("resched")) { const b = S.bookings.find((x) => x.id === +q.get("resched")!)!; return { dur: b.duration, ex: b.id, masters: mastersFor(b.service_id) }; }
  const s = S.services.find((x) => x.id === +q.get("service")!)!;
  const m = q.get("master");
  let masters = mastersFor(s.id);
  if (m && m !== "any") masters = masters.filter((x) => x === +m);
  return { dur: s.duration, ex: undefined, masters };
}
const svcJson = (s: Row) => ({ ...s, master_ids: mastersFor(s.id) });
const bJson = (b: Row) => ({ ...b, ics: undefined });
const sectionsJson = () => SECTIONS.map(([id, title, emoji]) => { const w = S.works.filter((x) => x.section === id); return { id, title, emoji, count: w.length, cover: w[0]?.src || null }; });
function book(sid: number, mid: number | null, date: string, time: string, name: string, phone: string, comment: string | null, uid: number, force = false) {
  const s = S.services.find((x) => x.id === sid)!;
  const t = toMin(time);
  const cand = mid ? [mid] : mastersFor(sid);
  const chosen = cand.find((m) => force ? S.bookings.filter((b) => b.date === date && b.master_id === m && ["pending", "confirmed"].includes(b.status)).every((b) => t + s.duration <= toMin(b.start.slice(11)) || t >= toMin(b.end.slice(11))) : free(date, s.duration, m).includes(t));
  if (!chosen) fail(409, "slot_taken");
  const m = S.masters.find((x) => x.id === chosen)!;
  const b = { id: S.nextId++, user_id: uid, service_id: s.id, service_title: s.title, price: s.price, price_from: s.price_from, duration: s.duration, date, start: `${date} ${time}`,
    end: `${date} ${hm(t + s.duration)}`, status: force || S.settings.auto_confirm === "1" ? "confirmed" : "pending", name, phone, comment, client_confirmed: 0, master_id: m.id, master_name: m.name, source: force ? "admin" : "webapp", created_at: nowStr() };
  S.bookings.push(b);
  return b;
}

async function handle(method: string, path: string, body: any): Promise<unknown> { // eslint-disable-line @typescript-eslint/no-explicit-any
  await new Promise((r) => setTimeout(r, 160));
  const u = new URL(path, "https://demo.local"), q = u.searchParams, p = u.pathname;
  const t = iso(new Date());
  const ok = (x: Row = {}) => { save(); return { ok: true, ...x }; };
  const me = S.users[0];

  if (p === "/api/bootstrap") {
    const g = S.settings;
    const nearSvc = S.services[0];
    let nearest = null;
    for (let i = 0; i < 20 && !nearest; i++) { const d = addDays(t, i); const sl = slotsBy(d, nearSvc.duration, mastersFor(nearSvc.id)); if (sl.length) nearest = { service_id: nearSvc.id, date: d, time: sl[0].time }; }
    return { ok: true,
      studio: { name: g.studio_name, logo: g.logo || null, master: g.master_name, about: g.about_text, address: g.address_text, address_hint: g.address_hint, map_url: g.map_url,
        contact_text: g.contact_text, contact_username: g.contact_username, contact_phone: g.contact_phone, channel_url: g.channel_url, instagram_url: g.instagram_url, vk_url: g.vk_url,
        cancel_rules: g.cancel_rules, cancel_min_hours: +g.cancel_min_hours, why_us: g.why_us.split("|").filter(Boolean), about_photo: g.photo_about || null, hero_photo: g.photo_welcome || P("beige_cat") },
      categories: CATS.map(([id, title]) => ({ id, title, emoji: "", photo: null, count: S.services.filter((s) => s.category === id && s.active).length })),
      services: S.services.filter((s) => s.active).map(svcJson), masters: S.masters.filter((m) => m.active), portfolio: sectionsJson(),
      reviews: [{ name: "Алёна", rating: 5, text: "Самый уютный маникюр в моей жизни, носится уже четвёртую неделю", created_at: "" },
        { name: "Катя", rating: 5, text: "Идеальный квадрат и нюд. Мастер — золото!", created_at: "" }, { name: "Вероника", rating: 5, text: "Френч мечты и очень приятная атмосфера", created_at: "" }],
      favorites: S.favorites, nearest,
      user: { id: 1, name: me.name, first_name: me.first_name, phone: me.phone, photo_url: null, is_admin: true } };
  }
  if (p === "/api/portfolio") { const s = q.get("s"); return { ok: true, items: S.works.filter((w) => !s || w.section === s) }; }
  if (p === "/api/month") { const x = target(q); return { ok: true, ...monthMap(q.get("ym")!, x.dur, x.masters, x.ex) }; }
  if (p === "/api/slots") { const x = target(q); return { ok: true, slots: slotsBy(q.get("date")!, x.dur, x.masters, x.ex) }; }
  if (p === "/api/sub") { S.subscribed = true; return ok({ subscribed: true }); }
  if (p === "/api/favorite") { const id = body.service; const on = !S.favorites.includes(id); S.favorites = on ? [...S.favorites, id] : S.favorites.filter((x) => x !== id); return ok({ favorite: on }); }
  if (p === "/api/book") {
    if (!S.subscribed && S.settings.sub_required === "1") fail(403, "subscribe", { channel_url: S.settings.channel_url });
    const digits = String(body.phone).replace(/\D/g, ""); if (digits.length < 11) fail(400, "phone");
    const b = book(body.service, body.master && body.master !== "any" ? +body.master : null, body.date, body.time, body.name, body.phone, body.comment || null, 1);
    me.name = body.name; me.phone = body.phone;
    return ok({ booking: bJson(b) });
  }
  if (p === "/api/reschedule" || p === "/api/cancel") {
    const b = S.bookings.find((x) => x.id === body.id && x.user_id === 1); if (!b) fail(404, "not_found");
    if (new Date(b!.start.replace(" ", "T")).getTime() - Date.now() < +S.settings.cancel_min_hours * 3600000) fail(400, "too_late");
    if (p === "/api/cancel") { b!.status = "cancelled"; return ok(); }
    const tt = toMin(body.time);
    const cand = [b!.master_id, ...mastersFor(b!.service_id).filter((m) => m !== b!.master_id)];
    const m = cand.find((mid) => free(body.date, b!.duration, mid, b!.id).includes(tt)); if (!m) fail(409, "slot_taken");
    Object.assign(b!, { date: body.date, start: `${body.date} ${body.time}`, end: `${body.date} ${hm(tt + b!.duration)}`, master_id: m, master_name: S.masters.find((x) => x.id === m)!.name, status: S.settings.auto_confirm === "1" ? "confirmed" : "pending" });
    return ok({ booking: bJson(b!) });
  }
  if (p === "/api/my") {
    const mine = S.bookings.filter((b) => b.user_id === 1);
    return { ok: true, active: mine.filter((b) => ["pending", "confirmed"].includes(b.status)).sort((a, b) => a.start.localeCompare(b.start)).map(bJson),
      history: mine.filter((b) => !["pending", "confirmed"].includes(b.status)).sort((a, b) => b.start.localeCompare(a.start)).map(bJson) };
  }

  /* ---------- админка ---------- */
  if (p === "/api/admin/login") return ok({ session: "demo" });
  if (p === "/api/admin/me") return { ok: true, id: 1, name: "Алина", studio: S.settings.studio_name };
  if (p === "/api/admin/dashboard") {
    const act = (b: Row) => ["pending", "confirmed", "done"].includes(b.status);
    const ws = addDays(t, -((new Date().getDay() + 6) % 7));
    const months = Array.from({ length: 6 }, (_, i) => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 5 + i); const ym = iso(d).slice(0, 7);
      const l = S.bookings.filter((b) => b.date.startsWith(ym) && act(b)); return { month: ym, bookings: l.length, revenue: l.filter((b) => b.status === "done").reduce((a, b) => a + b.price, 0) }; });
    const top: Record<string, number> = {}; S.bookings.filter(act).forEach((b) => (top[b.service_title] = (top[b.service_title] || 0) + 1));
    return { ok: true, today: S.bookings.filter((b) => b.date === t && act(b)).length, week: S.bookings.filter((b) => b.date >= ws && b.date <= addDays(ws, 6) && act(b)).length,
      new_clients: S.users.filter((x) => x.created_at.slice(0, 10) >= addDays(t, -30)).length,
      revenue_month: S.bookings.filter((b) => b.status === "done" && b.date >= t.slice(0, 8) + "01").reduce((a, b) => a + b.price, 0),
      revenue_total: S.bookings.filter((b) => b.status === "done").reduce((a, b) => a + b.price, 0),
      expected: S.bookings.filter((b) => ["pending", "confirmed"].includes(b.status) && b.date >= t).reduce((a, b) => a + b.price, 0),
      pending: S.bookings.filter((b) => b.status === "pending").length,
      upcoming: S.bookings.filter((b) => ["pending", "confirmed"].includes(b.status) && b.date >= t).sort((a, b) => a.start.localeCompare(b.start)).slice(0, 8),
      months, days: Array.from({ length: 14 }, (_, i) => { const d = addDays(t, i - 13); return { date: d, bookings: S.bookings.filter((b) => b.date === d && act(b)).length }; }),
      top: Object.entries(top).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([title, n]) => ({ title, n })) };
  }
  if (p === "/api/admin/bookings" && method === "GET") {
    let l = S.bookings.slice();
    const qq = (q.get("q") || "").toLowerCase();
    if (qq) l = l.filter((b) => `${b.name} ${b.service_title} ${b.phone}`.toLowerCase().includes(qq));
    if (q.get("from")) l = l.filter((b) => b.date >= q.get("from")!);
    if (q.get("to")) l = l.filter((b) => b.date <= q.get("to")!);
    if (q.get("master")) l = l.filter((b) => b.master_id === +q.get("master")!);
    if (q.get("status")) l = l.filter((b) => b.status === q.get("status"));
    l.sort((a, b) => (q.get("order") === "desc" ? b.start.localeCompare(a.start) : a.start.localeCompare(b.start)));
    return { ok: true, items: l.slice(0, 300) };
  }
  if (p === "/api/admin/bookings" && method === "POST") return ok({ booking: book(+body.service, body.master ? +body.master : null, body.date, body.time, body.name, body.phone, body.comment || null, 0, true) });
  const bm = p.match(/^\/api\/admin\/bookings\/(\d+)$/);
  if (bm) {
    const b = S.bookings.find((x) => x.id === +bm[1])!;
    if (body.action === "confirm") b.status = "confirmed";
    else if (body.action === "cancel") { b.status = "cancelled"; b.cancel_reason = body.reason || null; }
    else if (body.action === "done") b.status = "done";
    else if (body.action === "status") b.status = body.status;
    else if (body.action === "move") {
      const tt = toMin(body.time); const cand = body.master ? [+body.master] : [b.master_id, ...mastersFor(b.service_id)];
      const m = cand.find((mid) => free(body.date, b.duration, mid, b.id, true).includes(tt)); if (!m) fail(409, "slot_taken");
      Object.assign(b, { date: body.date, start: `${body.date} ${body.time}`, end: `${body.date} ${hm(tt + b.duration)}`, master_id: m, master_name: S.masters.find((x) => x.id === m)!.name, status: "confirmed" });
    }
    return ok({ booking: b });
  }
  if (p === "/api/admin/slots") {
    const ex = q.get("exclude") ? +q.get("exclude")! : undefined;
    const b = ex ? S.bookings.find((x) => x.id === ex) : null;
    const s = b ? null : S.services.find((x) => x.id === +q.get("service")!);
    const dur = b ? b.duration : s!.duration, sid = b ? b.service_id : s!.id;
    return { ok: true, slots: slotsBy(q.get("date")!, dur, q.get("master") ? [+q.get("master")!] : mastersFor(sid), ex, true) };
  }
  if (p === "/api/admin/calendar") {
    const ms = S.masters.filter((m) => m.active && (!q.get("master") || m.id === +q.get("master")!));
    const days = []; for (let d = q.get("from")!; d <= q.get("to")!; d = addDays(d, 1)) {
      days.push({ date: d, windows: Object.fromEntries(ms.map((m) => [m.id, windows(d, m.id)])),
        bookings: S.bookings.filter((b) => b.date === d && b.status !== "cancelled" && ms.some((m) => m.id === b.master_id)).sort((a, b) => a.start.localeCompare(b.start)),
        blocks: S.blocks.filter((x) => x.date === d) });
    }
    return { ok: true, days, masters: ms.map((m) => ({ id: m.id, name: m.name })) };
  }
  if (p === "/api/admin/services" && method === "GET") return { ok: true, services: S.services.map(svcJson), categories: CATS.map(([id, title]) => ({ id, title, emoji: "" })) };
  if (p === "/api/admin/services" && method === "POST") {
    const fields = { category: body.category, title: body.title, description: body.description || "", price: +body.price, price_from: !!body.price_from, duration: +body.duration, active: body.active !== false };
    let s = S.services.find((x) => x.id === body.id);
    if (s) Object.assign(s, fields); else { s = { id: S.nextId++, photo: null, ...fields }; S.services.push(s); }
    if ("photo" in body) s.photo = body.photo;
    return ok({ id: s.id });
  }
  const sd = p.match(/^\/api\/admin\/services\/(\d+)$/); if (sd) { S.services = S.services.filter((x) => x.id !== +sd[1]); return ok(); }
  if (p === "/api/admin/masters" && method === "GET") return { ok: true, masters: S.masters };
  if (p === "/api/admin/masters" && method === "POST") {
    const f = { name: body.name, role: body.role, bio: body.bio, active: body.active !== false, service_ids: body.service_ids || [], work_days: Array.isArray(body.work_days) ? body.work_days.join(",") : null,
      work_start: body.work_start || null, work_end: body.work_end || null, break_start: body.break_start || null, break_end: body.break_end || null };
    let m = S.masters.find((x) => x.id === body.id);
    if (m) Object.assign(m, f); else { m = { id: S.nextId++, photo: null, ...f }; S.masters.push(m); }
    if ("photo" in body) m.photo = body.photo;
    return ok({ id: m.id });
  }
  const md = p.match(/^\/api\/admin\/masters\/(\d+)$/); if (md) { const m = S.masters.find((x) => x.id === +md[1])!; m.active = false; return ok(); }
  if (p === "/api/admin/schedule" && method === "GET") return { ok: true, defaults: { work_days: S.settings.work_days, work_start: S.settings.work_start, work_end: S.settings.work_end, slot_step: S.settings.slot_step, horizon_days: S.settings.horizon_days, min_lead_min: S.settings.min_lead_min },
    vacations: S.vacations, blocks: S.blocks, windows: S.windows, studio_days: S.studio_days, master_days: S.master_days };
  const sa = p.match(/^\/api\/admin\/schedule\/(\w+)(?:\/(.+))?$/);
  if (sa && method === "POST") {
    const k = sa[1], mid = body.master_id ? +body.master_id : null;
    if (k === "vacation") S.vacations.push({ id: S.nextId++, master_id: mid, date_from: body.date_from, date_to: body.date_to, note: body.note });
    if (k === "block") S.blocks.push({ id: S.nextId++, master_id: mid, date: body.date, start: body.start, end: body.end, reason: body.reason });
    if (k === "window") S.windows.push({ id: S.nextId++, master_id: mid, date: body.date, start: body.start, end: body.end });
    if (k === "day") { const rec = { date: body.date, closed: body.closed ? 1 : 0, start: body.closed ? null : body.start, end: body.closed ? null : body.end };
      if (mid) { S.master_days = S.master_days.filter((x) => !(x.master_id === mid && x.date === body.date)); S.master_days.push({ master_id: mid, ...rec }); }
      else { S.studio_days = S.studio_days.filter((x) => x.date !== body.date); S.studio_days.push(rec); } }
    return ok({ id: 0 });
  }
  if (sa && method === "DELETE") {
    const k = sa[1], key = decodeURIComponent(sa[2] || "");
    if (k === "vacation") S.vacations = S.vacations.filter((x) => x.id !== +key);
    if (k === "block") S.blocks = S.blocks.filter((x) => x.id !== +key);
    if (k === "window") S.windows = S.windows.filter((x) => x.id !== +key);
    if (k === "day") { if (key.includes("_")) { const [m, d] = key.split("_"); S.master_days = S.master_days.filter((x) => !(x.master_id === +m && x.date === d)); } else S.studio_days = S.studio_days.filter((x) => x.date !== key); }
    return ok();
  }
  if (p === "/api/admin/clients") {
    const qq = (q.get("q") || "").toLowerCase();
    return { ok: true, items: S.users.filter((x) => !qq || `${x.name} ${x.first_name} ${x.phone} ${x.id}`.toLowerCase().includes(qq)).map((x) => {
      const done = S.bookings.filter((b) => b.user_id === x.id && b.status === "done");
      return { ...x, visits: done.length, spent: done.reduce((a, b) => a + b.price, 0), last_visit: done[0]?.date || null };
    }) };
  }
  const cd = p.match(/^\/api\/admin\/clients\/(\d+)$/);
  if (cd) { const x = S.users.find((y) => y.id === +cd[1])!; return { ok: true, user: x, bookings: S.bookings.filter((b) => b.user_id === x.id).sort((a, b) => b.start.localeCompare(a.start)), favorites: [] }; }
  if (p === "/api/admin/gallery" && method === "GET") return { ok: true, items: S.works.slice().reverse(), sections: SECTIONS.map(([id, title]) => ({ id, title })) };
  if (p === "/api/admin/gallery" && method === "POST") { S.works.push({ id: S.nextId++, section: body.section, src: body.photo, orig: body.photo, caption: body.caption || "" }); return ok(); }
  const gm = p.match(/^\/api\/admin\/gallery\/(\d+)$/);
  if (gm && method === "POST") { const w = S.works.find((x) => x.id === +gm[1])!; if (body.section) w.section = body.section; if ("caption" in body) w.caption = body.caption; return ok(); }
  if (gm && method === "DELETE") { S.works = S.works.filter((x) => x.id !== +gm[1]); return ok(); }
  if (p === "/api/admin/upload") {
    const f = body as File;
    const url = await new Promise<string>((res) => { const img = new Image(); img.onload = () => { const c = document.createElement("canvas"); const k = Math.min(1, 900 / Math.max(img.width, img.height));
      c.width = img.width * k; c.height = img.height * k; c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height); res(c.toDataURL("image/jpeg", 0.82)); }; img.onerror = () => res(""); img.src = URL.createObjectURL(f); });
    if (!url) fail(400, "not_image");
    return { ok: true, value: url, url };
  }
  if (p === "/api/admin/settings" && method === "GET") return { ok: true, settings: { ...S.settings, logo_url: S.settings.logo || null, photo_about_url: S.settings.photo_about || null, photo_welcome_url: S.settings.photo_welcome || null }, webapp_url: "" };
  if (p === "/api/admin/settings" && method === "POST") { Object.entries(body).forEach(([k, v]) => { if (k in S.settings) S.settings[k] = String(v ?? ""); }); return ok(); }
  fail(404, "not_found");
}

export function installMock() {
  useMock((method, path, body) => handle(method, path, body));
}
