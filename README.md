# \---

# TruthSync AI — Verify Before You Believe.

News verification (text, image, link, social post) with evidence, login, history, analytics and an
**ESP32 + SSD1306 OLED** display that shows the verdict — and confirms it was really displayed.

It builds on your original `fake-news-detector` project: `verifier.py`, `facts.py`, `common.py` and
`model.pkl` are reused unchanged.

\---

## 0\. What is tested and what is not (read this first)

|Part|Status|
|-|-|
|Database, passwords, SSRF protection, device keys, delivery flow, device HTTP API, rate limit|**Automatically tested** (`pytest`, 50 tests pass)|
|Every Streamlit page loads and the main buttons work|Tested with a **stand-in for Streamlit** (catches code errors)|
|How the pages **look** in a real browser|**NOT tested** — run it and check|
|ESP32 firmware|**NOT compiled, NOT tested on hardware** — follow the checklist in section 7|
|Web search / OCR / YouTube lookup|Need internet; not run in the test sandbox|

**Not built in this version** (be honest with your client): video verification, PDF report download
(CSV export works), light theme, storing uploaded images (only the extracted text is saved),
Raspberry Pi Pico W (you asked for ESP32 only), PostgreSQL (SQLite only for now).

## 1\. Install (Windows PowerShell)

Install Python 3.11 or 3.12 from python.org (tick **Add Python to PATH**). Then:

```powershell
cd $HOME\\Desktop
Expand-Archive truthsync-ai.zip -DestinationPath .
cd truthsync-ai
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

If activation is blocked: `Set-ExecutionPolicy -Scope Process Bypass` and run the activate line again.
In `.env` set `ADMIN\_EMAIL` to **your** email (that account becomes admin) and `DEV\_MODE=1` while
testing locally (so password-reset codes show on screen).

## 2\. Run (two PowerShell windows, both inside the `truthsync-ai` folder)

Window 1 — the **device API** (what the ESP32 talks to):

```powershell
.\\.venv\\Scripts\\Activate.ps1
uvicorn api:app --host 0.0.0.0 --port 8000
```

Window 2 — the **web app**:

```powershell
.\\.venv\\Scripts\\Activate.ps1
streamlit run app.py
```

Open http://localhost:8501. Windows may ask to allow Python through the firewall: allow **Private networks**.

## 3\. Test the software (no hardware needed) — 10 minutes

1. **Create account** with your `ADMIN\_EMAIL`, sign in. You should see **Admin Dashboard** in the sidebar. Create a second account with another email; it must **not** show Admin.
2. **Verify Content → Text**: paste `Virat Kohli got divorced from Anushka Sharma` → *LIKELY FAKE*, assessment type *Curated fact entry*.
3. Paste a real headline → sources list appears (needs internet). No sources → *UNVERIFIED* or *INSUFFICIENT INFORMATION*, never a guess.
4. **Image** tab: upload a JPG/PNG poster containing text. **URL** tab: paste a public news link. Try `http://127.0.0.1` → must be **blocked**.
5. **Social** tab: an Instagram link asks you to paste text (this is deliberate, not a bug).
6. **Verification History**: filter, open a report, export CSV, delete.
7. **Device Management → Register a new device**. Copy the Device ID and API key (shown once).
8. Simulate the ESP32 without hardware (replace the two values):

```powershell
$h = @{ "X-Device-ID"="esp32\_xxxxxxxxxx"; "X-API-Key"="tsk\_xxxxxxxx" }
# In the web app click "Send test message" first, then:
$m = Invoke-RestMethod http://localhost:8000/api/device/messages/latest -Headers $h
$m.message.pages
# Status in the app is "sent", NOT "displayed". Now confirm:
$body = '{"message\_id":"' + $m.message.message\_id + '","displayed":true}'
Invoke-RestMethod -Method Post http://localhost:8000/api/device/messages/acknowledge -Headers $h -ContentType "application/json" -Body $body
```

Click **Refresh status** in the app: it becomes **displayed**, the device shows **Online**.

Automatic tests: `pip install -r requirements-dev.txt` then `python -m pytest tests -q`.

## 4\. ESP32 + OLED hardware

**Parts:** ESP32 dev board, 0.96" SSD1306 I2C OLED (128x64), 4 jumper wires, USB cable.

|OLED|ESP32|
|-|-|
|VCC|3V3|
|GND|GND|
|SDA|GPIO 26|
|SCL|GPIO 27|

**Arduino IDE setup**

