/* Admin dashboard: paid-booking alerts, live page updates, popups and confirmations, and the chat inbox. */
(function () {
  const { api, esc, kes, poll } = window.ZCH;
  const bs = window.bootstrap;
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

  /* The bell on phones: what came in since the page opened. */
  const notes = [];
  let unseen = 0;
  function remember(title, body, href) {
    notes.unshift({ title, body, href, at: new Date() });
    notes.length = Math.min(notes.length, 20);
    unseen += 1;
    const time = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    document.querySelectorAll('[data-notify-list]').forEach((ul) => {
      ul.innerHTML = notes.map((n) => `<li><a class="dropdown-item notify-item" href="${esc(n.href || '#')}">
        <strong>${esc(n.title)}</strong><span>${esc(n.body)}</span><time>${time(n.at)}</time></a></li>`).join('');
    });
    document.querySelectorAll('[data-notify-count]').forEach((b) => { b.textContent = unseen; b.hidden = !unseen; });
  }
  document.querySelectorAll('[data-notify-toggle]').forEach((btn) => btn.addEventListener('show.bs.dropdown', () => {
    unseen = 0;
    document.querySelectorAll('[data-notify-count]').forEach((b) => { b.hidden = true; });
  }));

  function alertAll(title, body, href) { chime(); toast(title, body, href); desktopAlert(title, body, href); remember(title, body, href); }

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
    if (!box || refreshing || document.querySelector('.modal.show, .dropdown-menu.show, .offcanvas.show')) return;
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
    alertWaiting(res.waiting_chats || []);
    firstLoad = false;
  }

  /* A visitor asked for a person: alert once per chat, on every dashboard page. */
  const waitingSeen = new Set();
  function alertWaiting(list) {
    if (firstLoad && list.length) {
      toast(list.length === 1 ? `${list[0].name} is waiting for a person` : `${list.length} chats are waiting for a person`,
        'Open Live chat to reply.', list.length === 1 ? `/dashboard/chats/?c=${list[0].id}` : '/dashboard/chats/');
    }
    list.forEach((c) => {
      if (waitingSeen.has(c.id)) return;
      waitingSeen.add(c.id);
      if (!firstLoad) alertAll(`${c.name} wants to talk to a person`, 'Open the chat and reply.', `/dashboard/chats/?c=${c.id}`);
    });
  }

  function updateChatBadge(n) {
    document.querySelectorAll('[data-chat-count]').forEach((badge) => { badge.textContent = n; badge.hidden = !n; });
    if (!firstLoad && n > lastUnread && !document.getElementById('inbox-list')) {
      alertAll('New chat message', 'A visitor is waiting for a reply.', '/dashboard/chats/');
    }
    lastUnread = n;
    document.title = (n ? `(${n}) ` : '') + document.title.replace(/^\(\d+\)\s/, '');
  }

  /* ---------- Popups and confirmations (Bootstrap modals) ---------- */
  const modal = (el) => bs.Modal.getOrCreateInstance(el);
  function openPopup(el) {
    el.addEventListener('shown.bs.modal', () => el.querySelector('textarea, input:not([type=hidden]), select')?.focus(), { once: true });
    modal(el).show();
  }
  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open-dialog]');
    if (opener) {
      const el = document.getElementById(opener.dataset.openDialog);
      if (el) openPopup(el);
      return;
    }
    const closer = e.target.closest('[data-close-dialog]');
    if (closer) { const el = closer.closest('.modal'); if (el) modal(el).hide(); }
  });
  document.querySelectorAll('.modal[data-open-on-load]').forEach(openPopup);

  /* confirm(text, yesLabel) -> Promise<boolean>, in the shared #confirm-dialog. */
  const confirmEl = document.getElementById('confirm-dialog');
  function confirmBox(text, yesLabel = 'Yes') {
    if (!confirmEl) return Promise.resolve(window.confirm(text));
    return new Promise((resolve) => {
      let answer = false;
      document.getElementById('confirm-text').textContent = text;
      const yes = document.getElementById('confirm-yes');
      yes.textContent = yesLabel;
      yes.className = /delete|cancel/i.test(yesLabel) ? 'btn btn-danger' : 'btn btn-primary';
      const onYes = () => { answer = true; modal(confirmEl).hide(); };
      yes.addEventListener('click', onYes, { once: true });
      confirmEl.addEventListener('shown.bs.modal', () => yes.focus(), { once: true });
      confirmEl.addEventListener('hidden.bs.modal', () => { yes.removeEventListener('click', onYes); resolve(answer); }, { once: true });
      modal(confirmEl).show();
    });
  }

  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!form.dataset.confirm || form.dataset.confirmed) return;
    e.preventDefault();
    if (await confirmBox(form.dataset.confirm, form.dataset.confirmYes || 'Yes')) {
      form.dataset.confirmed = '1';
      form.requestSubmit();
    }
  });

  /* Switches and selects that save straight away (show/hide a car, the city picker). */
  document.addEventListener('change', (e) => {
    if (e.target.matches('[data-autosubmit]')) e.target.form?.requestSubmit();
  });

  /* ---------- Chats page ---------- */
  function initChats() {
    const inbox = document.getElementById('inbox');
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
      if (!res.chats.length) {
        listEl.innerHTML = '<li class="inbox-none"><i class="bi bi-inbox" aria-hidden="true"></i>No chats yet. When a visitor writes, it shows here and you get an alert.</li>';
        return;
      }
      res.chats.forEach((c) => {
        const before = unreadByChat.get(c.id) ?? c.unread;
        if (c.unread > before && c.id !== current) alertAll(`Chat: ${c.name}`, c.preview, `/dashboard/chats/?c=${c.id}`);
        unreadByChat.set(c.id, c.unread);
      });
      listEl.innerHTML = res.chats.map((c) => `
        <li><button type="button" class="inbox-item${c.id === current ? ' is-active' : ''}" data-id="${esc(c.id)}">
          <span class="inbox-row"><strong>${esc(c.name)}</strong><time>${esc(c.time)}</time></span>
          <span class="inbox-tags"><span class="city-tag">${esc(c.city)}</span>${c.wants_agent ? '<span class="status status-pending">Wants a person</span>' : ''}</span>
          <span class="inbox-preview">${esc(c.preview)}</span>
          ${c.unread && c.id !== current ? `<span class="badge rounded-pill text-bg-plate">${c.unread}<span class="visually-hidden"> unread</span></span>` : ''}
        </button></li>`).join('');
    }

    function renderMsgs(list) {
      list.forEach((m) => {
        if (seen.has(m.id)) return;
        seen.add(m.id);
        lastId = Math.max(lastId, m.id);
        const li = document.createElement('li');
        li.className = `msg msg-${m.sender === 'visitor' ? 'them' : 'me'}${m.sender === 'bot' ? ' msg-bot' : ''}`;
        li.innerHTML = `${m.label ? `<span class="msg-label">${esc(m.label)}</span>` : ''}<p>${esc(m.body)}</p><time>${esc(m.time)}</time>`;
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
      inbox.classList.add('has-thread');                 // phones: the conversation takes the whole screen
      document.documentElement.classList.add('inbox-open');
      history.replaceState(null, '', `?c=${id}`);
      listEl.querySelectorAll('.inbox-item').forEach((b) => b.classList.toggle('is-active', b.dataset.id === id));
      if (threadPoller) threadPoller.stop();
      threadPoller = poll(loadThread, 3000, 10000);
      if (window.matchMedia('(min-width: 768px)').matches) input.focus();
    }

    function closeChat() {
      const id = current;
      current = null;
      if (threadPoller) { threadPoller.stop(); threadPoller = null; }
      inbox.classList.remove('has-thread');
      document.documentElement.classList.remove('inbox-open');
      active.hidden = true; empty.hidden = false;
      history.replaceState(null, '', location.pathname);
      listEl.querySelector(`.inbox-item[data-id="${id}"]`)?.focus();
    }

    listEl.addEventListener('click', (e) => {
      const b = e.target.closest('.inbox-item');
      if (b) openChat(b.dataset.id);
    });
    document.getElementById('inbox-back')?.addEventListener('click', closeChat);

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

    /* Phones: the full-screen conversation follows the visible height, so the reply box stays above the keyboard. */
    const vv = window.visualViewport;
    if (vv) vv.addEventListener('resize', () => inbox.style.setProperty('--vvh', `${Math.round(vv.height)}px`));

    poll(loadList, 5000, 15000);
    if (current) openChat(current);
  }

  poll(feed, 5000, 15000);
  if (document.getElementById('inbox-list')) initChats();
  window.ZCHDash = { initChats, confirm: confirmBox };
})();
