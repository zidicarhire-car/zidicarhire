/*
 * Booking popup: 1 Dates, 2 Your details, 3 Pay (M-Pesa prompt), 4 Confirmed.
 * Prices always come from the server (/bookings/quote/), and the server prices the booking
 * again when it's created, so nothing here decides what the customer pays.
 */
(function () {
  const { api, esc, kes, poll, store } = window.ZCH;
  const dialog = document.getElementById('booking-dialog');
  if (!dialog || !window.RangeCalendar) return;

  const RC = window.RangeCalendar;
  const ds = dialog.dataset;
  const datesForm = document.getElementById('dates-form');
  const detailsForm = document.getElementById('details-form');
  const continueBtn = dialog.querySelector('[data-next="details"]');
  const payBtn = dialog.querySelector('[data-action="pay"]');
  const body = dialog.querySelector('.bd-body');
  const PROGRESS = ['dates', 'details', 'pay', 'done'];
  const DATE_FIELDS = new Set(['pickup_date', 'return_date', 'pickup_time', 'return_time', 'pickup_point',
    'return_location', 'extras']);
  const DETAIL_FIELDS = ['name', 'phone', 'email', 'id_number', 'licence_number'];
  const CUSTOMER_KEY = 'zch_customer';
  const RESEND_AFTER_MS = 45000;
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  let car = null;
  let range = { start: null, end: null };
  let quote = null;
  let quoteSeq = 0;
  let quoteTimer = null;
  let booking = null;
  let watcher = null;
  let resendTimer = null;
  let countdownTimer = null;

  const fill = (key, value) => dialog.querySelectorAll(`[data-fill="${key}"]`).forEach((el) => { el.textContent = value; });
  const setError = (step, message) => { const el = dialog.querySelector(`[data-error="${step}"]`); if (el) el.textContent = message || ''; };
  const fmtDay = (isoDay) => { const d = RC.parse(isoDay); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  /* ---------- steps ---------- */
  function showStep(name) {
    dialog.querySelectorAll('.bd-step').forEach((s) => { s.hidden = s.dataset.step !== name; });
    const step = dialog.querySelector(`.bd-step[data-step="${name}"]`);
    const at = PROGRESS.indexOf(step.dataset.progressStep);
    dialog.querySelectorAll('[data-progress]').forEach((li) => {
      const i = PROGRESS.indexOf(li.dataset.progress);
      li.classList.toggle('is-done', i < at);
      if (i === at) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });
    body.scrollTop = 0;
    const heading = step.querySelector('h3');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  }

  /* ---------- step 1: dates ---------- */
  const calendar = new RC(document.getElementById('rangecal'), {
    min: ds.today,
    maxDays: Number(ds.maxDays),
    onChange(start, end) { range = { start, end }; describeRange(); scheduleQuote(); },
    onMessage(message) { setError('dates', message); },
  });

  function describeRange() {
    const f = datesForm.elements;
    if (!range.start) fill('range', 'Tap your pick-up date, then your return date.');
    else if (!range.end) fill('range', `Pick-up ${fmtDay(range.start)}. Now tap your return date.`);
    else fill('range', `Pick-up ${fmtDay(range.start)} ${f.pickup_time.value} → Return ${fmtDay(range.end)} ${f.return_time.value}`);
  }

  function renderBreakdown(lines) {
    const html = lines.map((l) => (l.total
      ? `<div class="bd-total"><dt>Total to pay</dt><dd><strong>${kes(l.amount)}</strong></dd></div>`
      : `<div><dt>${esc(l.label)}</dt><dd>${kes(l.amount)}</dd></div>`)).join('');
    dialog.querySelectorAll('[data-breakdown]').forEach((el) => { el.innerHTML = html; });
  }

  function chosenExtras() {
    return [...datesForm.querySelectorAll('input[name="extras"]:checked')].map((cb) => cb.value);
  }

  function scheduleQuote() { clearTimeout(quoteTimer); quoteTimer = setTimeout(refreshQuote, 120); }

  async function refreshQuote() {
    quote = null;
    continueBtn.disabled = true;
    if (!car || !range.start || !range.end) { renderBreakdown([]); return; }
    const f = datesForm.elements;
    const params = new URLSearchParams({
      car_id: car.id, from: range.start, to: range.end,
      pickup_time: f.pickup_time.value, return_time: f.return_time.value,
      pickup_point: f.pickup_point ? f.pickup_point.value : '', return_location: f.return_location.value,
    });
    chosenExtras().forEach((id) => params.append('extras', id));
    const seq = ++quoteSeq;
    const boxes = dialog.querySelectorAll('[data-breakdown]');
    boxes.forEach((el) => el.setAttribute('aria-busy', 'true'));
    try {
      const res = await api(`${ds.quoteUrl}?${params}`);
      if (seq !== quoteSeq) return;
      quote = res.quote;
      setError('dates', '');
      renderBreakdown(quote.breakdown);
      fill('range', `Pick-up ${quote.pickup} → Return ${quote.return}, ${plural(quote.days, 'day')}`);
      continueBtn.disabled = false;
    } catch (err) {
      if (seq !== quoteSeq) return;
      renderBreakdown(err.data?.quote?.breakdown || []);
      setError('dates', err.message);
    } finally {
      if (seq === quoteSeq) boxes.forEach((el) => el.removeAttribute('aria-busy'));
    }
  }

  datesForm.addEventListener('change', () => { describeRange(); scheduleQuote(); });

  function firstFreeDay(from) {
    let day = from;
    for (let i = 0; i < 366 && calendar.isBlocked(day); i += 1) day = RC.addDays(day, 1);
    return day;
  }

  dialog.querySelectorAll('[data-quick]').forEach((chip) => chip.addEventListener('click', () => {
    const start = range.start || firstFreeDay(RC.addDays(ds.today, 1));
    const f = datesForm.elements;
    f.return_time.value = f.pickup_time.value;   // exactly N x 24 hours
    setError('dates', calendar.setRange(start, RC.addDays(start, Number(chip.dataset.quick))));
  }));

  continueBtn.addEventListener('click', () => {
    if (!quote) return;
    prefillCustomer();
    showStep('details');
  });

  /* ---------- step 2: details ---------- */
  const RULES = {
    name: (v) => (v.trim().length >= 2 ? '' : 'Enter your full name as it appears on your ID.'),
    phone: (v) => (/^(?:\+?254|0)?[17]\d{8}$/.test(v.replace(/[\s-]/g, ''))
      ? '' : 'Enter the Safaricom number that will pay, like 0712 345 678 or 0110 123 456.'),
    email: (v) => (!v.trim() || /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())
      ? '' : 'That email address looks incomplete. Check it, or leave it blank.'),
    id_number: (v) => (/^[A-Z0-9]{6,12}$/.test(v.replace(/[\s-]/g, '').toUpperCase())
      ? '' : 'Enter your national ID number (7 or 8 digits) or your passport number.'),
    licence_number: (v) => (/^[A-Z0-9][A-Z0-9/-]{3,19}$/.test(v.replace(/\s/g, '').toUpperCase())
      ? '' : 'Enter the number on your driving licence (letters, numbers and dashes).'),
  };

  function showFieldError(name, message) {
    const input = detailsForm.elements[name];
    const out = document.getElementById(`err-${name}`);
    if (out) out.textContent = message || '';
    if (input) { if (message) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid'); }
  }

  function validateField(name) {
    const message = RULES[name](detailsForm.elements[name].value);
    showFieldError(name, message);
    return message;
  }

  function validateDetails() {
    let first = null;
    DETAIL_FIELDS.forEach((name) => { if (validateField(name) && !first) first = name; });
    if (first) detailsForm.elements[first].focus();
    return !first;
  }

  DETAIL_FIELDS.forEach((name) => {
    const input = detailsForm.elements[name];
    input.addEventListener('blur', () => { if (input.value.trim() || input.getAttribute('aria-invalid')) validateField(name); });
    input.addEventListener('input', () => { if (input.getAttribute('aria-invalid')) validateField(name); });
  });

  /* Shows the number the way people write it: 0712 345 678 or +254 712 345 678. */
  function formatPhone(raw) {
    const plus = raw.trim().startsWith('+');
    const digits = raw.replace(/\D/g, '');
    if (plus || digits.startsWith('254')) {
      const d = digits.slice(0, 12);
      return (plus ? '+' : '') + [d.slice(0, 3), d.slice(3, 6), d.slice(6, 9), d.slice(9, 12)].filter(Boolean).join(' ');
    }
    const d = digits.slice(0, 10);
    return [d.slice(0, 4), d.slice(4, 7), d.slice(7, 10)].filter(Boolean).join(' ');
  }
  const phoneInput = detailsForm.elements.phone;
  phoneInput.addEventListener('input', (e) => {
    if (e.inputType && e.inputType.startsWith('delete')) return;
    if (phoneInput.selectionStart !== phoneInput.value.length) return;   // don't jump the cursor mid-edit
    phoneInput.value = formatPhone(phoneInput.value);
  });

  function prefillCustomer() {
    let saved = {};
    try { saved = JSON.parse(store.get(CUSTOMER_KEY) || '{}'); } catch (e) { saved = {}; }
    ['name', 'phone', 'email'].forEach((k) => {
      const input = detailsForm.elements[k];
      if (!input.value && saved[k]) input.value = k === 'phone' ? formatPhone(saved[k]) : saved[k];
    });
  }

  function rememberCustomer() {
    const f = detailsForm.elements;
    store.set(CUSTOMER_KEY, JSON.stringify({ name: f.name.value.trim(), phone: f.phone.value.trim(), email: f.email.value.trim() }));
  }

  dialog.querySelector('[data-next="pay"]').addEventListener('click', () => {
    setError('details', '');
    if (!validateDetails()) { setError('details', 'Check the highlighted details.'); return; }
    rememberCustomer();
    const f = datesForm.elements;
    const returnText = f.return_location.selectedOptions[0]?.textContent.replace(/\s*\(.*\)$/, '') || '';
    const pointText = f.pickup_point ? f.pickup_point.selectedOptions[0].textContent.replace(/\s*\(.*\)$/, '') : '';
    fill('pickup', `${quote.pickup}${pointText ? `, ${pointText}` : ''}`);
    fill('return', `${quote.return}, ${returnText}`);
    fill('phone-entered', detailsForm.elements.phone.value.trim());
    renderBreakdown(quote.breakdown);
    payBtn.textContent = `Pay ${kes(quote.total)} with M-Pesa`;
    setError('pay', '');
    showStep('pay');
  });

  dialog.querySelectorAll('[data-back]').forEach((btn) => btn.addEventListener('click', () => {
    stopWatching();
    showStep(btn.dataset.back);
  }));

  /* ---------- step 3: pay ---------- */
  function routeError(field, message) {
    if (DATE_FIELDS.has(field)) { showStep('dates'); setError('dates', message); }
    else if (DETAIL_FIELDS.includes(field)) { showStep('details'); showFieldError(field, message); detailsForm.elements[field].focus(); }
    else setError('pay', message);
  }

  payBtn.addEventListener('click', async () => {
    const f = datesForm.elements;
    const label = payBtn.textContent;
    payBtn.disabled = true;
    payBtn.textContent = 'Sending the M-Pesa prompt…';
    setError('pay', '');
    try {
      const res = await api(ds.createUrl, {
        method: 'POST',
        body: {
          ...Object.fromEntries(new FormData(detailsForm)),
          car_id: car.id, pickup_location: ds.city,
          pickup_date: range.start, return_date: range.end,
          pickup_time: f.pickup_time.value, return_time: f.return_time.value,
          pickup_point: f.pickup_point ? f.pickup_point.value : '', return_location: f.return_location.value,
          extras: chosenExtras(),
        },
      });
      startWaiting(res.booking);
    } catch (err) {
      if (err.data?.booking) { booking = err.data.booking; showFailed(err.message); }
      else if (err.status === 409) { showStep('dates'); setError('dates', err.message); loadBookedDays(); markBooked(car.id); }
      else if (err.data?.field) routeError(err.data.field, err.message);
      else setError('pay', err.message);
    } finally {
      payBtn.disabled = false;
      payBtn.textContent = label;
    }
  });

  function stopWatching() {
    if (watcher) { watcher.stop(); watcher = null; }
    clearTimeout(resendTimer);
    clearInterval(countdownTimer);
  }

  function startCountdown() {
    const ends = Date.now() + Number(ds.promptSeconds) * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((ends - Date.now()) / 1000));
      fill('countdown', `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`);
      if (!left) {
        clearInterval(countdownTimer);
        fill('wait-note', "The prompt has expired. If you didn't pay, send a new one.");
        dialog.querySelector('[data-step="waiting"] [data-action="resend"]').hidden = false;
      }
    };
    clearInterval(countdownTimer);
    tick();
    countdownTimer = setInterval(tick, 1000);
  }

  function startWaiting(b) {
    stopWatching();
    booking = b;
    fill('total', kes(b.amount));
    fill('phone', b.phone);
    fill('wait-note', 'Waiting for your payment…');
    const resendBtn = dialog.querySelector('[data-step="waiting"] [data-action="resend"]');
    resendBtn.hidden = true;
    resendTimer = setTimeout(() => {
      fill('wait-note', "Didn't get the prompt? Check your phone is on and unlocked, then send it again.");
      resendBtn.hidden = false;
    }, RESEND_AFTER_MS);
    startCountdown();
    showStep('waiting');
    watcher = poll(async () => {
      const res = await api(`/bookings/${booking.ref}/status/`);
      handle(res.booking);
    }, 3000, 6000);
  }

  function handle(b) {
    booking = b;
    if (['paid', 'picked_up', 'completed'].includes(b.status)) {
      stopWatching();
      showPaid(b);
    } else if (b.status === 'failed' || b.status === 'cancelled') {
      stopWatching();
      showFailed(b.message);
    }
  }

  function showFailed(message) {
    stopWatching();
    setError('failed', '');
    fill('fail-reason', message || 'The M-Pesa payment was cancelled or timed out.');
    showStep('failed');
  }

  async function resend() {
    if (!booking) return;
    setError('failed', '');
    try {
      const res = await api(`/bookings/${booking.ref}/retry/`, { method: 'POST', body: {} });
      if (['paid', 'picked_up', 'completed'].includes(res.booking.status)) handle(res.booking);
      else startWaiting(res.booking);
    } catch (err) {
      if (!dialog.querySelector('[data-step="failed"]').hidden) setError('failed', err.message);
      else showFailed(err.message);
    }
  }
  dialog.querySelectorAll('[data-action="resend"]').forEach((btn) => btn.addEventListener('click', resend));

  /* ---------- step 4: confirmed ---------- */
  function showPaid(b) {
    fill('car', b.car);
    fill('ref', b.ref);
    fill('receipt', b.receipt || 'on its way');
    fill('total', kes(b.amount));
    fill('pickup-done', `${fmtDay(b.pickup_date)} ${b.pickup_time}${b.pickup_point ? `, ${b.pickup_point}` : ''}`);
    fill('return-done', `${fmtDay(b.return_date)} ${b.return_time}${b.return_city ? `, ${b.return_city}` : ''}`);
    dialog.querySelectorAll('[data-link]').forEach((a) => {
      const url = b[a.dataset.link];
      a.hidden = !url;
      if (url) a.href = url;
    });
    showStep('paid');
    markBooked(car?.id, true);
  }

  /* ---------- open / close ---------- */
  async function loadBookedDays() {
    const id = car.id;
    try {
      const res = await api(`/api/cars/${id}/booked-dates/?months=12`);
      if (car && car.id === id) calendar.setUnavailable(res.unavailable);
    } catch (err) {
      setError('dates', "We couldn't load this car's booked days. Pick your dates and we'll check them before you pay.");
    }
  }

  async function open(btn, opts = {}) {
    stopWatching();
    car = { id: btn.dataset.carId, name: btn.dataset.name, city: btn.dataset.city || '', price: Number(btn.dataset.price) };
    quote = null;
    booking = null;
    ['dates', 'details', 'pay', 'failed'].forEach((s) => setError(s, ''));
    fill('car', car.name);
    fill('city', car.city);
    fill('price', kes(car.price));
    renderBreakdown([]);
    continueBtn.disabled = true;
    calendar.setUnavailable([]);
    calendar.clear();
    showStep('dates');
    dialog.showModal();
    await loadBookedDays();
    if (opts.start) {
      setError('dates', calendar.setRange(opts.start, null));
    } else if (ds.preselect === '1' && !range.start) {
      const message = calendar.setRange(ds.from, ds.to);
      if (message) setError('dates', `Your search dates don't work for this car: ${message}`);
    }
  }

  function close() { stopWatching(); dialog.close(); }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.book-btn');
    if (btn && !btn.disabled) open(btn);
  });
  dialog.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) close();
    if (e.target.closest('[data-open-chat]')) close();   // the chat panel sits under the popup
  });
  dialog.addEventListener('close', stopWatching);

  /* ---------- live availability on the car list ---------- */
  // Looked up each time: the car list is replaced when filters change.
  const carGrid = () => document.getElementById('car-grid');
  function markBooked(id, onlyIfFull) {
    if (!id || onlyIfFull) { refreshAvailability(); return; }
    const li = carGrid()?.querySelector(`[data-car-id="${id}"]`);
    if (li) li.classList.add('is-booked');
  }
  async function refreshAvailability() {
    const grid = carGrid();
    if (!grid) return;
    try {
      const res = await api(`/api/availability/?from=${grid.dataset.from}&to=${grid.dataset.to}&city=${encodeURIComponent(grid.dataset.city)}`);
      grid.querySelectorAll('li.car').forEach((li) => {
        const free = res.available[li.dataset.carId];
        if (free === undefined) return;
        li.classList.toggle('is-booked', !free);
      });
    } catch (e) { /* try again next round */ }
  }
  if (carGrid()) poll(refreshAvailability, 30000, 120000);

  window.ZCHBooking = { open };
})();
