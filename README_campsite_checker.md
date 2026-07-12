# Parks Canada Campsite Availability Checker

Polls Parks Canada's reservation site and texts you the moment a campsite opens up — just like Campnab, but yours and free.

---

## Setup (5 minutes)

### 1. Install dependencies (local testing only)
```bash
pip install playwright twilio python-dotenv
playwright install chromium
```

### 2. Get a free Twilio account
- Sign up at twilio.com (free trial gives ~$15 credit, more than enough)
- Get a phone number (free with trial)
- Copy your Account SID and Auth Token from the dashboard

### 3. Edit your search config in `campsite_checker.py`
```python
SEARCH_CONFIG = {
    "park":        "Banff National Park",
    "campground":  "Lake Louise Campground - Soft-sided",
    "checkin":     "2026-08-01",   # your check-in date
    "checkout":    "2026-08-04",   # your check-out date
    "party_size":  2,
}
```

### 4. Test it locally
Create a `.env` file:
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM=+1xxxxxxxxxx
TWILIO_TO=+1xxxxxxxxxx
```
Then run:
```bash
SINGLE_CHECK=true python campsite_checker.py
```

---

## Running 24/7 — Free vs Paid

### ✅ Option 1: GitHub Actions (FREE — recommended)

Your computer stays off. GitHub runs the checker every 5 minutes for free.

1. Push this whole folder to a **public** GitHub repo
   - It must be public for unlimited free minutes (private repos get 2,000 min/month — not enough)
   - The secrets below are stored securely in GitHub, NOT in the code
2. Go to your repo → **Settings → Secrets and variables → Actions**
3. Add these four secrets:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_FROM`
   - `TWILIO_TO`
4. Go to **Actions** tab → enable workflows → done

GitHub runs `.github/workflows/campsite_checker.yml` automatically every 5 minutes. No server, no cost.

---

### 💳 Option 2: Railway (~$1–5 CAD/month)

> ⚠️ **Correction from earlier:** Railway is NOT free. They offer a 30-day trial with $5 credit (no card needed), then charge $1/month minimum on the free plan or $5/month on Hobby. A lightweight Python script costs ~$0.30–0.50/month in resources, so you'd likely stay within the $1/month free plan — but it's not guaranteed to be free forever.

1. Push this folder to GitHub
2. Sign up at railway.app and connect your repo
3. Add your four Twilio variables under **Variables** in the Railway dashboard
4. Deploy — Railway detects the `Dockerfile` and `railway.toml` automatically

The `railway.toml` and `Dockerfile` in this repo handle everything. Railway uses the official Playwright Docker image so Chromium works out of the box.

---

### 💻 Option 3: DigitalOcean VPS (~$6 CAD/month)

Most control, most reliable uptime.

```bash
# SSH into a $6/month droplet, then:
screen -S checker
python campsite_checker.py
# Ctrl+A, D to detach — keeps running after you close SSH
```

---

## How it works

**GitHub Actions mode (`SINGLE_CHECK=true`):**
The workflow runs every 5 minutes, calls the script once, and exits. GitHub handles the scheduling.

**Server mode (Railway / local):**
The script loops forever, checking every ~5 minutes with random jitter to avoid bot detection. If a site opens → Twilio SMS. If checks fail 5 times in a row → warning SMS.

---

## If Parks Canada blocks it

The site may use Cloudflare bot protection. If you're getting repeated failures:

1. Increase the poll interval: set `POLL_INTERVAL_BASE = 600` (10 min)
2. Install stealth plugin: `pip install playwright-stealth` and add `await stealth_async(page)` after `page = await context.new_page()`
3. Check during off-peak hours (3–6 AM MT) when bot detection is less aggressive

---

## File structure

```
campsite_checker.py          # main script
requirements.txt             # Python dependencies
Dockerfile                   # for Railway deployment
railway.toml                 # Railway config
.github/
  workflows/
    campsite_checker.yml     # GitHub Actions workflow (free)
```

---

## Disclaimer

Personal use only. Don't set the poll interval below 3 minutes — hammering Parks Canada's servers is poor etiquette and will get you blocked faster.
