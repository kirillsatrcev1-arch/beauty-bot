export type Status = "pending" | "confirmed" | "done" | "cancelled" | "expired";

export interface Service {
  id: number;
  category: string;
  title: string;
  description: string;
  price: number;
  price_from: boolean;
  duration: number;
  photo: string | null;
  active: boolean;
  master_ids: number[];
}

export interface Category { id: string; title: string; emoji: string; photo: string | null; count: number }

export interface Master {
  id: number; name: string; role: string; bio: string; photo: string | null; active: boolean; service_ids: number[];
  work_days: string | null; work_start: string | null; work_end: string | null; break_start: string | null; break_end: string | null;
}

export interface Section { id: string; title: string; emoji: string; count: number; cover: string | null }
export interface Work { id: number; section: string; src: string; orig: string; caption: string }
export interface Review { name: string; rating: number; text: string; created_at: string }

export interface Booking {
  id: number; user_id: number; service_id: number | null; service_title: string; price: number; price_from: boolean;
  duration: number; date: string; start: string; end: string; status: Status; name: string; phone: string;
  comment: string | null; client_confirmed: number; master_id: number; master_name: string | null; source?: string;
  created_at?: string; cancel_reason?: string | null; ics?: string;
}

export interface Studio {
  name: string; logo: string | null; master: string; about: string; address: string; address_hint: string; map_url: string;
  contact_text: string; contact_username: string; contact_phone: string; channel_url: string; instagram_url: string; vk_url: string;
  cancel_rules: string; cancel_min_hours: number; why_us: string[]; about_photo: string | null; hero_photo: string | null;
}

export interface Boot {
  studio: Studio;
  categories: Category[];
  services: Service[];
  masters: Master[];
  portfolio: Section[];
  reviews: Review[];
  favorites: number[];
  nearest: { service_id: number; date: string; time: string } | null;
  user: { id: number; name: string; first_name: string; phone: string; photo_url?: string | null; is_admin: boolean };
}

export interface Slot { time: string; masters: number[] }
export type DayState = "free" | "busy" | "off" | "past";
