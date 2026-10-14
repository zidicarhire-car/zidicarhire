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
      box.className = 'toasts';
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    const el = document.createElement(href ? 'a' : 'div');
    el.className = 'toast' + (kind ? ` toast-${kind}` : '');
    if (href) el.href = href;
    el.innerHTML = `<strong>${esc(title)}</strong>${text ? `<span>${esc(text)}</span>` : ''}`;
    box.appendChild(el);
    setTimeout(() => el.classList.add('out'), ms);
    setTimeout(() => el.remove(), ms + 400);
    return el;
  }

  /* Tabs: <div role="tablist"> with <button role="tab" aria-controls="panel-id">. Arrow keys, Home and End move. */
  function initTabs(root = document) {
    root.querySelectorAll('[role="tablist"]').forEach((list) => {
      const tabs = [...list.querySelectorAll('[role="tab"]')];
      if (!tabs.length) return;
      const select = (tab, focus) => {
        tabs.forEach((t) => {
          const on = t === tab;
          t.setAttribute('aria-selected', String(on));
          t.tabIndex = on ? 0 : -1;
          const panel = document.getElementById(t.getAttribute('aria-controls'));
          if (panel) panel.hidden = !on;
        });
        if (focus) tab.focus();
      };
      tabs.forEach((t, i) => {
        t.addEventListener('click', () => select(t));
        t.addEventListener('keydown', (e) => {
          const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
          let next = null;
          if (step) next = tabs[(i + step + tabs.length) % tabs.length];
          else if (e.key === 'Home') next = tabs[0];
          else if (e.key === 'End') next = tabs[tabs.length - 1];
          if (next) { e.preventDefault(); select(next, true); }
        });
      });
      select(tabs.find((t) => t.getAttribute('aria-selected') === 'true') || tabs[0]);
    });
  }
  initTabs();

  window.ZCH = { api, esc, kes, store, poll, busy, toast, initTabs };
})();
