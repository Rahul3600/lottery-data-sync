"""
kerala_predictor.py — Kerala Lottery Daily Prediction Generator
================================================================
Algorithm (reverse-engineered from sample data):
  - Reads last 90 days of Kerala 1st Prize results from Google Sheets
  - Finds the TOP 30 most-frequent 4-digit endings from the 6-digit 1st Prize numbers
  - Builds 6-Digit VIP Numbers: for each ending X, VIP = X[:2] + X
    Then generates 3 series (SB, XC, DF) for each → 90 VIP numbers total
  - Posts to "Predictions Kerala (4 PM)"
"""

import os
import re
import json
import urllib.request
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter

GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL")
IST = timezone(timedelta(hours=5, minutes=30))
PRED_TAB = "Predictions Kerala (4 PM)"
RESULTS_TAB = "Kerala Results"
SERIES = ["SB", "XC", "DF"]


# ── Fetch historical 1st Prize endings from GAS ───────────────────────────────
def fetch_historical_first_prize_endings(days=90):
    """
    Reads the 'Kerala Results' tab from GAS and extracts the last 4 digits
    of each 1st Prize entry (format: 'XX 123456' → last4 = '3456').
    Returns a list of 4-digit strings.
    """
    try:
        resp = requests.get(GAS_WEBHOOK_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        dynamic = data.get("dynamic_data", {})
        rows = dynamic.get(RESULTS_TAB, [])
    except Exception as e:
        print(f"  [WARN] Could not fetch from GAS: {e}")
        return []

    cutoff = datetime.now(IST) - timedelta(days=days)
    last4_list = []

    for row in rows:
        date_str = str(row.get("date", "") or row.get("Date", ""))
        first    = str(row.get("first_prize", "") or row.get("1st Prize", ""))
        if not date_str or not first or first in ("", "HOLIDAY"):
            continue
        try:
            row_date = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=IST)
        except ValueError:
            continue
        if row_date < cutoff:
            continue
        # Kerala 1st Prize format: "XX 123456" — take last 4 digits
        nums = re.findall(r'\d{6}', first)
        if nums:
            last4 = nums[0][-4:]
            last4_list.append(last4)

    print(f"  Fetched {len(last4_list)} historical Kerala 1st Prize endings")
    return last4_list


# ── Build Top 30 4-digit endings ──────────────────────────────────────────────
def build_top30_endings(last4_list):
    """
    Returns the 30 most-frequent 4-digit endings.
    If < 30 unique, pads with common digit combos.
    """
    freq = Counter(last4_list)
    top30 = [num for num, _ in freq.most_common(30)]

    # Pad with zeros if insufficient data
    i = 0
    while len(top30) < 30:
        candidate = f"{i:04d}"
        if candidate not in top30:
            top30.append(candidate)
        i += 1

    return top30[:30]


# ── Build 6-digit VIP numbers ─────────────────────────────────────────────────
def build_vip_numbers(top30):
    """
    For each 4-digit ending X: 6-digit = X[:2] + X
    Then generate 3 entries: SB XXXXXX, XC XXXXXX, DF XXXXXX
    Total = 30 × 3 = 90 VIP numbers.
    """
    vip_list = []
    for ending in top30:
        six_digit = ending[:2] + ending
        for series in SERIES:
            vip_list.append(f"{series} {six_digit}")
    return vip_list


# ── Format as quoted CSV string ───────────────────────────────────────────────
def fmt_list(lst):
    return ", ".join(lst)


# ── Send to GAS ───────────────────────────────────────────────────────────────
def send_to_gas(data_dict):
    payload = {"action": "insert", "tab_name": PRED_TAB, "data": data_dict}
    try:
        req = urllib.request.Request(GAS_WEBHOOK_URL, method="POST")
        req.add_header("Content-Type", "application/json")
        body = json.dumps(payload).encode("utf-8")
        with urllib.request.urlopen(req, data=body) as f:
            print(f"  GAS response: {f.read().decode('utf-8')[:120]}")
    except Exception as e:
        print(f"  [ERROR] Failed to send to GAS: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not GAS_WEBHOOK_URL:
        print("ERROR: GAS_WEBHOOK_URL not set.")
        return

    today    = datetime.now(IST)
    date_str = today.strftime("%d/%m/%Y")   # Kerala format: DD/MM/YYYY
    day_str  = today.strftime("%A").upper()

    print(f"\n[KERALA PREDICTOR] Generating predictions for {date_str}")

    last4_list = fetch_historical_first_prize_endings(days=90)

    if len(last4_list) < 10:
        print(f"  [WARN] Not enough Kerala historical data ({len(last4_list)}). Need at least 10.")

    top30  = build_top30_endings(last4_list)
    vip    = build_vip_numbers(top30)

    print(f"  Top 30 Endings: {top30}")
    print(f"  VIP sample: {vip[:6]}")

    data = {
        "Date":                     date_str,
        "Time":                     "4 PM",
        "Day":                      day_str,
        "4-Digit Endings (Top 30)": fmt_list(top30),
        "6-Digit VIP Numbers":      fmt_list(vip),
    }

    send_to_gas(data)
    print(f"  [DONE] Predictions posted to '{PRED_TAB}'")


if __name__ == "__main__":
    main()
