# ZIDICARHIRE

Car hire website for zidicarhire.com, serving all of Kenya from branches in the major cities.
Customers choose a city, dates and a car, pick where to collect it (branch, airport or hotel), pay with
an M-Pesa prompt (through PayHero to your Safaricom till) and get a confirmation and PDF receipt
straight away. You run everything from a dashboard: bookings, a calendar, cars and photos, branches,
reports and live chat, with an alert the moment a booking is paid.

## What's inside

| App | Does |
|---|---|
| `fleet` | Branches, pick-up points, one-way routes, cars and photos, extras, home/city/car pages, sitemap |
| `bookings` | Booking popup API, server-side pricing, receipts (PDF), calendar files, Find my booking, emails |
| `payments` | PayHero STK push, payment callback, a record of every payment attempt |
| `chat` | Visitor live chat |
| `dashboard` | Staff dashboard: today, bookings, calendar, cars, chat, reports, branches, payment settings check |
| `pages` | About, Contact (messages saved and emailed), FAQ, Terms, Privacy |

Live updates use short polling (every few seconds), which works on a normal PythonAnywhere web app.
No WebSockets, Redis or background workers.

## 1. Run it on your computer

```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Mac/Linux: cp .env.example .env
```

Open `.env` and set at least:

```
SECRET_KEY=<paste the output of: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=true
FAKE_PAYMENTS=true
```

Then:

```bash
python manage.py migrate
python manage.py seed_locations      # the branches and their pick-up points
python manage.py createsuperuser     # your dashboard login
python manage.py seed_cars           # optional sample cars (Nairobi)
python manage.py runserver
```

- Website: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard/
- Django admin (staff accounts, extras, contact messages): http://localhost:8000/django-admin/

Run the tests with `python manage.py test`.

## 2. Filling in .env

Every setting lives in `.env` (never upload it anywhere; it is in `.gitignore`). Anything still
saying `FILL_ME` is treated as empty, so the site never uses a placeholder by mistake.

| Setting | What to put |
|---|---|
| `SECRET_KEY` | A long random string (command above). Required when `DEBUG=false`. |
| `DEBUG` | `true` on your computer, `false` on the live site. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` | Your domain(s), see the comments in `.env.example`. |
| `PAYHERO_AUTH_TOKEN` *or* `PAYHERO_API_USERNAME` + `PAYHERO_API_PASSWORD` | From PayHero > API Keys. |
| `PAYHERO_CHANNEL_ID` | PayHero > Payment Channels, the channel linked to your till. |
| `MPESA_TILL_NUMBER`, `MPESA_ACCOUNT_NAME` | Shown on the waiting screen and receipts. |
| `FAKE_PAYMENTS` | `true` for testing (no real prompts), `false` to take real money. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `ADMIN_NOTIFY_EMAILS` | Gmail with an App Password (Google Account > Security > App passwords). Until the email login is filled in, emails are printed in the server log. |
| `BUSINESS_*`, `KRA_PIN` | Shown on the website, emails and receipts. `KRA_PIN` is optional. |
| `BUSINESS_OPEN_TIME`, `BUSINESS_CLOSE_TIME` | Pick-up and return times are offered every 30 minutes between these. |
| `MIN_RENTAL_DAYS`, `MAX_RENTAL_DAYS`, `BOOKING_HOLD_MINUTES` | Booking rules. |
| `MAX_UPLOAD_MB` | Largest car photo staff can upload. |

The dashboard's **Payment settings check** page shows which of these are filled (never their values)
and can send you a KES 1 test prompt. If payments are switched on but PayHero details are missing,
every dashboard page shows a red warning.

## 3. Testing payments on your computer

PayHero can't send payment results to `localhost`. You have three options:

1. **`FAKE_PAYMENTS=true`** (easiest): no real prompt is sent and each booking pays itself about
   8 seconds after you click Pay. Use this to check the whole flow, emails and receipts.
2. **A tunnel** such as ngrok: run `ngrok http 8000`, set `SITE_URL` to the `https://...ngrok...` address,
   add that host to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, set `FAKE_PAYMENTS=false`, restart, and
   PayHero's callback will reach your computer.
3. **No tunnel, real prompts**: with `FAKE_PAYMENTS=false` and a localhost `SITE_URL`, the customer's
   screen still confirms the payment: about 25 seconds after the prompt, the site asks PayHero
   directly (the status-check fallback). It's slower, but it works.

To test the real till end to end, use the **Send test STK push for KES 1** button on the Payment
settings check page.

### Checking the look on phones and desktops

`tools/screenshots.py` (only for your computer, never the server) runs the site against a throwaway
database with fake payments, so your own data is never touched:

