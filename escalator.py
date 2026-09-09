"""
Zoho Books Late-Payment Escalator
----------------------------------
Run this once daily (via Task Scheduler). It checks all overdue invoices
in Zoho Books, and for each one that has newly crossed a 7/15/30-day
overdue threshold, sends an escalating WhatsApp reminder via WATI.

Each invoice's last-sent stage is tracked in escalation_state.json so
the same reminder is never sent twice.
"""

import os
import json
import time
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

# ---- Zoho config ----
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ZOHO_ORG_ID = os.getenv("ZOHO_ORG_ID")
ZOHO_API_DOMAIN = "https://www.zohoapis.in"
ZOHO_ACCOUNTS_DOMAIN = "https://accounts.zoho.in"

# ---- WATI config ----
WATI_TENANT_ID = os.getenv("WATI_TENANT_ID")
WATI_ACCESS_TOKEN = os.getenv("WATI_ACCESS_TOKEN")
WATI_BASE_URL = f"https://live-mt-server.wati.io/{WATI_TENANT_ID}"

STATE_FILE = "escalation_state.json"

# Escalation stages: (minimum days overdue, stage number)
# A client only gets a new message when one of their invoices crosses
# into a new stage for the first time — the message itself is built
# dynamically in run(), listing all their currently overdue invoices.
STAGES = [
    (30, 3),
    (15, 2),
    (7, 1),
]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_zoho_access_token():
    resp = requests.post(
        f"{ZOHO_ACCOUNTS_DOMAIN}/oauth/v2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "refresh_token": ZOHO_REFRESH_TOKEN,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_overdue_invoices(access_token):
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    resp = requests.get(
        f"{ZOHO_API_DOMAIN}/books/v3/invoices",
        headers=headers,
        params={"organization_id": ZOHO_ORG_ID, "status": "overdue"},
    )
    resp.raise_for_status()
    return resp.json().get("invoices", [])


def get_customer_phone(access_token, customer_id):
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    resp = requests.get(
        f"{ZOHO_API_DOMAIN}/books/v3/contacts/{customer_id}",
        headers=headers,
        params={"organization_id": ZOHO_ORG_ID},
    )
    if resp.status_code != 200:
        return None
    contact = resp.json().get("contact", {})
    return contact.get("mobile") or contact.get("phone")


def send_whatsapp_message(whatsapp_number, message_text):
    url = f"{WATI_BASE_URL}/api/v1/sendSessionMessage/{whatsapp_number}"
    headers = {"Authorization": f"Bearer {WATI_ACCESS_TOKEN}"}
    params = {"messageText": message_text}
    requests.post(url, headers=headers, params=params)


def days_overdue(due_date_str):
    due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
    return (datetime.now() - due_date).days


def run():
    print(f"[{datetime.now()}] Starting overdue invoice check...")

    access_token = get_zoho_access_token()
    invoices = get_overdue_invoices(access_token)
    state = load_state()

    print(f"Found {len(invoices)} overdue invoice(s).")

    # Group all overdue invoices by customer, so each client gets ONE
    # consolidated message instead of one message per invoice.
    by_customer = {}
    for invoice in invoices:
        customer_id = invoice["customer_id"]
        by_customer.setdefault(customer_id, []).append(invoice)

    print(f"Grouped into {len(by_customer)} unique customer(s). Processing...")
    phone_cache = {}
    total_customers = len(by_customer)

    for idx, (customer_id, customer_invoices) in enumerate(by_customer.items(), start=1):
        customer_name = customer_invoices[0]["customer_name"]
        print(f"  [{idx}/{total_customers}] Checking {customer_name}...")

        # For each invoice, figure out its overdue days and whether it has
        # newly crossed a threshold since the last run.
        needs_update = False
        invoice_lines = []
        total_balance = 0.0

        for invoice in customer_invoices:
            invoice_id = invoice["invoice_id"]
            invoice_number = invoice["invoice_number"]
            due_date = invoice["due_date"]
            balance = float(invoice["balance"])
            total_balance += balance

            overdue_days = days_overdue(due_date)
            current_stage = state.get(invoice_id, {}).get("stage", 0)

            target_stage = current_stage
            for min_days, stage_num in STAGES:
                if overdue_days >= min_days and stage_num > current_stage:
                    target_stage = stage_num
                    break

            if target_stage > current_stage:
                needs_update = True
                state[invoice_id] = {
                    "stage": target_stage,
                    "last_sent": datetime.now().isoformat(),
                    "invoice_number": invoice_number,
                    "customer_name": customer_name,
                }

            # Include every currently-overdue invoice in the message body,
            # not just the ones that just crossed a new threshold, so the
            # client sees their full picture in one message.
            invoice_lines.append(f"- {invoice_number}: ₹{balance:.2f} ({overdue_days} days overdue)")

        # Only actually send a message if at least one invoice for this
        # customer crossed a new threshold this run.
        if needs_update:
            if customer_id in phone_cache:
                phone = phone_cache[customer_id]
            else:
                phone = get_customer_phone(access_token, customer_id)
                phone_cache[customer_id] = phone
                time.sleep(0.5)  # small delay to avoid hitting Zoho's rate limit

            if not phone:
                print(f"    Skipping {customer_name} — no phone number found")
                continue

            message = (
                f"Dear {customer_name}, you have {len(customer_invoices)} overdue invoice(s) "
                f"totaling ₹{total_balance:.2f}:\n\n"
                + "\n".join(invoice_lines)
                + "\n\nPlease arrange payment at the earliest, or contact our office to discuss."
            )
            send_whatsapp_message(phone, message)
            print(f"    Sent consolidated reminder to {customer_name} ({len(customer_invoices)} invoice(s), ₹{total_balance:.2f} total)")
        else:
            print(f"    No new reminder needed for {customer_name}")

        # Save progress after every customer, so if the script is stopped
        # partway through, nothing already-processed gets re-sent next time.
        save_state(state)

    print(f"[{datetime.now()}] Done.")


if __name__ == "__main__":
    run()
