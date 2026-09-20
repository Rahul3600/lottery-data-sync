"""
kerala_predictor.py — Kerala Lottery Advanced Prediction Engine
================================================================
ALGORITHM (v2 — Weighted Recency + Digit Proximity Scoring):

  - Reads last 180 days of Kerala 1st Prize results from Google Sheets
  - Each 6-digit Kerala 1st Prize: 'XX 123456' → last 4 = '3456'
  - Scores each 4-digit ending by:
      * Recency weight : last 7d → ×8, last 14d → ×4, last 30d → ×2, older → ×1
      * Frequency      : +1 per occurrence
      * Day-of-week    : same weekday as today → +2
      * Digit proximity: endings within ±100 of most recent win get +1
  - Returns Top 30 by total score (4-Digit Endings)
  - 6-Digit VIP: for each ending X → X[:2] + X  (confirmed formula)
    with 3 series codes: SB, XC, DF → 90 total VIP numbers

History window: 180 days.
"""

import os
import re
import json
import urllib.request
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter

IST = timezone(timedelta(hours=5, minutes=30))
PRED_TAB   = "Predictions Kerala (4 PM)"
RESULTS_TAB = "Kerala Results"
SERIES     = ["SB", "XC", "DF"]
HISTORY_DAYS = 180


def fetch_gas_data():
    try:
        url = os.environ.get("GAS_WEBHOOK_URL")
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("dynamic_data", {}).get(RESULTS_TAB, [])
        preds = data.get("dynamic_data", {}).get(PRED_TAB, [])
        return results, preds
    except Exception as e:
        print(f"  [WARN] GAS fetch failed: {e}")
        return [], []


# ── Parse and score historical endings ────────────────────────────────────────
def parse_scored_endings(rows, today, weekday_int):
    """
    Returns a Counter of {last4_str: total_score}.
    Also returns most_recent_last4 (string) for proximity scoring.
    """
    cutoff = today - timedelta(days=HISTORY_DAYS)
    scores = Counter()
    most_recent_last4 = None
    most_recent_date  = None

    for row in rows:
        raw_date = str(row.get("date", "") or row.get("Date", ""))
        first    = str(row.get("first_prize", "") or row.get("1st Prize", ""))
        
        if not raw_date or not first or first in ("", "HOLIDAY"):
            continue
        try:
            row_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").replace(tzinfo=IST)
        except ValueError:
            try:
                row_date = datetime.strptime(raw_date[:10], "%d/%m/%Y").replace(tzinfo=IST)
            except ValueError:
                continue
        if row_date < cutoff or row_date >= today:
            continue

        # Extract last 4 digits of all numbers from all prizes
        all_prizes = " ".join([
            first,
            str(row.get("2nd Prize", "") or row.get("second_prize", "")),
            str(row.get("3rd Prize", "") or row.get("third_prize", "")),
            str(row.get("4th Prize", "") or row.get("fourth_prize", "")),
            str(row.get("5th Prize", "") or row.get("fifth_prize", "")),
            str(row.get("6th Prize", "") or row.get("sixth_prize") or row.get("6th_prize", "")),
            str(row.get("7th Prize", "") or row.get("seventh_prize") or row.get("7th_prize", "")),
            str(row.get("8th Prize", "") or row.get("eighth_prize") or row.get("8th_prize", "")),
            str(row.get("9th Prize", "") or row.get("ninth_prize") or row.get("9th_prize", "")),
            str(row.get("Consolidate Prize", "") or row.get("consolidate_prize", ""))
        ])
        
        all_last4s = [n[-4:] for n in re.findall(r'\b\d{4,6}\b', all_prizes) if len(n) >= 4]

        age_days = (today - row_date).days
        # Optimized weights from ML Optimizer
        if age_days <= 7:    rec = 5
        elif age_days <= 14: rec = 4
        elif age_days <= 30: rec = 2
        else:                rec = 1

        same_day = 2 if row_date.weekday() == weekday_int else 0
        
        for n in all_last4s:
            scores[n] += rec + same_day + 1  # +1 base frequency

        # Anchor for digit proximity is still the 1st prize
        last4 = None
        if first and first not in ("HOLIDAY", "N/A"):
            nums6 = re.findall(r'\b\d{6}\b', first)
            if nums6: last4 = nums6[0][-4:]

        # Track most recent result
        if most_recent_date is None or row_date > most_recent_date:
            most_recent_date  = row_date
            most_recent_last4 = last4

    # Digit proximity bonus: endings within ±200 of most recent last4
    if most_recent_last4 and most_recent_last4.isdigit():
        anchor = int(most_recent_last4)
        for num4 in list(scores.keys()):
            if abs(int(num4) - anchor) <= 200:
                scores[num4] += 1 # Proximity bonus = 1

    return scores, most_recent_last4


# ── Build Top 300 endings ──────────────────────────────────────────────────────
def build_top300(scores):
    """
    Returns up to 300 best-scored 4-digit endings.
    Only uses REAL historical data — no dummy padding.
    If fewer than 300 real entries exist, returns what we have.
    """
    top = [num for num, _ in scores.most_common(300)]
    return top


# ── Build 6-Digit VIP numbers ─────────────────────────────────────────────────
def build_vip(top300):
    """
    For each ending X: 6-digit = X[:2] + X (confirmed formula from sample data)
    We will just select the top 30 from the list to create VIP numbers (90 total).
    """
    vip = []
    for ending in top300[:30]:
        six = ending[:2] + ending
        for series in SERIES:
            vip.append(f"{series} {six}")
    return vip