```
pip install -r requirements-dev.txt
python -m playwright install chromium
python tools/screenshots.py --check   # a full booking with receipt, a chat with a staff reply, dashboard actions
python tools/screenshots.py           # the same, plus every page at 375, 768 and 1440 px, light and dark
```

Screenshots land in `tools/screenshots/`. It stops with a list of problems if a flow breaks, a page
scrolls sideways, a button or field has no accessible name, or the receipt doesn't print on one A4 page.

## 4. Deploying to PythonAnywhere

**Plan:** a paid plan (Hacker, about $5/month). The free plan can't use a custom domain and blocks
requests to PayHero.

### First time

1. Upload the code (`git clone` in a Bash console, or upload a zip and `unzip` it).
2. `mkvirtualenv --python=python3.12 zidienv`, then `cd ~/zidicarhire && pip install -r requirements.txt`.
3. `cp .env.example .env` and fill it in (Files tab). Set `DEBUG=false`, a real `SECRET_KEY`, your hosts
   and `SITE_URL=https://www.zidicarhire.com`.
4. Run:
   ```bash
   python manage.py migrate
   python manage.py seed_locations
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```
5. **Web tab > Add a new web app** > `www.zidicarhire.com` > Manual configuration > same Python version.
   - Virtualenv: `/home/YOURUSERNAME/.virtualenvs/zidienv`
   - WSGI file: replace everything with
     ```python
     import os, sys
     path = '/home/YOURUSERNAME/zidicarhire'
     if path not in sys.path:
         sys.path.insert(0, path)
     os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
     from django.core.wsgi import get_wsgi_application
     application = get_wsgi_application()
     ```
   - Static files: `/static/` → `/home/YOURUSERNAME/zidicarhire/staticfiles` and
     `/media/` → `/home/YOURUSERNAME/zidicarhire/media`
   - Turn on **Force HTTPS** and click **Reload**.
6. Point your domain's `www` CNAME at the address the Web tab shows, then enable the free HTTPS certificate.
7. Fill in PayHero in `.env`, set `FAKE_PAYMENTS=false`, Reload, and send a KES 1 test prompt from the
   dashboard's Payment settings check page.

### Every update

```bash
cd ~/zidicarhire
git pull                                # or upload the new files
workon zidienv
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** on the Web tab. Also Reload after any change to `.env`.
Migrations come with the code: don't run `makemigrations` on the server.

## 5. Day-to-day

- **Branches, pick-up points and one-way routes:** dashboard > Branches / One-way routes.
- **Cars:** dashboard > Cars and prices. Drop several photos at once; drag to reorder; the cover photo
  shows on car cards. Optional weekly and monthly prices apply automatically to 7+ and 30+ day hires.
- **Extras** (child seat, extra driver...): Django admin > Fleet > Extras.
- **Branch staff:** Django admin > Users: tick "Staff status" and choose their branch at the bottom.
  They only see that branch's cars, bookings and chats.
- **Bookings:** dashboard > Bookings (search, filters, CSV) and Calendar. Open a booking to mark it
  picked up or returned, cancel it with a reason, mark it paid with an M-Pesa code, change its dates,
  resend the confirmation or download the receipt. M-Pesa refunds are always done by hand from your till.
- **Website text to finish:** the About, FAQ, Terms and Privacy pages contain yellow
  "Owner to edit/confirm" notes. Edit `templates/pages/*.html` and the answers in `pages/content.py`
  (set `confirmed=True` when an answer is final).

## How payments are protected

- The car is held for `BOOKING_HOLD_MINUTES` while the customer pays, so two people can't pay for it.
- Prices, day counts and availability are always worked out again on the server.
- PayHero's callback must match the stored `CheckoutRequestID` and the full amount, and is double-checked
  with PayHero's transaction-status API before a booking is marked paid. Marking paid only happens once.
- If no callback arrives, the customer's page asks PayHero directly after about 25 seconds.
- Every prompt is stored as a payment attempt (with PayHero's raw reply), visible on the booking.
- Receipts and calendar files need a signed link, the browser that booked, or a staff login.
- Booking, retry, chat, contact and Find my booking are rate-limited per IP.

## Backups

Your data is in `db.sqlite3` and car photos in `media/`. Download both from the Files tab regularly,
or add a PythonAnywhere scheduled task, for example daily:

```bash
cd ~/zidicarhire && mkdir -p ~/backups && sqlite3 db.sqlite3 ".backup ~/backups/db-$(date +%F).sqlite3" && tar czf ~/backups/media-$(date +%F).tgz media
```

Keep a copy somewhere other than PythonAnywhere too.
