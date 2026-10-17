import { useQuery } from '@tanstack/react-query';

import { get } from '@/lib/api';
import type { Config } from '@/lib/types';

/** Branches, extras and booking rules. Fetched once, refreshed every 10 minutes. */
export function useConfig() {
  return useQuery({ queryKey: ['config'], queryFn: () => get<Config>('config/'), staleTime: 10 * 60 * 1000 });
}
