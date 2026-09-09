# Zoho Books Late-Payment Escalator

A daily script that checks all overdue invoices in Zoho Books and sends escalating WhatsApp reminders via WATI — consolidated per client, with multi-stage tracking so nobody gets the same reminder twice.

Built by **Aadhil Mohamed**.

---

## How it works

```
Runs once daily (Task Scheduler)
            │
            ▼
   Fetch all overdue invoices from Zoho Books
            │
            ▼
   Group invoices by customer
            │
            ▼
   For each customer, check if any invoice has newly
   crossed a 7 / 15 / 30-day overdue threshold
            │
            ▼
   If yes: send ONE consolidated WhatsApp message listing
   all their overdue invoices and the total amount due
            │
            ▼
   Record the new stage per invoice, so the same
   reminder is never sent twice
```

If a client has 3 overdue invoices, they get **one** message listing all 3 — not three separate pings.

---

## Prerequisites

- Python 3.10+
- A Zoho Books account (India region — `.in`)
- A [WATI](https://www.wati.io/) account with a scoped access token (see the [WATI Doc Collector](https://github.com/mr-aadheera/wati-doc-collector) repo for notes on getting a token with the right permissions)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/mr-aadheera/zoho-payment-escalator.git
cd zoho-payment-escalator
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Create a Zoho self-client

1. Go to [api-console.zoho.in](https://api-console.zoho.in) → **Add Client** → **Self Client**.
2. Copy the **Client ID** and **Client Secret**.
3. In the **Generate Code** tab, enter scope:
   ```
   ZohoBooks.invoices.READ,ZohoBooks.contacts.READ
   ```
4. Generate a code (valid for a few minutes only).

### 3. Exchange the code for a permanent refresh token

Run immediately after generating the code:
```bash
curl -X POST "https://accounts.zoho.in/oauth/v2/token" -d "grant_type=authorization_code" -d "client_id=YOUR_CLIENT_ID" -d "client_secret=YOUR_CLIENT_SECRET" -d "redirect_uri=https://www.zoho.in" -d "code=YOUR_AUTH_CODE"
```
Save the `refresh_token` from the response — this doesn't expire and is what the script actually uses going forward.

### 4. Get your Zoho Books Organization ID

Found in the URL while inside Zoho Books: `books.zoho.in/app/<ORG_ID>#/...`

### 5. Configure your secrets

```bash
copy .env.example .env
```
Fill in `.env`:
```
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
ZOHO_ORG_ID=...
WATI_TENANT_ID=...
WATI_ACCESS_TOKEN=...
```

### 6. Run it

```bash
python escalator.py
```

First run may take a few minutes if you have many overdue invoices, since each unique customer needs a phone-number lookup. Progress is printed as it goes, and state is saved after every customer — safe to stop and resume without duplicate sends.

---

## Automating it (Windows Task Scheduler)

A ready-made script, `run_zoho_escalator.bat`, is included — it activates the virtual environment, runs `escalator.py` once, and logs all output to `escalator_log.txt` in the project folder (so you can check what happened later without watching it live).

Before using it, open `run_zoho_escalator.bat` and update the `PROJECT_DIR` line to match wherever your working copy actually lives (the folder containing your real `.env` and `venv`, not just a copy meant for GitHub).

1. Open **Task Scheduler** → **Create Task**.
2. **General tab**: name it (e.g. "Zoho Payment Escalator"), leave **"Run only when user is logged on"** selected — this avoids needing to enter your Windows password.
3. **Triggers tab**: New → **Daily**, pick a time (e.g. 10:00 AM) → OK.
4. **Actions tab**: New → **Start a program** → Browse to `run_zoho_escalator.bat` → OK.
5. **Conditions tab**: uncheck "Start the task only if the computer is on AC power" if this runs on a laptop.
6. Save.

This is a **daily, one-shot job** — it runs once, does its work, and exits. It should not be set to run continuously or trigger "At log on," since re-running it every time you log in could mean multiple runs per day. A single daily trigger is enough; the escalation state file already prevents duplicate messages even if you also run it manually in between scheduled runs.

Test it manually first by double-clicking `run_zoho_escalator.bat` and checking `escalator_log.txt` for the expected output before relying on the scheduled trigger.

---

## Customizing the escalation stages

Edit the `STAGES` list in `escalator.py`:
```python
STAGES = [
    (30, 3),
    (15, 2),
    (7, 1),
]
```
Each tuple is `(minimum days overdue, stage number)`. Add, remove, or adjust thresholds as needed — the message text itself is built dynamically in `run()`, listing every currently overdue invoice for that client.

---

## Security

- `.env` is excluded via `.gitignore` — never commit real credentials.
- `escalation_state.json` (which contains real client names and invoice numbers) is also excluded.
- If any credential is accidentally exposed, rotate it immediately — Zoho self-client secrets can be regenerated at api-console.zoho.in, WATI tokens from its dashboard.

---

## Tech Stack

- Python 3
- Zoho Books API (OAuth2 refresh-token flow)
- WATI API for WhatsApp messaging

## Author

**Aadhil Mohamed**

## License

MIT
