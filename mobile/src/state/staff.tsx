/** Staff sign-in for the whole app: the token lives in SecureStore, the profile comes from the API. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';

import { ApiError, get, post } from '@/lib/api';
import { saveStaffToken, staffToken } from '@/lib/storage';
import type { StaffUser } from '@/lib/types';

type StaffState = {
  ready: boolean;
  token: string | null;
  user: StaffUser | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Calls the staff API with the token; a 401 signs the phone out. */
  call: <T>(fn: (token: string) => Promise<T>) => Promise<T>;
};

const StaffContext = createContext<StaffState | null>(null);

export function StaffProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<StaffUser | null>(null);
  const queryClient = useQueryClient();

  const forget = useCallback(async () => {
    await saveStaffToken(null);
    setToken(null);
    setUser(null);
    queryClient.removeQueries({ queryKey: ['staff'] });
  }, [queryClient]);

  useEffect(() => {
    (async () => {
      const saved = await staffToken();
      if (saved) {
        try {
          const res = await get<{ user: StaffUser }>('staff/me/', { token: saved });
          setToken(saved);
          setUser(res.user);
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) await saveStaffToken(null);
          else setToken(saved);   // offline: keep the sign-in, the profile loads later
        }
      }
      setReady(true);
    })();
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const res = await post<{ token: string; user: StaffUser }>('staff/login/', {
      username, password, device: `${Platform.OS} app`,
    });
    await saveStaffToken(res.token);
    setToken(res.token);
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    if (token) {
      try {
        await post('staff/logout/', {}, { token });
      } catch {
        /* signed out on the phone either way */
      }
    }
    await forget();
  }, [token, forget]);

  const call = useCallback(async <T,>(fn: (t: string) => Promise<T>) => {
    if (!token) throw new ApiError('Sign in again.', 401);
    try {
      return await fn(token);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) await forget();
      throw err;
    }
  }, [token, forget]);

  const value = useMemo(() => ({ ready, token, user, signIn, signOut, call }), [ready, token, user, signIn, signOut, call]);
  return <StaffContext.Provider value={value}>{children}</StaffContext.Provider>;
}

export function useStaff() {
  const ctx = useContext(StaffContext);
  if (!ctx) throw new Error('useStaff needs <StaffProvider>');
  return ctx;
}
