/* Search bar: remembers the visitor's city and only offers one-way returns the branch has set up. */
(function () {
  const { esc, kes, store } = window.ZCH;
  const form = document.getElementById('search');
  if (!form) return;

  const KEY = 'zch_city';
  const citySelect = form.elements.city;
  const returnSelect = form.elements.return_to;
  let routes = {};
  try { routes = JSON.parse(document.getElementById('routes-data').textContent); } catch (e) { /* no routes */ }

  function fillReturns() {
    const keep = returnSelect.value;
    const list = routes[citySelect.value] || [];
    returnSelect.innerHTML = '<option value="">Same city</option>' + list.map((r) => (
      `<option value="${esc(r.slug)}">${esc(r.name)} (one-way, +${kes(r.fee)})</option>`
    )).join('');
    returnSelect.value = list.some((r) => r.slug === keep) ? keep : '';
  }

  citySelect.addEventListener('change', () => { store.set(KEY, citySelect.value); fillReturns(); });
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
