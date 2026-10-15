/* Visitor live chat widget. Polls for replies: fast while open, slow while closed. */
(function () {
  const { api, esc, store, poll } = window.ZCH;
  const root = document.getElementById('chat');
  if (!root) return;

  const launcher = document.getElementById('chat-launcher');
  const panel = document.getElementById('chat-panel');
  const intro = document.getElementById('chat-intro');
  const introError = document.getElementById('chat-intro-error');
  const thread = document.getElementById('chat-thread');
  const list = document.getElementById('chat-messages');
  const compose = document.getElementById('chat-compose');
  const input = document.getElementById('chat-input');
  const dot = document.getElementById('chat-dot');
  const presence = document.getElementById('chat-presence');
  const quick = document.getElementById('chat-quick');
  const agentBtn = document.getElementById('chat-agent');

  let chatId = store.get('zch_chat');
  let lastId = 0;
  let isOpen = false;
  let poller = null;
  const seen = new Set();

  /* The red dot on the chat button and the badge on the phone tab bar. */
  function setUnread(on) {
    dot.hidden = !on;
    document.querySelectorAll('[data-chat-badge]').forEach((b) => { b.hidden = !on; });
  }

  function setOpen(open) {
    isOpen = open;
    panel.hidden = !open;
    launcher.setAttribute('aria-expanded', String(open));
    root.classList.toggle('is-open', open);
    document.documentElement.classList.toggle('chat-open', open);   // phones: the page behind stops scrolling
    if (open) {
      setUnread(false);
      if (chatId) { showThread(); input.focus(); } else { intro.hidden = false; thread.hidden = true; intro.querySelector('input').focus(); }
    }
    restartPolling();
  }

  function showThread() { intro.hidden = true; thread.hidden = false; scrollDown(); }

  /* Plain text with web links made clickable (text is escaped first). */
  function linkify(text) {
    return esc(text).replace(/https?:\/\/[^\s<]+[^\s<.,;:!?)]/g, (url) => `<a href="${url}" target="_blank" rel="noopener">${url}</a>`);
  }

  function setWaitingForPerson(waiting) {
    agentBtn.disabled = waiting;
    agentBtn.textContent = waiting ? 'Team member requested' : 'Talk to a person';
  }
  function scrollDown() { list.scrollTop = list.scrollHeight; }

  function render(messages) {
    let gotReply = false;
    messages.forEach((m) => {
      if (seen.has(m.id)) return;
      seen.add(m.id);
      lastId = Math.max(lastId, m.id);
      const li = document.createElement('li');
      li.className = `msg msg-${m.sender === 'visitor' ? 'me' : 'them'}${m.sender === 'bot' ? ' msg-bot' : ''}`;
      li.innerHTML = `${m.label ? `<span class="msg-label">${esc(m.label)}</span>` : ''}<p>${linkify(m.body)}</p><time>${esc(m.time)}</time>`;
      list.appendChild(li);
      if (m.sender !== 'visitor') gotReply = true;
      if (m.sender === 'admin') { quick.hidden = true; setWaitingForPerson(false); }
    });
    if (messages.length) scrollDown();
    if (gotReply && !isOpen) setUnread(true);
  }

  async function fetchMessages() {
    if (!chatId) return;
    try {
      const res = await api(`/chat/${chatId}/messages/?after=${lastId}`);
      render(res.messages);
      presence.textContent = res.agent_online ? 'Online now' : 'Instant answers, or a person during opening hours';
      if (res.wants_agent) setWaitingForPerson(true);
      root.classList.toggle('agent-online', !!res.agent_online);
    } catch (err) {
      if (err.status === 404) { store.del('zch_chat'); chatId = null; }
    }
  }

  function restartPolling() {
    if (poller) poller.stop();
    if (chatId) poller = poll(fetchMessages, isOpen ? 3000 : 20000, 60000);
  }

  /* Pre-fill the city the visitor is looking at, so the right branch answers. */
  function presetCity(slug) {
    const select = intro.elements.city;
    if (!select) return;
    const wanted = slug || store.get('zch_city') || '';
    if ([...select.options].some((o) => o.value === wanted)) select.value = wanted;
  }

  launcher.addEventListener('click', () => { if (!isOpen) presetCity(); setOpen(!isOpen); });
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-open-chat]');
    if (!btn) return;
    presetCity(btn.dataset.chatCity);
    setOpen(true);
  });
  document.getElementById('chat-close').addEventListener('click', () => { setOpen(false); launcher.focus(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen) { setOpen(false); launcher.focus(); } });

  intro.addEventListener('submit', async (e) => {
    e.preventDefault();
    introError.textContent = '';
    const data = Object.fromEntries(new FormData(intro));
    if (!data.name.trim()) { introError.textContent = 'Enter your name to start chatting.'; return; }
    try {
      const res = await api(root.dataset.startUrl, { method: 'POST', body: data });
      chatId = res.id;
      store.set('zch_chat', chatId);
      showThread();
      input.focus();
      restartPolling();
    } catch (err) { introError.textContent = err.message; }
  });

  async function send(text) {
    const body = (text ?? input.value).trim();
    if (!body || !chatId) return;
    if (text === undefined) { input.value = ''; autosize(); }
    try {
      const res = await api(`/chat/${chatId}/send/`, { method: 'POST', body: { body } });
      render([res.message, ...(res.replies || [])]);
      if (res.wants_agent) setWaitingForPerson(true);
    } catch (err) {
      if (text === undefined) input.value = body;
      const li = document.createElement('li');
      li.className = 'msg msg-error';
      li.textContent = err.message;
      list.appendChild(li);
      scrollDown();
    }
  }

  compose.addEventListener('submit', (e) => { e.preventDefault(); send(); });
  quick.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-ask]');
    if (chip) send(chip.dataset.ask);
  });
  agentBtn.addEventListener('click', async () => {
    if (!chatId) return;
    agentBtn.disabled = true;
    try {
      const res = await api(`/chat/${chatId}/agent/`, { method: 'POST', body: {} });
      render(res.replies || []);
      setWaitingForPerson(true);
    } catch (err) {
      agentBtn.disabled = false;
      const li = document.createElement('li');
      li.className = 'msg msg-error';
      li.textContent = err.message;
      list.appendChild(li);
      scrollDown();
    }
  });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; }
  input.addEventListener('input', autosize);

  /* Phones: the full-screen panel follows the visible height, so the message box stays above the keyboard. */
  const vv = window.visualViewport;
  if (vv) vv.addEventListener('resize', () => panel.style.setProperty('--vvh', `${Math.round(vv.height)}px`));

  restartPolling();
})();
