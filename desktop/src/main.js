/**
 * ZidiCarHire for Windows: the live website in its own window, with desktop touches. Booking, M-Pesa payments,
 * receipts, chat and the staff dashboard all run on the website, so the app is always up to date.
 */
const { app, BrowserWindow, Menu, dialog, shell, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const SITE = (process.env.ZIDI_URL || 'https://www.zidicarhire.com').replace(/\/$/, '');
const ORIGIN = new URL(SITE).origin;
// Sites that belong to the same business and may open inside the window (www and bare domain).
const OWN_HOSTS = new Set([new URL(SITE).hostname, new URL(SITE).hostname.replace(/^www\./, '')]);
// The website hides its "Get the app" strip when it sees this.
const UA_TAG = `ZidiCarHireDesktop/${app.getVersion()}`;

let win = null;

// ---------- Window size and position, remembered between runs ----------
const stateFile = () => path.join(app.getPath('userData'), 'window.json');
function loadState() {
  try { return JSON.parse(fs.readFileSync(stateFile(), 'utf8')); } catch { return { width: 1280, height: 860 }; }
}
function saveState() {
  if (!win || win.isDestroyed()) return;
  const state = { ...win.getNormalBounds(), maximized: win.isMaximized() };
  try { fs.writeFileSync(stateFile(), JSON.stringify(state)); } catch { /* not critical */ }
}

const isOwn = (url) => {
  try {
    const u = new URL(url);
    return u.origin === ORIGIN || (u.protocol === 'https:' && OWN_HOSTS.has(u.hostname));
  } catch { return false; }
};
// Phone, email, WhatsApp, maps and any other site open in the right app on the computer, not in this window.
const openOutside = (url) => {
  if (/^(https?|mailto|tel|whatsapp):/i.test(url)) shell.openExternal(url);
};

function go(pathname) {
  if (win) win.loadURL(SITE + pathname);
}

function showOffline(failedUrl) {
  win.loadFile(path.join(__dirname, 'offline.html'), { query: { retry: isOwn(failedUrl) ? failedUrl : SITE } });
}

function createWindow() {
  const state = loadState();
  win = new BrowserWindow({
    x: state.x, y: state.y, width: state.width, height: state.height, minWidth: 380, minHeight: 560,
    title: 'ZidiCarHire',
    backgroundColor: '#1C2340',
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    show: false,
    autoHideMenuBar: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: true },
  });
  if (state.maximized) win.maximize();
  win.once('ready-to-show', () => win.show());
  ['resize', 'move', 'close'].forEach((e) => win.on(e, saveState));

  const wc = win.webContents;
  wc.setUserAgent(`${wc.getUserAgent()} ${UA_TAG}`);

  // Links that try to open a new window: our own pages stay in this window, everything else goes outside.
  wc.setWindowOpenHandler(({ url }) => {
    if (isOwn(url)) wc.loadURL(url); else openOutside(url);
    return { action: 'deny' };
  });
  wc.on('will-navigate', (event, url) => {
    if (url.startsWith('file:') || isOwn(url)) return;
    event.preventDefault();
    openOutside(url);
  });

  // No internet, or the site is down: a friendly page with a retry button instead of a blank window.
  wc.on('did-fail-load', (_e, code, _desc, url, isMainFrame) => {
    if (isMainFrame && code !== -3 && !url.startsWith('file:')) showOffline(url);   // -3 is a cancelled load, not an error
  });

  win.loadURL(SITE + '/');
}

// ---------- Downloads (receipts and booking PDFs): save to Downloads and show the file ----------
function handleDownloads() {
  session.defaultSession.on('will-download', (_event, item) => {
    const target = path.join(app.getPath('downloads'), item.getFilename());
    item.setSavePath(target);
    item.once('done', (_e, state) => {
      if (state === 'completed') {
        shell.showItemInFolder(target);
      } else if (state !== 'cancelled' && win) {
        dialog.showMessageBox(win, { type: 'warning', message: 'The download did not finish.', detail: 'Check your internet and try again.' });
      }
    });
  });
  // The website only needs notifications (staff alerts) and the clipboard; everything else is refused.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, done) => {
    done(['notifications', 'clipboard-sanitized-write'].includes(permission));
  });
}

// ---------- Menu ----------
function buildMenu() {
  const template = [
    {
      label: 'ZidiCarHire',
      submenu: [
        { label: 'Home', accelerator: 'Alt+Home', click: () => go('/') },
        { label: 'Cars', accelerator: 'CmdOrCtrl+Shift+C', click: () => go('/cars/') },
        { label: 'Find my booking', accelerator: 'CmdOrCtrl+Shift+F', click: () => go('/bookings/find/') },
        { type: 'separator' },
        { label: 'Staff dashboard', accelerator: 'CmdOrCtrl+Shift+D', click: () => go('/dashboard/') },
        { type: 'separator' },
        { label: 'Print…', accelerator: 'CmdOrCtrl+P', click: () => win?.webContents.print() },
        { label: 'Open in browser', click: () => win && shell.openExternal(isOwn(win.webContents.getURL()) ? win.webContents.getURL() : SITE) },
        { type: 'separator' },
        { role: 'quit', label: 'Quit ZidiCarHire' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Back', accelerator: 'Alt+Left', click: () => win?.webContents.navigationHistory.canGoBack() && win.webContents.navigationHistory.goBack() },
        { label: 'Forward', accelerator: 'Alt+Right', click: () => win?.webContents.navigationHistory.canGoForward() && win.webContents.navigationHistory.goForward() },
        { role: 'reload' },
        { type: 'separator' },
        { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'resetZoom', label: 'Actual size' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        ...(app.isPackaged ? [] : [{ role: 'toggleDevTools' }]),
      ],
    },
    { role: 'editMenu' },
    {
      label: 'Help',
      submenu: [
        { label: 'Questions', click: () => go('/faq/') },
        { label: 'Contact us', click: () => go('/contact/') },
        { type: 'separator' },
        { label: `Version ${app.getVersion()}`, enabled: false },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---------- Start: one copy at a time ----------
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.focus();
  });
  app.setAppUserModelId('com.zidicarhire.desktop');
  app.whenReady().then(() => {
    handleDownloads();
    buildMenu();
    createWindow();
  });
  app.on('window-all-closed', () => app.quit());
}
