import { useEffect, useState } from "react";
import { Button, Field, Skeleton, Toggle } from "../components/ui";
import { useApp } from "../hooks/useApp";
import { api, errorText } from "../services/api";
import { Panel, PhotoInput, useLoad } from "./shared";

type S = Record<string, string | null>;

export function SettingsAdmin() {
  const { toast } = useApp();
  const { data } = useLoad<{ settings: S; webapp_url: string }>("/api/admin/settings");
  const [s, setS] = useState<S | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) setS(data.settings); }, [data]);
  if (!s) return <Skeleton className="h-96" />;

  const set = (k: string) => (e: { target: { value: string } }) => setS({ ...s, [k]: e.target.value });
  const flag = (k: string) => s[k] === "1";
  const save = async () => {
    setBusy(true);
    const body = Object.fromEntries(Object.entries(s).filter(([k]) => !k.endsWith("_url") || ["map_url", "channel_url", "instagram_url", "vk_url"].includes(k)));
    try { await api.post("/api/admin/settings", body); toast("Настройки сохранены"); } catch (e) { toast(errorText(e)); } finally { setBusy(false); }
  };
  const input = (k: string, label: string, ph = "", hint?: string) => <Field label={label} hint={hint}><input className="input" value={s[k] || ""} onChange={set(k)} placeholder={ph} /></Field>;

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div><div className="eyebrow">Студия</div><h1 className="h-display mt-1 text-[38px]">Настройки</h1></div>
        <Button size="sm" disabled={busy} onClick={save}>{busy ? "Сохраняю…" : "Сохранить"}</Button>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="Студия">
          <div className="mb-4 flex items-center gap-4">
            <PhotoInput value={s.logo} url={s.logo_url} onChange={(v, u) => setS({ ...s, logo: v || "", logo_url: u })} className="h-20 w-20 shrink-0 !rounded-full" label="Лого" />
            <div className="flex-1">{input("studio_name", "Название студии")}</div>
          </div>
          {input("master_name", "Имя мастера (для чата)")}
          <Field label="О студии / мастере"><textarea className="input min-h-[120px] resize-none" value={s.about_text || ""} onChange={set("about_text")} /></Field>
          <Field label="Почему выбирают нас" hint="Каждый пункт через вертикальную черту |"><input className="input" value={s.why_us || ""} onChange={set("why_us")} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <div><div className="mb-1.5 ml-1 text-[12px] font-semibold text-muted">Фото на главной</div>
              <PhotoInput value={s.photo_welcome} url={s.photo_welcome_url} onChange={(v, u) => setS({ ...s, photo_welcome: v || "", photo_welcome_url: u })} className="h-36 w-full" label="Главное фото" /></div>
            <div><div className="mb-1.5 ml-1 text-[12px] font-semibold text-muted">Фото мастера</div>
              <PhotoInput value={s.photo_about} url={s.photo_about_url} onChange={(v, u) => setS({ ...s, photo_about: v || "", photo_about_url: u })} className="h-36 w-full" label="Фото" /></div>
          </div>
        </Panel>
        <Panel title="Адрес и контакты">
          {input("address_text", "Адрес", "г. Москва, ул. …")}
          {input("address_hint", "Как пройти", "Вход со двора, домофон 12")}
          {input("map_url", "Ссылка на карту", "https://yandex.ru/maps/…")}
          {input("contact_phone", "Телефон", "+7 900 000-00-00")}
          {input("contact_username", "Telegram мастера", "username без @")}
          {input("contact_text", "Текст «Связаться»")}
          {input("instagram_url", "Instagram", "https://instagram.com/…")}
          {input("vk_url", "ВКонтакте", "https://vk.com/…")}
        </Panel>
        <Panel title="Telegram-канал и подписка">
          {input("channel_id", "ID канала", "@my_channel или -100…", "Бот должен быть администратором канала")}
          {input("channel_url", "Ссылка на канал", "https://t.me/…")}
          <div className="card px-4"><Toggle on={flag("sub_required")} onChange={(v) => setS({ ...s, sub_required: v ? "1" : "0" })} label="Обязательная подписка перед записью" /></div>
        </Panel>
        <Panel title="Правила и уведомления">
          <Field label="Правила отмены (видят клиентки)"><textarea className="input min-h-[90px] resize-none" value={s.cancel_rules || ""} onChange={set("cancel_rules")} /></Field>
          {input("cancel_min_hours", "Отмена/перенос не позднее чем за, ч")}
          <div className="card divide-y divide-line px-4">
            <Toggle on={flag("auto_confirm")} onChange={(v) => setS({ ...s, auto_confirm: v ? "1" : "0" })} label="Подтверждать записи автоматически" />
            <Toggle on={flag("remind_24")} onChange={(v) => setS({ ...s, remind_24: v ? "1" : "0" })} label="Напоминание за 24 часа" />
            <Toggle on={flag("remind_2")} onChange={(v) => setS({ ...s, remind_2: v ? "1" : "0" })} label="Напоминание за 2 часа" />
            <Toggle on={flag("notify_new_clients")} onChange={(v) => setS({ ...s, notify_new_clients: v ? "1" : "0" })} label="Сообщать мне о новых клиентах" />
          </div>
        </Panel>
      </div>
      <Button size="lg" className="mt-4 w-full lg:w-auto" disabled={busy} onClick={save}>{busy ? "Сохраняю…" : "Сохранить настройки"}</Button>
    </div>
  );
}
