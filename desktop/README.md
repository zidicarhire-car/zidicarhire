# ZidiCarHire for Windows

The live website (www.zidicarhire.com) in its own desktop window, built with Electron. Booking, M-Pesa payments,
receipts, chat and the staff dashboard all run on the website, so the app never needs updating when the site changes.

What the app adds:

- Its own window and Start-menu/desktop shortcuts. It remembers its size and position, and only one copy runs at a time.
- A menu: Home, Cars, Find my booking, Staff dashboard (Ctrl+Shift+D), Print (Ctrl+P), zoom, back and forward.
- Phone, email, WhatsApp, maps and other websites open in the right program, not inside the app.
- Receipts and other downloads go to the Downloads folder, which then opens with the file selected.
- A "You're offline" screen with a retry button when there is no internet.
- The website hides its "Get the app" strip inside the app (it looks for `ZidiCarHireDesktop` in the user agent).

## Run it while developing

```
cd desktop
npm install
npm start
```

To point it at your local site instead of the live one, set `ZIDI_URL` first, for example
`ZIDI_URL=http://127.0.0.1:8000 npm start`.

If `npm start` fails with "bad option" from inside VS Code, the editor has set `ELECTRON_RUN_AS_NODE`. Run it from a
normal terminal, or clear that variable first.

## Build the installer

```
npm run dist
```

This writes `dist/ZidiCarHire-Setup-<version>.exe`. Raise `version` in `package.json` for each new release.

The installer is not code-signed, so Windows SmartScreen shows "Windows protected your PC" the first time. People
click **More info**, then **Run anyway**; the `/app/` page on the website explains this. To remove the warning, buy a
code-signing certificate and set `CSC_LINK` and `CSC_KEY_PASSWORD` before `npm run dist`.

## Publish it

Upload the installer (and the Android `.apk`) to a GitHub release, then set the links in the server's `.env`:

```
APP_WINDOWS_URL=https://github.com/zidicarhire-car/zidicarhire/releases/latest/download/ZidiCarHire-Setup.exe
APP_ANDROID_URL=https://github.com/zidicarhire-car/zidicarhire/releases/latest/download/ZidiCarHire.apk
```

`releases/latest/download/<file name>` always points at the newest release, so keep the uploaded file names the same.
With a link set, the website shows a "Get the app" strip to visitors on that platform and lists the download on `/app/`.
