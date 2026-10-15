/*
 * Car list filters: results update as you change a filter, without reloading the page. The sort select and the
 * active-filter chips come back with the results; changing city reloads the page (the booking popup belongs to it).
 */
(function () {
  const form = document.getElementById('car-filters');
  const results = document.getElementById('car-results');
  if (!form || !results || !window.fetch) return;

  form.classList.add('is-live');   // the "Show cars" button is only needed without JavaScript
  const countBadge = document.querySelector('[data-filter-count]');
  const showBtn = document.querySelector('[data-show-cars]');
  let timer = null;
  let seq = 0;

  const SKELETON_CARD = `<li class="col"><div class="card car-card h-100 placeholder-glow" aria-hidden="true">
    <div class="ratio ratio-16x10"><span class="placeholder w-100 h-100"></span></div>
    <div class="card-body"><span class="placeholder col-7 mb-3"></span><span class="placeholder col-10 mb-3"></span>
    <span class="placeholder col-4"></span></div>
    <div class="card-footer"><span class="placeholder col-12 btn disabled"></span></div></div></li>`;

  function showSkeleton() {
    const head = results.querySelector('.results-head')?.outerHTML || '';
    results.innerHTML = `${head}<p class="visually-hidden" role="status">Finding cars…</p>
      <ul class="row row-cols-1 row-cols-sm-2 row-cols-xl-3 g-3 g-md-4 car-grid">${SKELETON_CARD.repeat(6)}</ul>`;
  }

  function query() {
    const params = new URLSearchParams();
    new FormData(form).forEach((value, key) => { if (String(value).trim()) params.append(key, value); });
    return params.toString();
  }

  /* The number on the Filters button (phones) and the "Show N cars" button in the sheet. */
  function syncCounts() {
    const f = form.elements;
    const active = [f.category.value, f.transmission.value, f.seats.value, f.price_min.value || f.price_max.value]
      .filter(Boolean).length;
    if (countBadge) { countBadge.textContent = active; countBadge.hidden = !active; }
    const n = Number(results.querySelector('#results-count')?.dataset.count ?? NaN);
    if (showBtn && !Number.isNaN(n)) showBtn.textContent = n ? `Show ${n} car${n === 1 ? '' : 's'}` : 'No cars match';
  }

  async function update() {
    const url = `${form.action}?${query()}`;
    const id = ++seq;
    const focusedId = results.contains(document.activeElement) ? document.activeElement.id : '';
    results.setAttribute('aria-busy', 'true');
    const slow = setTimeout(showSkeleton, 150);   // only flash the skeleton if the answer is slow
    try {
      const res = await fetch(`${url}&partial=1`, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      if (id !== seq) return;
      results.innerHTML = html;
      history.replaceState(null, '', url);
      if (focusedId) document.getElementById(focusedId)?.focus();   // e.g. keep the keyboard on the sort select
    } catch (e) {
      if (id === seq) form.submit();             // fall back to a normal page load
    } finally {
      clearTimeout(slow);
      if (id === seq) { results.setAttribute('aria-busy', 'false'); syncCounts(); }
    }
  }

  function later(ms) { clearTimeout(timer); timer = setTimeout(update, ms); }

  function clearFilters(names) {
    const f = form.elements;
    names.forEach((name) => {
      if (name === 'transmission') form.querySelector('input[name="transmission"][value=""]').checked = true;
      else if (name === 'price') { f.price_min.value = ''; f.price_max.value = ''; }
      else f[name].value = '';
    });
  }

  form.addEventListener('change', (e) => {
    if (e.target.name === 'city') { form.submit(); return; }
    later(150);
  });
  form.addEventListener('input', (e) => { if (e.target.type === 'number') later(600); });
  form.addEventListener('submit', (e) => { e.preventDefault(); update(); });   // form.submit() above skips this
  results.addEventListener('change', (e) => { if (e.target.name === 'sort') later(0); });

  document.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-clear]');
    const all = e.target.closest('[data-clear-filters]');
    if (!chip && !all) return;
    e.preventDefault();
    clearFilters(chip ? [chip.dataset.clear] : ['category', 'transmission', 'seats', 'price']);
    if (all) { const sort = document.getElementById('sort'); if (sort) sort.value = 'recommended'; }
    update();
  });

  syncCounts();
})();
