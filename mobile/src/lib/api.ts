/**
 * Talks to the Django API. The address comes from EXPO_PUBLIC_API_URL (see .env.example); it defaults to the
 * live site. Errors carry the server's message (already written for customers) and the field it concerns.
 */
export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'https://www.zidicarhire.com').replace(/\/+$/, '');

export class ApiError extends Error {
  status: number;
  field?: string;
  data: Record<string, unknown>;

  constructor(message: string, status: number, data: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.field = typeof data.field === 'string' ? data.field : undefined;
    this.data = data;
  }
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export type RequestOptions = {
  params?: Params;
  body?: unknown;
  form?: FormData;
  token?: string | null;          // staff sign-in
  bookingToken?: string | null;   // a customer's booking
  method?: 'GET' | 'POST';
};

function query(params?: Params) {
  if (!params) return '';
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    if (Array.isArray(value)) value.forEach((v) => q.append(key, String(v)));
    else q.append(key, String(value));
  });
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (opts.token) headers.Authorization = `Token ${opts.token}`;
  if (opts.bookingToken) headers['X-Booking-Token'] = opts.bookingToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  const method = opts.method ?? (body ? 'POST' : 'GET');

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/${path.replace(/^\/+/, '')}${query(opts.params)}`, { method, headers, body });
  } catch {
    throw new ApiError("You're offline or the connection dropped. Check your internet and try again.", 0);
  }
  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    const message = typeof data.error === 'string' ? data.error : `Something went wrong (error ${res.status}). Try again.`;
    throw new ApiError(message, res.status, data);
  }
  return data as T;
}

export const get = <T>(path: string, opts: Omit<RequestOptions, 'body' | 'method'> = {}) => request<T>(path, { ...opts, method: 'GET' });
export const post = <T>(path: string, body: unknown = {}, opts: Omit<RequestOptions, 'body' | 'method'> = {}) =>
  request<T>(path, { ...opts, body, method: 'POST' });

/** Media and receipt links from the API are absolute; relative ones (photo upload replies) get the API host. */
export const absoluteUrl = (url: string) => (!url || /^https?:/.test(url) ? url : `${API_URL}${url}`);
