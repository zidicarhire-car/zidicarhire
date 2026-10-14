/* Admin dashboard: paid-booking alerts, live page updates, confirmation dialogs and the chat inbox. */
(function () {
  const { api, esc, kes, poll } = window.ZCH;
  const feedUrl = document.body.dataset.feedUrl;
  const known = new Map();            // ref -> status
  let since = '';
  let firstLoad = true;
  let lastUnread = 0;

  /* ---------- Alerts ---------- */
  function chime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [880, 1175].forEach((freq, i) => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.frequency.value = freq;
        o.connect(g); g.connect(ctx.destination);
        const t = ctx.currentTime + i * 0.18;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
        o.start(t); o.stop(t + 0.5);
      });
    } catch (e) { /* audio blocked until the admin clicks the page once */ }
  }

  const toast = (title, text, href) => window.ZCH.toast(title, text, { href });

  function desktopAlert(title, body, href) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    const n = new Notification(title, { body, tag: title });
    n.onclick = () => { window.focus(); if (href) location.href = href; };
  }

  function alertAll(title, body, href) { chime(); toast(title, body, href); desktopAlert(title, body, href); }

  const alertsBtn = document.getElementById('alerts-btn');
  function syncAlertsBtn() {
    if (!('Notification' in window)) { alertsBtn.hidden = true; return; }
    alertsBtn.hidden = Notification.permission === 'granted';
  }
  alertsBtn?.addEventListener('click', async () => {
    await Notification.requestPermission();
    syncAlertsBtn();
    if (Notification.permission === 'granted') toast('Desktop alerts on', "You'll get a pop-up for each paid booking and chat.");
  });
  if (alertsBtn) syncAlertsBtn();

  /* ---------- Live page updates ---------- */
  /* Pages mark the changing part with data-live; it is re-fetched (?partial=1) when bookings change. */
  let refreshing = false;
  async function refreshLive() {
    const box = document.querySelector('[data-live]');
    if (!box || refreshing || document.querySelector('dialog[open]')) return;
    if (box.contains(document.activeElement)) return;   // don't pull the page from under the keyboard
    refreshing = true;
    try {
      const url = new URL(location.href);
      url.searchParams.set('partial', '1');
      const res = await fetch(url, { credentials: 'same-origin' });
      if (res.ok && !res.redirected) box.innerHTML = await res.text();
    } catch (e) { /* try again on the next change */ }
    refreshing = false;
  }

  /* ---------- Feed (runs on every dashboard page) ---------- */
  async function feed() {
    const url = since ? `${feedUrl}?since=${encodeURIComponent(since)}` : feedUrl;
    let res;
    try { res = await api(url); } catch (err) {
      if (err.status === 401) location.href = '/dashboard/login/?next=' + encodeURIComponent(location.pathname);
      return;
    }
    since = res.server_time;

    res.bookings.slice().reverse().forEach((b) => {
      const prev = known.get(b.ref);
      if (!firstLoad) {
        const where = [b.city, b.pickup_point].filter(Boolean).join(', ');
        if (b.just_paid) {
          alertAll(`Paid: ${b.car}${b.city ? ` (${b.city})` : ''}`,
            `${b.customer_name} paid ${kes(b.amount)} (${b.ref})${where ? `. Pick-up: ${where}` : ''}${b.return_city ? `. One-way to ${b.return_city}` : ''}`,
            `/dashboard/bookings/${b.ref}/`);
        } else if (!prev && b.status === 'pending') {
          toast('New booking started', `${b.customer_name} is paying for ${b.car}${b.city ? ` in ${b.city}` : ''}`);
        }
      }
      known.set(b.ref, b.status);
    });

    if (!firstLoad && res.bookings.length) refreshLive();
    updateChatBadge(res.unread_chats);
    firstLoad = false;
  }

  function updateChatBadge(n) {
    const badge = document.getElementById('chat-badge');
    badge.textContent = n;
    badge.hidden = !n;
    if (!firstLoad && n > lastUnread && !document.getElementById('inbox-list')) {
      alertAll('New chat message', 'A visitor is waiting for a reply.', '/dashboard/chats/');
    }
    lastUnread = n;
    document.title = (n ? `(${n}) ` : '') + document.title.replace(/^\(\d+\)\s/, '');
  }

  /* ---------- Dialogs and confirmations ---------- */
  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open-dialog]');
    if (opener) {
      const dlg = document.getElementById(opener.dataset.openDialog);
      if (dlg) { dlg.showModal(); dlg.querySelector('textarea, input:not([type=hidden]), select')?.focus(); }
      return;
    }
    const closer = e.target.closest('[data-close-dialog]');
    if (closer) closer.closest('dialog')?.close();
  });
  document.querySelectorAll('dialog[data-open-on-load]').forEach((dlg) => dlg.showModal());

  const confirmDialog = document.getElementById('confirm-dialog');
  let pendingForm = null;
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!form.dataset.confirm || form.dataset.confirmed) return;
    e.preventDefault();
    if (!confirmDialog) { if (window.confirm(form.dataset.confirm)) { form.dataset.confirmed = '1'; form.requestSubmit(); } return; }
    pendingForm = form;
    document.getElementById('confirm-text').textContent = form.dataset.confirm;
    const yes = document.getElementById('confirm-yes');
    yes.textContent = form.dataset.confirmYes || 'Yes';
    confirmDialog.showModal();
    yes.focus();
  });
  document.getElementById('confirm-yes')?.addEventListener('click', () => {
    if (!pendingForm) return;
    pendingForm.dataset.confirmed = '1';
    confirmDialog.close();
    pendingForm.requestSubmit();
  });

  /* ---------- Chats page ---------- */
  function initChats() {
    const listEl = document.getElementById('inbox-list');
    const active = document.getElementById('inbox-active');
    const empty = document.getElementById('inbox-empty');
    const msgs = document.getElementById('thread-messages');
    const form = document.getElementById('reply-form');
    const input = document.getElementById('reply-input');
    let current = new URLSearchParams(location.search).get('c');
    let lastId = 0;
    const seen = new Set();
    let threadPoller = null;
    const unreadByChat = new Map();

    async function loadList() {
      const res = await api('/dashboard/api/chats/');
      if (!res.chats.length) { listEl.innerHTML = '<li class="muted pad">No chats yet. When a visitor writes, it shows here and you get an alert.</li>'; return; }
      res.chats.forEach((c) => {
        const before = unreadByChat.get(c.id) ?? c.unread;
        if (c.unread > before && c.id !== current) alertAll(`Chat: ${c.name}`, c.preview, `/dashboard/chats/?c=${c.id}`);
        unreadByChat.set(c.id, c.unread);
      });
      listEl.innerHTML = res.chats.map((c) => `
        <li><button type="button" class="inbox-item${c.id === current ? ' is-active' : ''}" data-id="${esc(c.id)}">
          <span class="inbox-row"><strong>${esc(c.name)}</strong><time>${esc(c.time)}</time></span>
          <span class="city-tag">${esc(c.city)}</span>
          <span class="inbox-preview">${esc(c.preview)}</span>
          ${c.unread && c.id !== current ? `<span class="badge">${c.unread}</span>` : ''}
        </button></li>`).join('');
    }

    function renderMsgs(list) {
      list.forEach((m) => {
        if (seen.has(m.id)) return;
        seen.add(m.id);
        lastId = Math.max(lastId, m.id);
        const li = document.createElement('li');
        li.className = `msg msg-${m.sender === 'admin' ? 'me' : 'them'}`;
        li.innerHTML = `<p>${esc(m.body)}</p><time>${esc(m.time)}</time>`;
        msgs.appendChild(li);
      });
      if (list.length) msgs.scrollTop = msgs.scrollHeight;
    }

    async function loadThread() {
      if (!current) return;
      const res = await api(`/dashboard/api/chats/${current}/messages/?after=${lastId}`);
      document.getElementById('thread-name').textContent = res.name;
      document.getElementById('thread-contact').textContent = res.contact || '';
      const citySelect = document.getElementById('thread-city');
      if (citySelect && document.activeElement !== citySelect) citySelect.value = String(res.city_id || '');
      const cityTag = document.getElementById('thread-city-tag');
      if (cityTag) cityTag.textContent = res.city || '';
      renderMsgs(res.messages);
    }

    function openChat(id) {
      current = id;
      lastId = 0; seen.clear(); msgs.innerHTML = '';
      empty.hidden = true; active.hidden = false;
      history.replaceState(null, '', `?c=${id}`);
      listEl.querySelectorAll('.inbox-item').forEach((b) => b.classList.toggle('is-active', b.dataset.id === id));
      if (threadPoller) threadPoller.stop();
      threadPoller = poll(loadThread, 3000, 10000);
      input.focus();
    }

    listEl.addEventListener('click', (e) => {
      const b = e.target.closest('.inbox-item');
      if (b) openChat(b.dataset.id);
    });

    async function sendReply() {
      const body = input.value.trim();
      if (!body || !current) return;
      input.value = '';
      try {
        const res = await api(`/dashboard/api/chats/${current}/reply/`, { method: 'POST', body: { body } });
        renderMsgs([res.message]);
        loadList();
      } catch (err) { input.value = body; toast("Reply not sent", err.message); }
    }
    form.addEventListener('submit', (e) => { e.preventDefault(); sendReply(); });
    document.getElementById('thread-city')?.addEventListener('change', async (e) => {
      if (!current) return;
      try {
        const res = await api(`/dashboard/api/chats/${current}/assign/`, { method: 'POST', body: { city_id: e.target.value } });
        toast('Chat moved', res.city ? `The ${res.city} branch can now see this chat.` : 'This chat has no city now.');
        loadList();
      } catch (err) { toast("Couldn't move chat", err.message); }
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(); } });

    poll(loadList, 5000, 15000);
    if (current) openChat(current);
  }

  poll(feed, 5000, 15000);
  window.ZCHDash = { initChats };
})();
