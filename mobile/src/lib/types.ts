/** Shapes returned by the Django API (/api/v1/). Keep in step with api/views.py and api/staff.py. */

export type Choice = { value: string; label: string };

export type Branch = {
  slug: string;
  name: string;
  city: string;
  county: string;
  address: string;
  opening_hours: string;
  phone: string;
  whatsapp: string;
  maps_url: string;
  latitude: number | null;
  longitude: number | null;
  pickup_points?: { id: number; name: string; fee: number }[];
  routes?: { to: string; name: string; fee: number }[];
};

export type Config = {
  business: { name: string; phone: string; whatsapp: string; email: string; till_name: string; site_url: string };
  branches: Branch[];
  extras: { id: number; name: string; description: string; price: number; per_day: boolean }[];
  categories: Choice[];
  transmissions: Choice[];
  seat_choices: { value: number; label: string }[];
  sort_choices: Choice[];
  booking: {
    times: string[];
    default_time: string;
    min_days: number;
    max_days: number;
    min_fee: number;
    prompt_seconds: number;
    hold_minutes: number;
  };
  links: { terms: string; privacy: string; faq: string };
};

export type Car = {
  id: number;
  name: string;
  category: string;
  category_label: string;
  transmission: string;
  transmission_label: string;
  fuel: string;
  fuel_label: string;
  seats: number;
  doors: number;
  luggage: number;
  engine_size: string;
  air_con: boolean;
  price_per_day: number;
  weekly_rate: number | null;
  monthly_rate: number | null;
  booking_fee: number;
  location: { slug: string; name: string };
  photo: string;
  web_url: string;
  days?: number;
  available?: boolean;
  total?: number;
  rate_type?: string;
};

export type CarList = {
  location: Branch | null;
  from: string;
  to: string;
  days: number;
  total_count: number;
  cars: Car[];
  suggestions: { slug: string; name: string; free_cars: number; distance_km: number | null }[];
};

export type CarDetail = {
  car: Car & {
    description: string;
    features: string[];
    photos: { url: string; thumb: string; width: number; height: number }[];
    prices: { label: string; per_day: number; note: string }[];
  };
  branch: Branch;
  unavailable: string[];
  from: string;
  to: string;
};

export type PriceLine = { label: string; amount: number; total?: boolean };

export type Quote = {
  total: number;
  days: number;
  breakdown: PriceLine[];
  one_way: boolean;
  min_pay: number;
  pickup: string;
  return: string;
  available: boolean;
};

export type BookingStatus = 'pending' | 'paid' | 'picked_up' | 'completed' | 'cancelled' | 'failed';

export type Booking = {
  ref: string;
  status: BookingStatus;
  status_label: string;
  amount: number;
  pay_now: number;
  amount_paid: number;
  balance: number;
  days: number;
  car: string;
  car_id?: number;
  car_photo?: string;
  pickup_date: string;
  pickup_time: string;
  return_date: string;
  return_time: string;
  phone: string;
  receipt: string;
  message: string;
  city: string;
  pickup_point: string;
  return_city: string;
  breakdown: PriceLine[];
  token?: string;
  detail_url?: string;
  ics_url?: string;
  receipt_url?: string;
  receipt_page_url?: string;
};

export type StaffUser = {
  username: string;
  name: string;
  branch: { slug: string; name: string } | null;
  is_owner: boolean;
  branches: { slug: string; name: string }[];
};

export type AdminBooking = Booking & {
  customer_name: string;
  email: string;
  city_slug: string;
  notes: string;
  awaiting_relocation: boolean;
  result_desc: string;
  created: string;
  paid_at: string;
};

export type AdminBookingDetail = AdminBooking & {
  id_number: string;
  licence_number: string;
  whatsapp_link: string;
  allowed: Record<'pickup' | 'return' | 'cancel' | 'mark_paid' | 'balance' | 'dates' | 'resend' | 'receipt' | 'relocate', boolean>;
  events: { kind: string; label: string; who: string; message: string; at: string }[];
  payments: { status: string; label: string; amount: number; phone: string; receipt: string; result: string; at: string }[];
};

export type Stats = {
  paid_today: number;
  revenue_today: number;
  revenue_month: number;
  on_the_road: number;
  awaiting_payment: number;
  returning: number;
};

export type Overview = {
  today: string;
  city: string;
  stats: Stats;
  pickups: AdminBooking[];
  returns: AdminBooking[];
  out: AdminBooking[];
  awaiting: AdminBooking[];
  latest: AdminBooking[];
};

export type ChatMessage = { id: number; sender: 'visitor' | 'bot' | 'admin'; label: string; body: string; time: string };

export type StaffChat = {
  id: string;
  name: string;
  contact: string;
  city: string;
  city_id: number | '';
  unread: number;
  wants_agent: boolean;
  preview: string;
  time: string;
};
