# JOBIRA Dashboard: phone and tablet app

`../mobile_dashboard.py` serves an installable app (PWA) on `127.0.0.1:8430`. JOBIRA 2 has its own copy in `~/JOBIRA2/mobile_dashboard.py` on port 8431. The two apps have different names, icons and colours.

What the app does:
- **Apply next**: open jobs in priority order (`rank.py`). Each job has an **Apply** button that opens the posting, plus **Resume** and **Cover** buttons and a status menu.
- **All jobs**: search and filter by Open, To apply, Applied, Responses, Filtered out or All.
- **Files**: every PDF in `resumes/` and `cover_letters/`, with the jobs each one was used for. Tap a file to open it, or use the download button to save it.
- **Refresh**: the button in the top bar. The app also refreshes whenever you switch back to it. If the laptop is off, it shows the last data it loaded.
- **Status changes** rewrite only that row's `Status` (after a confirm prompt), then refresh the xlsx, the same as the desktop dashboard.

## Always on
Two systemd user services keep the servers running whenever you're logged in. They restart if they crash.

    systemctl --user status jobira-dashboard jobira2-dashboard
    systemctl --user restart jobira-dashboard      # after editing mobile_dashboard.py

## Access from anywhere (Tailscale)
The servers only listen on localhost. Tailscale makes them reachable from your own devices on any network, over HTTPS. Nothing is published to the public internet. See `remote_access.sh` for the one-time setup. On the tablet or phone, install the Tailscale app and sign in with the same account. Then open the URLs the script prints and use **Install app** (or **Add to Home screen**) for each one.

## Passcode
Each new device asks for a passcode once. The passcodes are stored in `mobile/.passcode` (mode 600). To view them, run `cat ~/JOBIRA/mobile/.passcode`. To sign every device out, delete that file and run `systemctl --user restart jobira-dashboard`; a new passcode is generated.

## Icons
To redraw the icons: `python3 mobile/make_icons.py "J" "#4355B9" "#DEE0FF"` (needs Pillow).

## Android apps (APKs)
`android/build_apks.sh` builds `android/out/JOBIRA_Dashboard.apk` and `JOBIRA_2_Dashboard.apk`, about 17 KB each. It doesn't use Gradle; it runs aapt2, javac, d8 and apksigner from `~/Android/Sdk` and `~/.local/share/jdk17`. Each APK is a WebView wrapper around its Tailscale URL that always uses the black dark theme.
- Job links open in the tablet's browser.
- Resume and cover-letter PDFs are downloaded to `Downloads/JOBIRA/` and then open in the PDF viewer.
- If the laptop can't be reached, the app shows a Retry screen.

To rebuild and install over USB, run `bash android/build_apks.sh install`. Keep `android/keystore.jks` and `.keystore_pass`, because an update only installs over the existing app if it's signed with the same key.
