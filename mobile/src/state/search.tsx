/** The customer's city and dates, shared by Home, Cars and car pages (like the website's search card). */
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

import { addDays, today } from '@/lib/format';

type Search = {
  city: string;
  from: string;
  to: string;
  setCity: (slug: string) => void;
  setDates: (from: string, to: string) => void;
};

const SearchContext = createContext<Search | null>(null);

export function SearchProvider({ children }: { children: ReactNode }) {
  const tomorrow = addDays(today(), 1);
  const [city, setCity] = useState('nairobi');
  const [from, setFrom] = useState(tomorrow);
  const [to, setTo] = useState(addDays(tomorrow, 3));
  const value = useMemo(() => ({
    city, from, to, setCity,
    setDates: (f: string, t: string) => { setFrom(f); setTo(t); },
  }), [city, from, to]);
  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>;
}

export function useSearch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error('useSearch needs <SearchProvider>');
  return ctx;
}
