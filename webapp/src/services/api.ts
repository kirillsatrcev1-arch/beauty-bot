/* HTTP-клиент. Каждый запрос подписан Telegram initData — сервер проверяет его подпись.
   Веб-админка в браузере использует сессию, выданную сервером по одноразовой ссылке из бота. */
import { tg } from "./telegram";

export class ApiError extends Error {
  status: number;
  data: Record<string, unknown>;
  constructor(code: string, status: number, data: Record<string, unknown>) {
    super(code);
    this.status = status;
    this.data = data;
  }
}

const SESSION_KEY = "ns-admin-session";
export const adminSession = {
  get: () => { try { return localStorage.getItem(SESSION_KEY) || ""; } catch { return ""; } },
  set: (v: string) => { try { localStorage.setItem(SESSION_KEY, v); } catch { /* */ } },
  clear: () => { try { localStorage.removeItem(SESSION_KEY); } catch { /* */ } },
};

type Handler = (method: string, path: string, body?: unknown) => Promise<unknown>;
let mock: Handler | null = null;
export function useMock(h: Handler) { mock = h; }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (mock) return (await mock(method, path, body)) as T;
  const headers: Record<string, string> = { "X-Init-Data": tg?.initData || "" };
  const session = adminSession.get();
  if (session && path.startsWith("/api/admin/")) headers["X-Admin-Session"] = session;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError("network", 0, {});
  }
  let data: Record<string, unknown> = {};
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok || data.ok === false) throw new ApiError(String(data.error || "error"), res.status, data);
  return data as T;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  del: <T,>(path: string) => request<T>("DELETE", path),
  upload: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ value: string; url: string }>("POST", "/api/admin/upload", mock ? file : fd);
  },
};

export const errorText = (e: unknown): string => {
  const code = e instanceof ApiError ? e.message : "error";
  return ({
    slot_taken: "Это время только что заняли — выбери другое",
    too_late: "До визита осталось мало времени — напиши мастеру",
    phone: "Проверь номер телефона",
    name: "Напиши имя",
    network: "Нет соединения. Проверь интернет",
    forbidden: "Нет доступа",
    unauthorized: "Сессия устарела — открой приложение заново",
    has_bookings: "У мастера есть будущие записи — сначала перенеси их",
    last_master: "Нельзя отключить последнего мастера",
    not_image: "Это не изображение",
    too_large: "Файл больше 15 МБ",
    hours: "Начало работы должно быть раньше конца",
    break: "Проверь время перерыва",
    time: "Проверь время",
    range: "Проверь даты",
  } as Record<string, string>)[code] || "Что-то пошло не так, попробуй ещё раз";
};
