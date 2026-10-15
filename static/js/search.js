/* Search card: remembers the visitor's city, keeps the return date after the pick-up date and shows the day count. */
(function () {
  const { store } = window.ZCH;
  const form = document.getElementById('search');
  if (!form) return;

  const KEY = 'zch_city';
  const citySelect = form.elements.city;
  const from = form.elements.from;
  const to = form.elements.to;
  const daysOut = form.querySelector('[data-days]');
  const DAY_MS = 86400000;
  const parse = (v) => { const [y, m, d] = v.split('-').map(Number); return Date.UTC(y, m - 1, d); };
  const iso = (ms) => new Date(ms).toISOString().slice(0, 10);

  function showDays() {
    if (!from.value || !to.value) { daysOut.textContent = 'Choose your pick-up and return dates'; return; }
    const days = Math.round((parse(to.value) - parse(from.value)) / DAY_MS);
    daysOut.textContent = days > 0 ? `${days} day${days === 1 ? '' : 's'}` : 'Choose a return date after the pick-up date';
  }

  from.addEventListener('change', () => {
    if (from.value) {
      const next = iso(parse(from.value) + DAY_MS);
      to.min = next;
      if (!to.value || to.value < next) to.value = next;
    }
    showDays();
  });
  to.addEventListener('change', showDays);
  if (from.value) to.min = iso(parse(from.value) + DAY_MS);

  citySelect.addEventListener('change', () => store.set(KEY, citySelect.value));
  form.addEventListener('submit', () => store.set(KEY, citySelect.value));

  // The home page shows Nairobi unless a city is in the address. Send returning visitors to their last city.
  const remembered = store.get(KEY);
  if (form.dataset.explicitCity === '1') {
    store.set(KEY, form.dataset.city);
  } else if (remembered && remembered !== form.dataset.city
             && [...citySelect.options].some((o) => o.value === remembered)) {
    const url = new URL(location.href);
    url.searchParams.set('city', remembered);
    location.replace(url.toString());
  }
})();
