/** Money, dates and phone numbers, written the way the website writes them. */

export const kes = (n: number | null | undefined) => `KES ${Math.round(Number(n || 0)).toLocaleString('en-KE')}`;

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-10-16" -> a local Date at noon (no time-zone surprises). */
export const parseDay = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d, 12);
};
export const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const addDays = (iso: string, n: number) => {
  const d = parseDay(iso);
  d.setDate(d.getDate() + n);
  return isoDay(d);
};
export const daysBetween = (a: string, b: string) => Math.round((parseDay(b).getTime() - parseDay(a).getTime()) / 86400000);
export const today = () => isoDay(new Date());

/** "Fri 16 Oct" */
export const fmtDay = (iso: string) => {
  const d = parseDay(iso);
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
};

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** 0712 345 678 or +254 712 345 678, as people write it. */
export function formatPhone(raw: string) {
  const plus = raw.trim().startsWith('+');
  const digits = raw.replace(/\D/g, '');
  if (plus || digits.startsWith('254')) {
    const d = digits.slice(0, 12);
    return (plus ? '+' : '') + [d.slice(0, 3), d.slice(3, 6), d.slice(6, 9), d.slice(9, 12)].filter(Boolean).join(' ');
  }
  const d = digits.slice(0, 10);
  return [d.slice(0, 4), d.slice(4, 7), d.slice(7, 10)].filter(Boolean).join(' ');
}

/** The same checks as the website's booking form (the server checks again). */
export const RULES: Record<string, (v: string) => string> = {
  name: (v) => (v.trim().length >= 2 ? '' : 'Enter your full name as it appears on your ID.'),
  phone: (v) =>
    /^(?:\+?254|0)?[17]\d{8}$/.test(v.replace(/[\s-]/g, ''))
      ? ''
      : 'Enter the Safaricom number that will pay, like 0712 345 678 or 0110 123 456.',
  email: (v) =>
    !v.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) ? '' : 'That email address looks incomplete. Check it, or leave it blank.',
  id_number: (v) =>
    /^[A-Z0-9]{6,12}$/.test(v.replace(/[\s-]/g, '').toUpperCase()) ? '' : 'Enter your national ID number (7 or 8 digits) or your passport number.',
  licence_number: (v) =>
    /^[A-Z0-9][A-Z0-9/-]{3,19}$/.test(v.replace(/\s/g, '').toUpperCase()) ? '' : 'Enter the number on your driving licence (letters, numbers and dashes).',
};
