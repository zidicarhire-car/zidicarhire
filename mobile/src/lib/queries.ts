/** Query definitions shared by more than one screen, so a prefetch and the screen use the same cache entry. */
import { get } from './api';
import type { CarList } from './types';

export type CarFilters = { city: string; from: string; to: string; category?: string; transmission?: string; sort?: string };

export function carsQuery(f: CarFilters) {
  const params = { city: f.city, from: f.from, to: f.to, category: f.category ?? '', transmission: f.transmission ?? '', sort: f.sort ?? 'recommended' };
  return { queryKey: ['cars', params] as const, queryFn: () => get<CarList>('cars/', { params }) };
}
