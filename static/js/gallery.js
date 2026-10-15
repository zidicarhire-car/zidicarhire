/*
 * Car page: photo carousel with thumbnails and a full-screen view (Bootstrap carousel + modal, swipe and arrow keys
 * built in), the availability preview calendar, and the booking card's dates and total (priced by the server).
 */
(function () {
  const { api, kes } = window.ZCH;
  const bs = window.bootstrap;

  /* ---------- photos ---------- */
  const gallery = document.getElementById('car-gallery');
  const lightbox = document.getElementById('lightbox');
  const boxCarousel = document.getElementById('lightbox-carousel');
  const thumbs = [...document.querySelectorAll('[data-gallery-thumb]')];

  function markThumb(i) {
    thumbs.forEach((t, n) => { if (n === i) t.setAttribute('aria-current', 'true'); else t.removeAttribute('aria-current'); });
    thumbs[i]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  /* Shows slide i straight away (no slide animation), e.g. before the full-screen view opens. */
  function jump(carousel, i) {
    carousel.querySelectorAll('.carousel-item').forEach((item, n) => item.classList.toggle('active', n === i));
    carousel.querySelectorAll('.carousel-indicators [data-bs-slide-to]').forEach((b, n) => {
      b.classList.toggle('active', n === i);
      if (n === i) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
  }

  if (gallery && bs) {
    gallery.addEventListener('slide.bs.carousel', (e) => markThumb(e.to));
    gallery.addEventListener('click', (e) => {
      const open = e.target.closest('[data-gallery-open]');
      if (!open || !lightbox) return;
      const i = Number(open.dataset.index);
      jump(boxCarousel, i);
      lightbox.querySelector('[data-lightbox-count]').textContent = i + 1;
      bs.Modal.getOrCreateInstance(lightbox).show();
    });
  }
  if (lightbox && bs) {
    boxCarousel.addEventListener('slide.bs.carousel', (e) => {
      lightbox.querySelector('[data-lightbox-count]').textContent = e.to + 1;
    });
    lightbox.addEventListener('keydown', (e) => {   // arrow keys anywhere in the full-screen view
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const c = bs.Carousel.getOrCreateInstance(boxCarousel);
      if (e.key === 'ArrowLeft') c.prev(); else c.next();
    });
    lightbox.addEventListener('hidden.bs.modal', () => {   // come back to the photo you were looking at
      const items = [...boxCarousel.querySelectorAll('.carousel-item')];
      const i = items.findIndex((item) => item.classList.contains('active'));
      if (gallery && i >= 0) { jump(gallery, i); markThumb(i); }
    });
  }

  /* ---------- booking card: dates and total ---------- */
  const card = document.querySelector('[data-quick-quote]');
  const bookButtons = document.querySelectorAll('.book-btn[data-from]');
  const totals = document.querySelectorAll('[data-quote-total]');
  const DAY_MS = 86400000;
  const parse = (v) => { const [y, m, d] = v.split('-').map(Number); return Date.UTC(y, m - 1, d); };
  const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
  let seq = 0;

  function showTotal(text) { totals.forEach((el) => { el.textContent = text; }); }

  async function requote() {
    const from = card.elements.from.value;
    const to = card.elements.to.value;
    if (!from || !to || to <= from) { showTotal('Choose a return date after the pick-up date'); return; }
    bookButtons.forEach((b) => { b.dataset.from = from; b.dataset.to = to; });
    const id = ++seq;
    const t = card.dataset.time;
    const params = new URLSearchParams({ car_id: card.dataset.carId, from, to, pickup_time: t, return_time: t,
      pickup_point: card.dataset.pickupPoint });   // the branch's first pick-up point, as in the booking popup
    try {
      const res = await api(`${card.dataset.quoteUrl}?${params}`);
      if (id !== seq) return;
      const q = res.quote;
      showTotal(`${kes(q.total)} for ${q.days} day${q.days === 1 ? '' : 's'}`);
    } catch (err) {
      if (id === seq) showTotal(err.message);
    }
  }

  if (card) {
    card.elements.from.addEventListener('change', () => {
      const from = card.elements.from.value;
      if (from) {
        const next = iso(parse(from) + DAY_MS);
        card.elements.to.min = next;
        if (!card.elements.to.value || card.elements.to.value < next) card.elements.to.value = next;
      }
      requote();
    });
    card.elements.to.addEventListener('change', requote);
    requote();
  }

  /* ---------- availability preview ---------- */
  const preview = document.getElementById('availability-preview');
  const bookBtn = document.querySelector('[data-book-main]');
  if (preview && window.RangeCalendar) {
    const cal = new window.RangeCalendar(preview, {
      min: preview.dataset.today,
      onPick: (day) => window.ZCHBooking?.open(bookBtn, { start: day }),
      onMessage: () => {},
    });
    api(`/api/cars/${preview.dataset.carId}/booked-dates/?months=12`)
      .then((res) => cal.setUnavailable(res.unavailable))
      .catch(() => { preview.insertAdjacentHTML('beforeend', '<p class="fine">Booked days could not be loaded. You can still pick dates when you book.</p>'); });
  }
})();
