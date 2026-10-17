/**
 * What the phone remembers. Customers have no accounts: their bookings (number + access token), their details
 * for the next booking and their chat live in AsyncStorage. The staff sign-in token is kept encrypted in
 * SecureStore.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import type { Booking } from './types';

const BOOKINGS = 'zch.bookings';
const CUSTOMER = 'zch.customer';
const CHAT = 'zch.chat';
const STAFF_TOKEN = 'zch.staff_token';

export type SavedBooking = Pick<Booking, 'ref' | 'token' | 'car' | 'car_photo' | 'pickup_date' | 'return_date' | 'status' | 'status_label' | 'city'>;
export type Customer = { name: string; phone: string; email: string };

async function readJson<T>(key: string, fallback: T): Promise<T> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const savedBookings = () => readJson<SavedBooking[]>(BOOKINGS, []);

/** Adds or refreshes a booking in "My bookings" (newest first). */
export async function saveBooking(b: Booking) {
  if (!b.token) return;
  const list = (await savedBookings()).filter((s) => s.ref !== b.ref);
  const item: SavedBooking = {
    ref: b.ref, token: b.token, car: b.car, car_photo: b.car_photo, pickup_date: b.pickup_date,
    return_date: b.return_date, status: b.status, status_label: b.status_label, city: b.city,
  };
  await AsyncStorage.setItem(BOOKINGS, JSON.stringify([item, ...list].slice(0, 50)));
}

export async function forgetBooking(ref: string) {
  const list = (await savedBookings()).filter((s) => s.ref !== ref);
  await AsyncStorage.setItem(BOOKINGS, JSON.stringify(list));
}

export const savedCustomer = () => readJson<Customer>(CUSTOMER, { name: '', phone: '', email: '' });
export const saveCustomer = (c: Customer) => AsyncStorage.setItem(CUSTOMER, JSON.stringify(c));

export const savedChatId = async () => {
  try {
    return await AsyncStorage.getItem(CHAT);
  } catch {
    return null;
  }
};
export const saveChatId = (id: string | null) => (id ? AsyncStorage.setItem(CHAT, id) : AsyncStorage.removeItem(CHAT));

export const staffToken = async () => {
  try {
    return await SecureStore.getItemAsync(STAFF_TOKEN);
  } catch {
    return null;
  }
};
export const saveStaffToken = (token: string | null) =>
  token ? SecureStore.setItemAsync(STAFF_TOKEN, token) : SecureStore.deleteItemAsync(STAFF_TOKEN);
