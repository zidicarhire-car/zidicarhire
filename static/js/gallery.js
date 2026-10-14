/*
 * Car page: swipeable photo gallery (scroll-snap, so swiping is native), a full-screen view with
 * keyboard and touch support, and the availability preview calendar.
 */
(function () {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- gallery ---------- */
  const gallery = document.querySelector('[data-gallery]');
  const track = gallery?.querySelector('.gallery-track');
  const slides = track ? [...track.querySelectorAll('.gallery-slide')] : [];
  const lightbox = document.getElementById('lightbox');
  let current = 0;

  function show(i, smooth = true) {
    if (!slides.length) return;
    current = (i + slides.length) % slides.length;
    track.scrollTo({ left: slides[current].offsetLeft - track.offsetLeft, behavior: smooth && !reduceMotion ? 'smooth' : 'auto' });
    mark();
  }

  function mark() {
    const counter = gallery.querySelector('[data-current]');
    if (counter) counter.textContent = current + 1;
    gallery.querySelectorAll('.gallery-thumbs button').forEach((b, i) => {
      if (i === current) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
  }

  if (track && slides.length) {
    let ticking = false;
    track.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        current = Math.round(track.scrollLeft / track.clientWidth);
        mark();
        ticking = false;
      });
    }, { passive: true });
    gallery.querySelector('.gallery-prev')?.addEventListener('click', () => show(current - 1));
    gallery.querySelector('.gallery-next')?.addEventListener('click', () => show(current + 1));
    gallery.querySelectorAll('.gallery-thumbs button').forEach((b) => b.addEventListener('click', () => show(Number(b.dataset.index))));
    track.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); show(current - 1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); show(current + 1); }
    });
    track.addEventListener('click', (e) => {
      const btn = e.target.closest('.gallery-open');
      if (btn) openLightbox(Number(btn.dataset.index));
    });
  }

  /* ---------- full-screen view ---------- */
  const fullImg = document.getElementById('lightbox-img');
  let boxIndex = 0;

  function paint() {
    const btn = slides[boxIndex].querySelector('.gallery-open');
    fullImg.src = btn.dataset.full;
    fullImg.alt = btn.querySelector('img').alt;
    lightbox.querySelector('.lightbox-count').textContent = `${boxIndex + 1} / ${slides.length}`;
  }

  function openLightbox(i) {
    if (!lightbox) return;
    boxIndex = i;
    paint();
    lightbox.showModal();
    lightbox.querySelector('.lightbox-close').focus();
  }

  function step(n) {
    boxIndex = (boxIndex + n + slides.length) % slides.length;
    paint();
  }

  if (lightbox) {
    lightbox.querySelector('.lightbox-prev')?.addEventListener('click', () => step(-1));
    lightbox.querySelector('.lightbox-next')?.addEventListener('click', () => step(1));
    lightbox.querySelector('[data-close-lightbox]').addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') step(-1);
      if (e.key === 'ArrowRight') step(1);
    });
    lightbox.addEventListener('close', () => show(boxIndex, false));
    let startX = null;
    lightbox.addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
    lightbox.addEventListener('touchend', (e) => {
      if (startX === null) return;
      const dx = e.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(dx) > 45) step(dx < 0 ? 1 : -1);
    }, { passive: true });
    lightbox.addEventListener('click', (e) => { if (e.target === lightbox) lightbox.close(); });
  }

  /* ---------- availability preview ---------- */
  const preview = document.getElementById('availability-preview');
  const bookBtn = document.querySelector('.car-info .book-btn');
  if (preview && window.RangeCalendar && window.ZCH) {
    const cal = new window.RangeCalendar(preview, {
      min: preview.dataset.today,
      onPick: (day) => window.ZCHBooking?.open(bookBtn, { start: day }),
      onMessage: () => {},
    });
    window.ZCH.api(`/api/cars/${preview.dataset.carId}/booked-dates/?months=12`)
      .then((res) => cal.setUnavailable(res.unavailable))
      .catch(() => { preview.insertAdjacentHTML('beforeend', '<p class="muted small">Booked days could not be loaded. You can still pick dates when you book.</p>'); });
  }
})();
