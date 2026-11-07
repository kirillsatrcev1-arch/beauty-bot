export const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
export const MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
export const WD = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
export const WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export const pad = (n: number) => String(n).padStart(2, "0");
export const isoOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const today = () => isoOf(new Date());
export const addDays = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return isoOf(d); };
export const parseIso = (iso: string) => new Date(iso.slice(0, 10) + "T12:00:00");

export const rub = (n: number, from = false) => (from ? "от " : "") + n.toLocaleString("ru-RU").replace(/ |,/g, " ") + " ₽";
export const dur = (m: number) => { const h = Math.floor(m / 60), mm = m % 60; return h && mm ? `${h} ч ${mm} мин` : h ? `${h} ч` : `${mm} мин`; };

export function hdate(iso: string, withWeekday = true) {
  const d = parseIso(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}` + (withWeekday ? `, ${WD[d.getDay()]}` : "");
}
export function relDay(iso: string) {
  const t = today();
  if (iso === t) return "сегодня";
  if (iso === addDays(t, 1)) return "завтра";
  return hdate(iso, false);
}
export const time = (start: string) => start.slice(11, 16);
export const plural = (n: number, one: string, few: string, many: string) => {
  const m = n % 10, h = n % 100;
  return m === 1 && h !== 11 ? one : m >= 2 && m <= 4 && (h < 12 || h > 14) ? few : many;
};
export function fmtPhone(raw: string) {
  let d = raw.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "8") d = "7" + d.slice(1);
  if (d.length === 10) d = "7" + d;
  if (d.length === 11 && d[0] === "7") return `+7 ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
  return d ? "+" + d : raw;
}
export const toMin = (t: string) => +t.slice(0, 2) * 60 + +t.slice(3, 5);
export const fromMin = (m: number) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
export const STATUS_LABEL: Record<string, string> = {
  pending: "Ждёт подтверждения", confirmed: "Подтверждена", done: "Визит состоялся", cancelled: "Отменена", expired: "Не подтверждена",
};