1. Boards Manager → install **esp32 by Espressif Systems**. Board: *ESP32 Dev Module*.
2. Library Manager → install **Adafruit SSD1306**, **Adafruit GFX Library**, **ArduinoJson** (v7).
3. Open `firmware/esp32\_oled\_final/esp32\_oled\_final.ino`.
4. Edit the settings block at the top of that same file (Wi-Fi, `SERVER\_URL`, `DEVICE\_ID`, `DEVICE\_KEY`). There is no `config.h` any more.

   * Find your PC's address with `ipconfig` (IPv4), e.g. `http://192.168.1.50:8000`.
   * The ESP32 and the PC must be on the **same Wi-Fi** (guest Wi-Fi often blocks this; a phone hotspot works).
5. Upload. Open Serial Monitor at 115200.

If the screen stays blank, the address may be `0x3D` instead of `0x3C` (`OLED\_ADDR` in the sketch).

**HTTPS note:** plain `http://` is fine for testing on your own Wi-Fi. For a public deployment use `https://` and paste your server's root CA into `ROOT\_CA` in the settings block of the sketch; without it the sketch does **not** validate the certificate (testing only).

## 5\. Deployment — what actually works

The ESP32 needs an API that is **always on** and shares the database with the web app. Streamlit Community Cloud
only runs the Streamlit app (it sleeps, and its files are not permanent). Therefore:

* **Recommended for your client demo today:** run both programs on your laptop (section 2). Optional: a free
HTTPS tunnel (e.g. Cloudflare Tunnel or ngrok) gives the ESP32 an `https://` address to your laptop's port 8000.
* **Streamlit Community Cloud:** the web UI can be deployed (push to GitHub → share.streamlit.io → main file `app.py`;
put values from `.env.example` into *Secrets*), but on its own it would use a temporary SQLite file that resets, and
the device API is not running there — so **the OLED flow does not work from Streamlit Cloud with this version.**
* **Full cloud setup (next step, not done):** move the database to a free hosted PostgreSQL (Neon/Supabase), run
`api.py` on a free web service (Render), keep Streamlit on Streamlit Cloud. This needs the database layer
(`db.py`) converted from SQLite — about a day of work.

Login sessions are held in the Streamlit server's memory: refreshing the browser tab signs you out.

## 6\. Which features need keys (all have free options)

|Feature|Needs|Without it|
|-|-|-|
|Web evidence search|Internet (DuckDuckGo via `ddgs`, no key)|Verdict becomes UNVERIFIED / INSUFFICIENT|
|Fact-check lookup|Free Google Fact Check API key (optional)|Skipped|
|Image text reading (OCR)|Free key from ocr.space (shared demo key works but is limited)|Uses shared key|
|Password-reset email|SMTP settings|Reset disabled (or dev-mode code on screen)|
|Stronger NLI / local OCR|`pip install -r requirements-full.txt` (heavy)|Lighter heuristic mode|

## 7\. Hardware test checklist

* \[ ] OLED shows "Starting..." then "Connecting Wi-Fi..." after upload
* \[ ] Device appears **Online** in the app within \~30 s
* \[ ] "Send test message" → OLED shows TEST MESSAGE; app status becomes **displayed**
* \[ ] Verify a claim → send to device → verdict screen, then headline screen
* \[ ] Unplug the ESP32 → app shows **Offline** after \~45 s and a notification appears
* \[ ] Turn Wi-Fi/API off → OLED shows OFFLINE / SERVER OFFLINE, recovers when back
* \[ ] Wrong key in the sketch → OLED shows AUTH FAILED
* \[ ] Revoke the device in the app → it can no longer fetch messages

## 8\. Security notes

Passwords: scrypt hashes. Device keys: random, shown once, only a SHA-256 hash stored. Every device request
needs `X-Device-ID` + `X-API-Key`; wrong, unknown and revoked all get the same `401`. Per-device message isolation,
rate limiting, message expiry (30 min) and at most 5 delivery attempts. URL fetching blocks private/internal
addresses, re-checks every redirect, and caps time and size (known limit: DNS-rebinding is not fully prevented).
Secrets live in `.env` / Streamlit secrets; `.gitignore` excludes `.env`, databases and `config.h`.

## 9\. Files

```
app.py            web app (all pages)          api.py        device API (run separately)
engine.py         verification pipeline        devices.py    device + delivery logic
security.py       hashing, SSRF, URL fetch     db.py         SQLite schema
store.py          saving reports               ui.py         styling
verifier.py facts.py common.py model.pkl       (from your original project, unchanged)
firmware/esp32\_oled/   Arduino sketch + config.example.h
tests/            50 automated tests
```

