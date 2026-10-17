/**
 * Keeps the last car lists and settings on the phone, so the app opens with them straight away and refreshes in the
 * background instead of showing a spinner. Only public data is kept: never staff data.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { QueryClient, QueryKey } from '@tanstack/react-query';

const STORE = 'warm-cache-v1';
const KEEP = new Set(['config', 'cars']);
const MAX_AGE = 7 * 24 * 60 * 60 * 1000;
const MAX_ENTRIES = 12;

type Entry = { key: QueryKey; data: unknown; updatedAt: number };

export async function restoreWarmCache(qc: QueryClient) {
  try {
    const entries: Entry[] = JSON.parse((await AsyncStorage.getItem(STORE)) || '[]');
    const now = Date.now();
    for (const e of entries) {
      // updatedAt keeps them stale, so the screens still fetch fresh data as soon as they open.
      if (now - e.updatedAt < MAX_AGE) qc.setQueryData(e.key, e.data, { updatedAt: e.updatedAt });
    }
  } catch {
    // A broken or missing cache just means a normal first load.
  }
}

export function keepWarmCache(qc: QueryClient) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    const entries: Entry[] = qc.getQueryCache().getAll()
      .filter((q) => KEEP.has(String(q.queryKey[0])) && q.state.status === 'success' && q.state.data !== undefined)
      .sort((a, b) => b.state.dataUpdatedAt - a.state.dataUpdatedAt)
      .slice(0, MAX_ENTRIES)
      .map((q) => ({ key: q.queryKey, data: q.state.data, updatedAt: q.state.dataUpdatedAt }));
    AsyncStorage.setItem(STORE, JSON.stringify(entries)).catch(() => {});
  };
  return qc.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success' || !KEEP.has(String(event.query.queryKey[0]))) return;
    clearTimeout(timer);
    timer = setTimeout(save, 1000);
  });
}
