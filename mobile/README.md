# ZIDICARHIRE mobile app

React Native app (Expo SDK 58, TypeScript, Expo Router) for customers and staff. It talks only to the Django
site's mobile API at `/api/v1/` (see `api/` in the main project), so prices, availability, M-Pesa payments,
receipts and chats are exactly the same as on the website.

## What's in it

**Customers** (no account needed)
- Home: city, dates, search; branches; how it works
- Cars: filters (type, gearbox), sorting, nearby branches when nothing is free
- Car page: photos, specs, features, prices, branch, live total for the dates
- Booking: dates (booked days blocked), times, pick-up point, one-way return, extras, details, M-Pesa payment
  (booking fee, half or full), waiting screen with countdown and resend, confirmation with receipt and calendar
- My bookings: every booking made or found on the phone, with live status, receipt and help
- Chat: the website's assistant and team, with "Talk to a person"

**Staff** (More → Staff sign in, with the website dashboard username and password)
- Today: takings, cars out, waiting for payment; pick-ups, returns, out now and waiting lists
- Bookings: search and filter; every dashboard action (picked up, returned, cancel, mark paid, balance payment,
  change dates, resend email, notes, one-way arrivals)
- Chats: inbox with unread counts, replies
- Cars: show or hide on the website, add photos from the camera
- The phone buzzes for new paid bookings while the staff app is open

## Run it on your phone

```
cd mobile
npm install
copy .env.example .env      (Windows; cp on Mac/Linux) and set EXPO_PUBLIC_API_URL if needed
npx expo start
```

Install **Expo Go** from the Play Store, then scan the QR code shown in the terminal.

To use your own computer's Django instead of the live site, run Django with
`python manage.py runserver 0.0.0.0:8000`, add your computer's Wi-Fi IP address to `ALLOWED_HOSTS`, and set
`EXPO_PUBLIC_API_URL=http://<that address>:8000` in `mobile/.env`. Keep `FAKE_PAYMENTS=true` while testing so no
real M-Pesa prompts are sent.

## Build the Android app

Builds run in Expo's cloud (EAS); no Android Studio needed.

```
npx eas-cli@latest login
npx eas-cli@latest build --profile preview --platform android     # an .apk to install and share for testing
npx eas-cli@latest build --profile production --platform android  # an .aab for the Play Store
```

`eas.json` holds the build profiles. Every build uses the live site unless `EXPO_PUBLIC_API_URL` says otherwise.
iPhone builds use the same commands with `--platform ios` and need an Apple Developer account.

The cloud build installs packages with `npm ci` on Node 22 (npm 10). After adding or updating a package, refresh the
lock file with that npm so the build accepts it: `npx npm@10 install --package-lock-only`.

## Checks

```
npx tsc --noEmit
npx expo lint
npx expo-doctor
```

## How it signs in and keeps data

- A customer's booking is opened with its signed token (the same one in the confirmation email links), kept in
  the phone's storage with the booking number. There are no customer accounts or passwords.
- Staff sign in once; the API returns a token that is stored encrypted (SecureStore). Only a hash of it is kept
  on the server. Signing out deletes it; it also stops working after 60 days unused, or if the person loses
  staff access. The Django admin lists every signed-in phone under "App sign-ins".
