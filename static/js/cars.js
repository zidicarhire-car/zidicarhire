/* Car list filters: results update as you change a filter, without reloading the page. */
(function () {
  const form = document.getElementById('car-filters');
  const results = document.getElementById('car-results');
  if (!form || !results || !window.fetch) return;

  form.classList.add('is-live');   // the "Show cars" button is only needed without JavaScript
  let timer = null;
  let seq = 0;

  const SKELETON_CARD = `<li class="car skeleton" aria-hidden="true"><div class="sk-photo"></div>
    <div class="car-body"><div class="sk-line"></div><div class="sk-line sk-short"></div><div class="sk-line"></div></div></li>`;

  function showSkeleton() {
    results.innerHTML = `<p class="results-count">Finding cars…</p><ul class="car-grid">${SKELETON_CARD.repeat(6)}</ul>`;
  }

  function query() {
    const params = new URLSearchParams();
    new FormData(form).forEach((value, key) => { if (String(value).trim()) params.append(key, value); });
    return params.toString();
  }

  async function update() {
    const qs = query();
    const url = `${form.action}?${qs}`;
    const id = ++seq;
    results.setAttribute('aria-busy', 'true');
    const slow = setTimeout(showSkeleton, 150);   // only flash the skeleton if the answer is slow
    try {
      const res = await fetch(`${url}&partial=1`, { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      if (id !== seq) return;
      results.innerHTML = html;
      history.replaceState(null, '', url);
    } catch (e) {
      if (id === seq) form.submit();             // fall back to a normal page load
    } finally {
      clearTimeout(slow);
      if (id === seq) results.setAttribute('aria-busy', 'false');
    }
  }

  function later(ms) { clearTimeout(timer); timer = setTimeout(update, ms); }

  form.addEventListener('change', () => later(150));
  form.addEventListener('input', (e) => { if (e.target.type === 'number') later(600); });
  form.addEventListener('submit', (e) => { e.preventDefault(); update(); });

  results.addEventListener('click', (e) => {
    if (!e.target.closest('[data-clear-filters]')) return;
    e.preventDefault();
    form.elements.category.value = '';
    form.querySelector('input[name="transmission"][value=""]').checked = true;
    form.elements.seats.value = '';
    form.elements.price_min.value = '';
    form.elements.price_max.value = '';
    form.elements.sort.value = 'recommended';
    update();
  });
})();
