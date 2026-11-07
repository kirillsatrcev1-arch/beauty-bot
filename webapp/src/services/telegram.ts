/* Тонкая обёртка над Telegram WebApp SDK: работает и вне Telegram (в браузере, в демо). */

interface TgWebApp {
  initData: string;
  initDataUnsafe?: { user?: { first_name?: string; photo_url?: string } };
  colorScheme?: "light" | "dark";
  ready(): void;
  expand(): void;
  close(): void;
  openLink(url: string): void;
  openTelegramLink(url: string): void;
  setHeaderColor?(c: string): void;
  setBackgroundColor?(c: string): void;
  setBottomBarColor?(c: string): void;
  disableVerticalSwipes?(): void;
  HapticFeedback?: { impactOccurred(s: string): void; notificationOccurred(s: string): void; selectionChanged(): void };
  BackButton?: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
}

declare global {
  interface Window { Telegram?: { WebApp?: TgWebApp } }
}

export const tg: TgWebApp | undefined = window.Telegram?.WebApp?.initData !== undefined ? window.Telegram?.WebApp : undefined;
export const inTelegram = !!tg && !!tg.initData;

export function initTelegram(bg: string) {
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor?.(bg);
    tg.setBackgroundColor?.(bg);
    tg.setBottomBarColor?.(bg);
    tg.disableVerticalSwipes?.();
  } catch { /* старые клиенты Telegram */ }
}

export const haptic = {
  tap: () => { try { tg?.HapticFeedback?.impactOccurred("light"); } catch { /* */ } },
  select: () => { try { tg?.HapticFeedback?.selectionChanged(); } catch { /* */ } },
  success: () => { try { tg?.HapticFeedback?.notificationOccurred("success"); } catch { /* */ } },
  error: () => { try { tg?.HapticFeedback?.notificationOccurred("error"); } catch { /* */ } },
};

export function openLink(url: string) {
  const abs = url.startsWith("http") ? url : new URL(url, location.href).toString();
  if (abs.startsWith("https://t.me/") && tg) return tg.openTelegramLink(abs);
  if (tg) return tg.openLink(abs);
  window.open(abs, "_blank", "noopener");
}

/** Системная кнопка «Назад» Telegram: показываем, пока есть обработчик. */
let current: (() => void) | null = null;
export function setBackButton(cb: (() => void) | null) {
  const bb = tg?.BackButton;
  if (!bb) return;
  if (current) bb.offClick(current);
  current = cb;
  if (cb) { bb.onClick(cb); bb.show(); } else bb.hide();
}
