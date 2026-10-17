/* Shared helpers for ZIDICARHIRE pages. */
(function () {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  async function api(url, { method = 'GET', body } = {}) {
    const opts = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.headers['X-CSRFToken'] = csrf();
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      const err = new Error("You're offline or the connection dropped. Check your internet and try again.");
      err.status = 0;
      throw err;
    }
    let data = {};
    try { data = await res.json(); } catch (e) { /* non-JSON response */ }
    if (!res.ok) {
      const err = new Error(data.error || `Something went wrong (error ${res.status}). Try again.`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  const kes = (n) => 'KES ' + Number(n || 0).toLocaleString('en-KE');

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* storage blocked */ } },
  };

  /* Polls fn every `ms`, slows down while the tab is hidden, never overlaps calls. */
  function poll(fn, ms, hiddenMs = ms * 4) {
    let timer = null;
    let stopped = false;
    async function tick() {
      if (stopped) return;
      try { await fn(); } catch (e) { /* errors are handled inside fn */ }
      if (!stopped) timer = setTimeout(tick, document.hidden ? hiddenMs : ms);
    }
    tick();
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && !stopped) { clearTimeout(timer); tick(); }
    });
    return { stop() { stopped = true; clearTimeout(timer); } };
  }

  /* Loading state for a button: keeps its width, shows a spinner and blocks double clicks. */
  function busy(btn, on = true) {
    if (!btn) return;
    if (on) {
      btn.setAttribute('aria-busy', 'true');
      btn.disabled = true;
    } else {
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
    }
  }

  /* Small message in the bottom corner. kind: '' | 'success' | 'error'. With href it is a link. */
  function toast(title, text = '', { kind = '', href = '', ms = 7000 } = {}) {
    let box = document.getElementById('toasts');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toasts';
      box.className = 'toast-container position-fixed top-0 end-0';
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    const el = document.createElement(href ? 'a' : 'div');
    el.className = 'toast show' + (kind ? ` toast-${kind}` : '');
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    if (href) el.href = href;
    el.innerHTML = `<strong>${esc(title)}</strong>${text ? `<span>${esc(text)}</span>` : ''}`;
    box.appendChild(el);
    setTimeout(() => el.classList.add('out'), ms);
    setTimeout(() => el.remove(), ms + 400);
    return el;
  }

  /* Light / dark mode. _theme_head.html applies it before first paint; any [data-theme-toggle] button
     switches it and the choice is remembered. Until the visitor chooses, it follows the device. */
  const THEME_KEY = 'zch-theme';
  const root = document.documentElement;
  const isDark = () => root.getAttribute('data-bs-theme') === 'dark';

  function applyTheme(mode) {
    root.setAttribute('data-bs-theme', mode);
    document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(mode === 'dark'));
      const icon = btn.querySelector('.bi');
      if (icon) {
        icon.classList.toggle('bi-moon-stars', mode !== 'dark');
        icon.classList.toggle('bi-sun', mode === 'dark');
      }
      btn.title = mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
      const label = btn.querySelector('[data-theme-label]');
      if (label) label.textContent = mode === 'dark' ? 'Light mode' : 'Dark mode';
    });
  }

  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-theme-toggle]')) return;
    const next = isDark() ? 'light' : 'dark';
    store.set(THEME_KEY, next);
    applyTheme(next);
  });
  const deviceDark = window.matchMedia('(prefers-color-scheme: dark)');
  deviceDark.addEventListener('change', (e) => { if (!store.get(THEME_KEY)) applyTheme(e.matches ? 'dark' : 'light'); });
  applyTheme(isDark() ? 'dark' : 'light');

  /* Navbar: a little shorter once the page scrolls. */
  const header = document.getElementById('site-header');
  if (header) {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { header.classList.toggle('is-scrolled', window.scrollY > 8); ticking = false; });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    // Sticky toolbars and cards sit just under the navbar: --header-live is its current height.
    const setHeight = () => root.style.setProperty('--header-live', `${header.offsetHeight}px`);
    if (window.ResizeObserver) new ResizeObserver(setHeight).observe(header);
    setHeight();
  }

  /* Phone menu: tapping a link closes it (data-bs-dismiss would cancel the link). */
  document.addEventListener('click', (e) => {
    const link = e.target.closest('.offcanvas a[href]');
    if (link && window.bootstrap) window.bootstrap.Offcanvas.getInstance(link.closest('.offcanvas'))?.hide();
  });

  /* "Get the app" strip: closing it hides it for 30 days (a cookie, so the server stops rendering it). */
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-app-strip-close]')) return;
    document.cookie = `app_strip=off; max-age=${60 * 60 * 24 * 30}; path=/; samesite=lax`;
    document.getElementById('app-strip')?.remove();
  });

  window.ZCH = { api, esc, kes, store, poll, busy, toast, applyTheme };
})();