# ── Trust Badge Calculation ───────────────────────────────────────────────────
def calculate_trust_badge(yesterday_pred_str, yesterday_results_dict):
    clean_pred_str = yesterday_pred_str.replace('"', '').replace(' ', '')
    if not clean_pred_str:
        return "0", ""
    
    predicted_4_digits = set(clean_pred_str.split(","))
    
    all_prizes = " ".join([
        str(yesterday_results_dict.get("first_prize", "") or yesterday_results_dict.get("1st Prize", "")),
        str(yesterday_results_dict.get("second_prize", "") or yesterday_results_dict.get("2nd Prize", "")),
        str(yesterday_results_dict.get("third_prize", "") or yesterday_results_dict.get("3rd Prize", "")),
        str(yesterday_results_dict.get("fourth_prize", "") or yesterday_results_dict.get("4th Prize", "")),
        str(yesterday_results_dict.get("fifth_prize", "") or yesterday_results_dict.get("5th Prize", "")),
        str(yesterday_results_dict.get("sixth_prize", "") or yesterday_results_dict.get("6th_prize", "") or yesterday_results_dict.get("6th Prize", "")),
        str(yesterday_results_dict.get("seventh_prize", "") or yesterday_results_dict.get("7th_prize", "") or yesterday_results_dict.get("7th Prize", "")),
        str(yesterday_results_dict.get("eighth_prize", "") or yesterday_results_dict.get("8th_prize", "") or yesterday_results_dict.get("8th Prize", "")),
        str(yesterday_results_dict.get("ninth_prize", "") or yesterday_results_dict.get("9th_prize", "") or yesterday_results_dict.get("9th Prize", "")),
        str(yesterday_results_dict.get("consolidate_prize", "") or yesterday_results_dict.get("Consolidate Prize", ""))
    ])
    
    winning_numbers = set([n[-4:] for n in re.findall(r'\b\d{4,6}\b', all_prizes) if len(n) >= 4])
    matched = predicted_4_digits.intersection(winning_numbers)
    
    if len(matched) == 0:
        return "0", ""
    return str(len(matched)), ", ".join(list(matched))


# ── Send to GAS ───────────────────────────────────────────────────────────────
def send_to_gas(data_dict):
    """Sends the prediction data to the GAS webhook."""
    payload = {"action": "insert", "tab_name": PRED_TAB, "data": data_dict}
    try:
        url = os.environ.get("GAS_WEBHOOK_URL")
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        body = json.dumps(payload).encode("utf-8")
        with urllib.request.urlopen(req, data=body) as f:
            print(f"  GAS: {f.read().decode('utf-8')[:120]}")
    except Exception as e:
        print(f"  [ERROR] {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    url = os.environ.get("GAS_WEBHOOK_URL")
    if not url:
        print("ERROR: GAS_WEBHOOK_URL not set.")
        return

    today       = datetime.now(IST)
    date_str    = today.strftime("%Y-%m-%d")
    day_str     = today.strftime("%A").upper()
    weekday_int = today.weekday()

    print(f"\n[KERALA PREDICTOR v2] {date_str} ({day_str})  |  History: {HISTORY_DAYS} days")

    rows, preds = fetch_gas_data()
    print(f"  Rows fetched: {len(rows)} | Preds fetched: {len(preds)}")

    # Trust Badge Logic
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_pred_row = next((r for r in preds if r.get("Date", "")[:10] == yesterday_str or r.get("date", "")[:10] == yesterday_str), None)
    yesterday_result_row = next((r for r in rows if r.get("Date", "")[:10] == yesterday_str or r.get("date", "")[:10] == yesterday_str), None)
    
    trust_count = "0"
    trust_matched = ""
    if yesterday_pred_row and yesterday_result_row:
        pred_4_str = str(yesterday_pred_row.get("4-Digit Endings (Top 300)", "") or yesterday_pred_row.get("4_digit_endings_top_300", "") or yesterday_pred_row.get("4-Digit Endings", ""))
        trust_count, trust_matched = calculate_trust_badge(pred_4_str, yesterday_result_row)
        print(f"  Trust Badge: {trust_count} matched from yesterday")

    scores, most_recent = parse_scored_endings(rows, today, weekday_int)
    print(f"  Unique endings scored: {len(scores)}")
    print(f"  Most recent 1st prize last4: {most_recent}")

    if not scores:
        print("  [WARN] No historical data available. Cannot generate predictions.")
        return

    top300 = build_top300(scores)
    vip   = build_vip(top300)

    print(f"  Top 300 endings : {len(top300)} generated")
    print(f"  VIP sample     : {vip[:6]}")

    data = {
        "Date":                     date_str,
        "Time":                     "'3:00 PM",   # quote prefix prevents GAS time conversion
        "Day":                      day_str,
        "4-Digit Endings (Top 300)": ", ".join(top300),
        "6-Digit VIP Numbers":      ", ".join(vip),
        "Yesterday Matches":        trust_count,
        "Yesterday Matched Numbers": trust_matched,
    }

    send_to_gas(data)
    print(f"  [DONE] → '{PRED_TAB}'")


if __name__ == "__main__":
    main()
