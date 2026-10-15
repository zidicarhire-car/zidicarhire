"""
Dev-only UI check and screenshots for ZIDICARHIRE.

Setup once:   pip install -r requirements-dev.txt  &&  python -m playwright install chromium

  python tools/screenshots.py --check          # one full booking (fake payments) + a chat round trip, phone and desktop
  python tools/screenshots.py                  # the check, then every page at 375, 768 and 1440 px, light and dark
  python tools/screenshots.py --only home,cars --widths 375 --themes light

It runs the site on 127.0.0.1:8765 against a throwaway database (tools/ui_settings.py), so db.sqlite3 and media/
are never touched, and payments are simulated. Screenshots go to tools/screenshots/ (git-ignored).
Exits with 1 if the booking or chat flow breaks, or if any page scrolls sideways (the elements that stick out
are listed).
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'tools' / 'screenshots'
PORT = 8765
BASE = f'http://127.0.0.1:{PORT}'
STAFF = ('ui-staff', 'ui-pass-4821')
WIDTHS = (375, 768, 1440)
THEMES = ('light', 'dark')
VISITOR = {'name': 'Achieng Otieno', 'phone': '0712345678', 'email': 'achieng@example.com',
           'id_number': '12345678', 'licence_number': 'DL123456'}

sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'tools.ui_settings'


# ----------------------------------------------------------------------------------------------- data and server
def build_database():
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files import File
    from django.core.management import call_command

    from fleet.images import save_photo
    from fleet.models import Car, Location

    shutil.rmtree(settings.UI_TMP, ignore_errors=True)
    settings.UI_TMP.mkdir(parents=True)
    call_command('migrate', verbosity=0)
    call_command('seed_locations', verbosity=0)
    call_command('seed_cars', verbosity=0)
    Location.objects.filter(slug='nairobi').update(address='Kenyatta Avenue, CBD')
    Location.objects.filter(slug='mombasa').update(address='Moi Avenue')
    mombasa, kisumu = Location.objects.get(slug='mombasa'), Location.objects.get(slug='kisumu')
    for loc, name, cat, seats, price in ((mombasa, 'Nissan X-Trail', 'suv', 5, 7500), (mombasa, 'Toyota Vitz', 'compact', 5, 3500),
                                         (kisumu, 'Toyota Hiace', 'van', 14, 9000)):
        Car.objects.get_or_create(name=name, location=loc, defaults=dict(category=cat, seats=seats, price_per_day=price,
                                                                         units=1, luggage=3))
    Car.objects.filter(name='Toyota Axio').update(weekly_rate=28000, features=['bluetooth', 'reverse_camera', 'usb'])
    samples = sorted((ROOT / 'media' / 'cars').glob('*.jpg'))
    if samples:
        for i, car in enumerate(Car.objects.order_by('pk')):
            for path in (samples[i % len(samples)], samples[(i + 1) % len(samples)]):
                with path.open('rb') as fh:
                    save_photo(car, File(fh, name=path.name))
    get_user_model().objects.create_superuser(STAFF[0], 'ui@example.com', STAFF[1], first_name='Wanjiru')


def start_server():
    log = (OUT / 'server.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload',
                             '--settings=tools.ui_settings'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            socket.create_connection(('127.0.0.1', PORT), timeout=0.2).close()
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    sys.exit(f'The dev server did not start. See {OUT / "server.log"}')


# ----------------------------------------------------------------------------------------------- page helpers
OVERFLOW_JS = """() => {
  const vw = document.documentElement.clientWidth;
  const found = [];
  const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).slice(0, 3).join('.') : '');
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || r.right <= vw + 1 || !el.checkVisibility({ visibilityProperty: true })) continue;
    let p = el.parentElement, clipped = false;
    while (p && p !== document.body) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) { clipped = true; break; }
      p = p.parentElement;
    }
    if (!clipped) found.push(`${name(el)} (right edge ${Math.round(r.right)}px, page ${vw}px)`);
  }
  if (document.documentElement.scrollWidth > vw + 1) found.unshift(`page scrollWidth ${document.documentElement.scrollWidth}px`);
  return found.slice(0, 12);
}"""


A11Y_JS = """() => {
  const bad = [];
  const label = (el) => {
    const by = el.getAttribute('aria-labelledby');
    const named = by && by.split(' ').map((id) => document.getElementById(id)?.textContent || '').join(' ');
    return (el.getAttribute('aria-label') || named || el.textContent || el.title || '').trim();
  };
  for (const el of document.querySelectorAll('button, a[href], [role="button"]')) {
    if (!el.checkVisibility({ visibilityProperty: true }) || el.closest('[aria-hidden="true"]')) continue;
    if (!label(el) && !el.querySelector('img[alt]:not([alt=""])')) bad.push(`${el.tagName.toLowerCase()} with no name: ${el.outerHTML.slice(0, 90)}`);
  }
  for (const el of document.querySelectorAll('input:not([type=hidden]), select, textarea')) {
    if (!el.checkVisibility({ visibilityProperty: true })) continue;
    if (!(el.labels && el.labels.length) && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')) bad.push(`field with no label: ${el.name || el.id}`);
  }
  for (const img of document.querySelectorAll('img:not([alt])')) bad.push(`img with no alt: ${img.src.slice(-50)}`);
  return [...new Set(bad)].slice(0, 8);
}"""


class Run:
    def __init__(self, pw, shots):
        self.browser = pw.chromium.launch()
        self.shots = shots
        self.problems = []
        self.taken = 0

    def context(self, width, theme='light', staff=False):
        height = 812 if width < 768 else (1024 if width < 1200 else 900)
        ctx = self.browser.new_context(viewport={'width': width, 'height': height}, color_scheme=theme,
                                       reduced_motion='reduce', device_scale_factor=1,
                                       has_touch=width < 768, is_mobile=width < 768)
        ctx.add_init_script(f"try {{ localStorage.setItem('zch-theme', '{theme}') }} catch (e) {{}}")
        ctx.set_default_timeout(15000)
        if staff:
            page = ctx.new_page()
            page.goto(f'{BASE}/dashboard/login/')
            page.fill('input[name="username"]', STAFF[0])
            page.fill('input[name="password"]', STAFF[1])
            page.click('button[type="submit"]')
            page.wait_for_url(f'{BASE}/dashboard/**')
            page.close()
        return ctx

    def snap(self, page, name, full=True):
        """Checks the page for sideways scrolling, then saves a screenshot (when screenshots are on)."""
        page.wait_for_timeout(250)
        bad = page.evaluate(OVERFLOW_JS)
        if bad:
            self.problems.append(f'{name}: scrolls sideways\n    ' + '\n    '.join(bad))
        missing = page.evaluate(A11Y_JS)
        if missing:
            self.problems.append(f'{name}: accessibility\n    ' + '\n    '.join(missing))
        if self.shots:
            page.screenshot(path=str(OUT / f'{name}.png'), full_page=full)
            self.taken += 1

    def fail(self, message):
        self.problems.append(message)
        print('  FAIL', message)


def goto(page, path):
    page.goto(BASE + path, wait_until='networkidle')


# ----------------------------------------------------------------------------------------------- flows
def booking_flow(run, page, tag, *, shots=False, fail_payment=False):
    """Cars list -> book -> dates -> details -> pay -> confirmed -> receipt PDF. Returns the booking number."""
    goto(page, '/cars/?city=nairobi')
    page.locator('#car-grid .book-btn:not([disabled])').first.click()
    modal = page.locator('#booking-dialog')
    modal.locator('.bd-step[data-step="dates"]').wait_for(state='visible')
    modal.locator('[data-quick="3"]').click()
    page.wait_for_function("() => !document.querySelector('#booking-dialog [data-next=\"details\"]').disabled")
    if shots:
        run.snap(page, f'booking-1-dates-{tag}', full=False)
    modal.locator('[data-next="details"]').click()
    modal.locator('.bd-step[data-step="details"]').wait_for(state='visible')
    if shots:
        modal.locator('[data-next="pay"]').click()          # empty form: shows the inline errors
        run.snap(page, f'booking-2-details-errors-{tag}', full=False)
    for field, value in VISITOR.items():
        modal.locator(f'#details-form [name="{field}"]').fill(value)
    if shots:
        run.snap(page, f'booking-2-details-{tag}', full=False)
    modal.locator('[data-next="pay"]').click()
    modal.locator('.bd-step[data-step="pay"]').wait_for(state='visible')
    if page.viewport_size['width'] >= 576:            # phones get a full-screen popup: nothing outside to tap
        page.mouse.click(5, page.viewport_size['height'] - 5)
        page.wait_for_timeout(400)
        if not modal.locator('.bd-step[data-step="pay"]').is_visible():
            run.fail(f'booking {tag}: a click outside closed the popup on the pay step')
    if shots:
        run.snap(page, f'booking-3-pay-{tag}', full=False)

    held = []
    if shots or fail_payment:
        page.route('**/bookings/*/status/', lambda route: held.append(route))
    modal.locator('[data-action="pay"]').click()
    modal.locator('.bd-step[data-step="waiting"]').wait_for(state='visible')
    if shots:
        run.snap(page, f'booking-4-waiting-{tag}', full=False)
    if fail_payment:   # answer the status check with a cancelled payment, to see the failed screen
        for _ in range(40):
            if held:
                break
            page.wait_for_timeout(250)
        body = json.dumps({'booking': {'ref': 'ZCHFAILED', 'status': 'failed',
                                       'message': 'You cancelled the M-Pesa prompt on your phone.'}})
        for route in held:
            route.fulfill(status=200, content_type='application/json', body=body)
        page.unroute('**/bookings/*/status/')
        modal.locator('.bd-step[data-step="failed"]').wait_for(state='visible')
        run.snap(page, f'booking-5-failed-{tag}', full=False)
        return None, None
    if held or shots:
        for route in held:
            route.continue_()
        page.unroute('**/bookings/*/status/')
    paid = modal.locator('.bd-step[data-step="paid"]')
    paid.wait_for(state='visible', timeout=30000)
    ref = paid.locator('[data-fill="ref"]').inner_text().strip()
    if shots:
        run.snap(page, f'booking-5-confirmed-{tag}', full=False)
    href = paid.locator('[data-link="receipt_url"]').get_attribute('href')
    res = page.request.get(BASE + href)
    if not (res.ok and 'application/pdf' in res.headers.get('content-type', '')):
        run.fail(f'booking {tag}: receipt download returned {res.status} {res.headers.get("content-type")}')
    detail = paid.locator('[data-link="detail_url"]').get_attribute('href')
    return ref, detail


def chat_flow(run, visitor, staff_ctx, tag):
    """Visitor starts a chat and gets the assistant's reply; staff reply from the inbox; the visitor sees it."""
    goto(visitor, '/')
    visitor.locator('#chat-launcher').click()
    visitor.locator('#chat-intro [name="name"]').fill('Brian Kiprop')
    visitor.locator('#chat-intro [type="submit"]').click()
    visitor.locator('#chat-thread').wait_for(state='visible')
    visitor.locator('#chat-input').fill('Hello, is the Vitz free this weekend?')
    visitor.locator('#chat-input').press('Enter')
    visitor.locator('#chat-messages .msg-me', has_text='Vitz free').wait_for()
    visitor.locator('#chat-messages .msg-them').first.wait_for()
    chat_id = visitor.evaluate("() => localStorage.getItem('zch_chat')")
    staff = staff_ctx.new_page()
    goto(staff, f'/dashboard/chats/?c={chat_id}')
    staff.locator('#inbox-active').wait_for(state='visible')
    staff.locator('#thread-messages .msg', has_text='Vitz free').wait_for()
    reply = f'Yes, the Vitz is free this weekend ({tag}).'
    staff.locator('#reply-input').fill(reply)
    staff.locator('#reply-input').press('Enter')
    staff.locator('#thread-messages .msg-me', has_text=reply).wait_for()
    visitor.locator('#chat-messages .msg-them', has_text=reply).wait_for(timeout=20000)
    return chat_id, staff


def dashboard_flow(run, staff, ref, tag):
    """Staff: mark the booking picked up through the confirmation popup; hide and show a car with its switch."""
    goto(staff, f'/dashboard/bookings/{ref}/')
    staff.locator('.action-bar button', has_text='Mark picked up').click()
    staff.locator('#confirm-dialog.show').wait_for()
    with staff.expect_navigation():
        staff.locator('#confirm-yes').click()
    if 'Picked up' not in staff.locator('.detail-title .status').inner_text():
        run.fail(f'dashboard {tag}: marking {ref} picked up did not work')
    goto(staff, '/dashboard/cars/')
    car_switch = staff.locator('.fleet-foot input[role="switch"]').first.get_attribute('id')   # hidden cars move in the list
    switch = lambda: staff.locator(f'#{car_switch}')
    for want in (False, True):
        with staff.expect_navigation():
            switch().click()
        if switch().is_checked() != want:
            run.fail(f'dashboard {tag}: the switch did not {"show" if want else "hide"} the car')


def menu_flow(run, page):
    """Phone menu: Esc closes it and focus goes back to the menu button; the backdrop closes it; a link closes it."""
    goto(page, '/contact/')
    button = page.locator('[aria-controls="site-menu"]')
    menu = page.locator('#site-menu')
    button.click()
    page.locator('#site-menu.show').wait_for()
    page.keyboard.press('Escape')
    menu.wait_for(state='hidden')
    page.wait_for_timeout(200)
    if not page.evaluate("() => document.activeElement?.getAttribute('aria-controls') === 'site-menu'"):
        run.fail('menu: focus did not return to the menu button after Esc')
    button.click()
    page.locator('#site-menu.show').wait_for()
    page.mouse.click(20, 400)                          # the backdrop, left of the panel
    menu.wait_for(state='hidden')
    button.click()
    page.locator('#site-menu.show').wait_for()
    menu.locator('a', has_text='How it works').click()
    page.wait_for_url('**/#how')
    menu.wait_for(state='hidden')


# ----------------------------------------------------------------------------------------------- screens
def open_menu(page):
    page.locator('[aria-controls="site-menu"]').click()
    page.locator('#site-menu.show').wait_for()


def open_filters(page):
    page.locator('[aria-controls="car-filters-panel"]').click()
    page.locator('#car-filters-panel.show').wait_for()


def open_chat(page):
    page.locator('#chat-launcher').click()
    page.locator('#chat-panel').wait_for(state='visible')


def chat_thread(page):
    open_chat(page)
    page.locator('#chat-intro [name="name"]').fill('Grace Wanjiku')
    page.locator('#chat-intro [type="submit"]').click()
    page.locator('#chat-input').fill('What are your prices?')
    page.locator('#chat-input').press('Enter')
    page.locator('#chat-messages .msg-them').first.wait_for()


def open_gallery(page):
    page.locator('[data-gallery-open]').first.click()
    page.locator('#lightbox.show').wait_for()


def public_screens(ctx):
    """name, path, action, which widths (None = all)."""
    return [
        ('home', '/', None, None),
        ('home-menu-open', '/', open_menu, (375, 768)),
        ('home-chat-open', '/', open_chat, None),
        ('chat-thread', '/faq/', chat_thread, (375, 1440)),
        ('cars', '/cars/?city=nairobi', None, None),
        ('cars-filters-open', '/cars/?city=nairobi&transmission=automatic', open_filters, (375, 768)),
        ('cars-empty', '/cars/?city=nairobi&price_max=100', None, (375, 1440)),
        ('car-detail', ctx['car_url'], None, None),
        ('car-detail-photos', ctx['car_url'], open_gallery, (375, 1440)),
        ('city', '/car-hire/mombasa/', None, None),
        ('find-booking', '/bookings/find/', None, None),
        ('booking-status', ctx['detail_url'], None, None),
        ('receipt', ctx['receipt_url'], None, None),
        ('contact', '/contact/', None, None),
        ('about', '/about/', None, (375, 1440)),
        ('faq', '/faq/', None, (375, 1440)),
        ('terms', '/terms/', None, (375,)),
        ('404', '/__ui/404/', None, None),
        ('500', '/__ui/500/', None, (375, 1440)),
    ]


def staff_screens(ctx):
    return [
        ('dash-overview', '/dashboard/', None, None),
        ('dash-menu-open', '/dashboard/', lambda p: (p.locator('[aria-controls="dash-menu"]').first.click(),
                                                    p.locator('#dash-menu.show').wait_for()), (375, 768)),
        ('dash-bookings', '/dashboard/bookings/', None, None),
        ('dash-booking-detail', f'/dashboard/bookings/{ctx["ref"]}/', None, None),
        ('dash-cars', '/dashboard/cars/', None, None),
        ('dash-car-form', f'/dashboard/cars/{ctx["car_id"]}/edit/', None, None),
        ('dash-calendar', '/dashboard/calendar/', None, (375, 1440)),
        ('dash-chats', '/dashboard/chats/', None, None),
        ('dash-chat-thread', f'/dashboard/chats/?c={ctx["chat_id"]}', None, None),
        ('dash-login', None, None, (375, 1440)),
    ]


def capture(run, screens, width, theme, staff, wanted):
    ctx = run.context(width, theme, staff=staff)
    page = ctx.new_page()
    for name, path, action, widths in screens:
        if (widths and width not in widths) or (wanted and name not in wanted):
            continue
        try:
            if name == 'dash-login':
                ctx2 = run.context(width, theme)
                p2 = ctx2.new_page()
                goto(p2, '/dashboard/login/')
                run.snap(p2, f'{name}-{width}-{theme}')
                ctx2.close()
                continue
            goto(page, path)
            if action:
                action(page)
            run.snap(page, f'{name}-{width}-{theme}', full=action is None)
            if name == 'receipt' and width == 1440 and theme == 'light':   # the print stylesheet: one A4 page
                pdf = page.pdf(format='A4', print_background=True)
                (OUT / 'receipt-print.pdf').write_bytes(pdf)
                pages = pdf.count(b'/Type /Page') - pdf.count(b'/Type /Pages')
                if pages != 1:
                    run.fail(f'receipt prints on {pages} A4 pages, not 1')
        except Exception as exc:  # keep going: report every broken screen at the end
            run.fail(f'{name}-{width}-{theme}: {type(exc).__name__}: {str(exc).splitlines()[0]}')
    ctx.close()


# ----------------------------------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='only run the booking and chat flows')
    parser.add_argument('--only', default='', help='comma-separated screen names, e.g. home,cars,dash-bookings')
    parser.add_argument('--widths', default=','.join(map(str, WIDTHS)))
    parser.add_argument('--themes', default=','.join(THEMES))
    args = parser.parse_args()
    widths = [int(w) for w in args.widths.split(',')]
    themes = args.themes.split(',')
    wanted = set(filter(None, args.only.split(',')))

    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    print('Building a throwaway database...')
    build_database()
    from fleet.models import Car
    car = Car.objects.select_related('location').filter(location__slug='nairobi', name='Toyota Axio').first()
    ctx = {'car_url': car.get_absolute_url(), 'car_id': car.pk}   # no database calls inside Playwright's event loop
    server = start_server()
    try:
        with sync_playwright() as pw:
            run = Run(pw, shots=not args.check)

            print('Booking flow and chat, phone (375 px) and desktop (1440 px)...')
            for width in ((375, 1440) if args.check else (375, 768, 1440)):
                tag = {375: 'phone', 768: 'tablet'}.get(width, 'desktop')
                c = run.context(width)
                page = c.new_page()
                ref, detail = booking_flow(run, page, tag, shots=not args.check)
                print(f'  booked and paid {ref} on {tag}, receipt PDF downloads')
                if not args.check:
                    booking_flow(run, page, tag, shots=True, fail_payment=True)
                    goto(page, detail)
                    ctx.update(ref=ref, detail_url=detail,
                               receipt_url=page.locator('a', has_text='Printable receipt').get_attribute('href'))
                staff_ctx = run.context(width, staff=True)
                chat_id, staff_page = chat_flow(run, c.new_page(), staff_ctx, tag)
                print(f'  chat sent, answered and replied to on {tag}')
                dashboard_flow(run, staff_page, ref, tag)
                print(f'  staff marked {ref} picked up (confirmation popup) and hid/showed a car on {tag}')
                ctx['chat_id'] = chat_id
                if width < 992:
                    menu_flow(run, c.new_page())
                    print('  phone menu closes with Esc, backdrop and links; focus returns to the menu button')
                c.close()
                staff_ctx.close()

            if not args.check:
                for width in widths:
                    for theme in themes:
                        print(f'Screenshots at {width} px, {theme}...')
                        capture(run, public_screens(ctx), width, theme, False, wanted)
                        capture(run, staff_screens(ctx), width, theme, True, wanted)
            run.browser.close()
    finally:
        server.terminate()

    if run.shots:
        print(f'{run.taken} screenshots in {OUT}')
    if run.problems:
        print('\nProblems:')
        for p in run.problems:
            print(' -', p)
        sys.exit(1)
    print('All good: no sideways scrolling, booking and chat flows work.')


if __name__ == '__main__':
    main()
