"""
dear_predictor.py — Dear Lottery Daily Prediction Generator
============================================================
Algorithm (reverse-engineered from sample data):
  - Reads last 90 days of Dear Lottery 5th Prize numbers from Google Sheets
  - Groups all 4-digit prize numbers by their first 2 digits (00xx, 01xx, … 99xx)
  - Picks the TOP 3 most-frequent 4-digit numbers from each group → 300 total (4 Digit Prediction)
  - Generates 5 Digit Prediction: for each 4-digit number, prepend digits 0-9 → 3000 combos,
    then take a strategic subset
  - Generates SUPER VIP PREDICTION: top 15 most-frequent 5-digit combos
  - Middle Matrix: fixed "00"-"99" (constant, same every day)
  - Posts to "Predictions 1:00 PM", "Predictions 6:00 PM", "Predictions 8:00 PM"
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL")
IST = timezone(timedelta(hours=5, minutes=30))

DRAWS = [
    {"time": "1:00 PM", "tab": "Predictions 1:00 PM", "url_part": "1pm"},
    {"time": "6:00 PM", "tab": "Predictions 6:00 PM", "url_part": "6pm"},
    {"time": "8:00 PM", "tab": "Predictions 8:00 PM", "url_part": "8pm"},
]

# ── Fetch historical 5th Prize data from Google Sheet via GAS ──────────────────
def fetch_historical_fifth_prizes(tab_name, days=90):
    """
    Fetches all 4-digit numbers from the '5th Prize' column
    in the specified Results tab, for the last `days` days.
    Returns a flat list of all 4-digit strings.
    """
    try:
        resp = requests.get(GAS_WEBHOOK_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        dynamic = data.get("dynamic_data", {})
        rows = dynamic.get(tab_name, [])
    except Exception as e:
        print(f"  [WARN] Could not fetch from GAS: {e}")
        return []

    cutoff = datetime.now(IST) - timedelta(days=days)
    all_nums = []

    for row in rows:
        date_str = str(row.get("date", "") or row.get("Date", ""))
        fifth    = str(row.get("fifth_prize", "") or row.get("5th Prize", ""))
        if not date_str or not fifth:
            continue
        try:
            row_date = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=IST)
        except ValueError:
            continue
        if row_date < cutoff:
            continue
        nums = re.findall(r'\b\d{4}\b', fifth)
        nums = [n for n in nums if n not in ('2023', '2024', '2025', '2026', '2027')]
        all_nums.extend(nums)

    print(f"  Fetched {len(all_nums)} historical 4-digit numbers from '{tab_name}'")
    return all_nums


# ── Build 4-digit prediction list (300 total) ─────────────────────────────────
def build_four_digit_prediction(historical_nums):
    """
    Groups 4-digit numbers by their first 2 digits (00–99).
    Picks the Top 3 most frequent from each group.
    Returns a list of up to 300 4-digit strings.
    """
    groups = defaultdict(Counter)
    for num in historical_nums:
        prefix = num[:2]
        groups[prefix][num] += 1

    result = []
    for prefix in [f"{i:02d}" for i in range(100)]:
        top3 = [n for n, _ in groups[prefix].most_common(3)]
        # Pad with zero-filled placeholders if not enough data
        while len(top3) < 3:
            placeholder = f"{prefix}00"
            if placeholder not in top3:
                top3.append(placeholder)
            else:
                top3.append(f"{prefix}{len(top3):02d}")
        result.extend(top3[:3])

    return result  # exactly 300


# ── Build 5-digit prediction list ─────────────────────────────────────────────
def build_five_digit_prediction(four_digit_list, historical_nums):
    """
    For each of the 300 4-digit predictions, generates 5-digit numbers
    by using the historically most-common leading digit for each 4-digit number.
    Then returns ~300 five-digit numbers (one "best" per 4-digit entry).
    """
    # Build frequency of full 5-digit combos from history
    # We approximate: for each 4-digit ending, find which leading digit (0-9)
    # would complete it most often based on pattern of last digits in history
    freq_5 = Counter()
    for num in historical_nums:
        # Approximate: the number itself as a 4-digit — prepend all 0-9
        for lead in '0123456789':
            freq_5[lead + num] += 1

    result = []
    seen_five = set()
    for four in four_digit_list:
        # Pick the leading digit whose corresponding 5-digit is highest frequency
        best = None
        best_score = -1
        for lead in '0123456789':
            candidate = lead + four
            score = freq_5[candidate]
            if score > best_score:
                best_score = score
                best = candidate
        if best and best not in seen_five:
            result.append(best)
            seen_five.add(best)
        elif best:
            # Try next best lead digit
            for lead in '9876543210':
                alt = lead + four
                if alt not in seen_five:
                    result.append(alt)
                    seen_five.add(alt)
                    break

    return result[:300]


# ── Build SUPER VIP (top 15) ──────────────────────────────────────────────────
def build_super_vip(five_digit_list, four_digit_list):
    """
    Returns top 15 five-digit predictions as the SUPER VIP picks.
    Selected by frequency of their last-4-digits appearing in historical 5th prizes.
    """
    freq_4 = Counter()
    for four in four_digit_list:
        freq_4[four] += 1

    scored = [(five, freq_4.get(five[-4:], 0)) for five in five_digit_list]
    scored.sort(key=lambda x: -x[1])
    top15 = [x[0] for x in scored[:15]]
    return top15


# ── Middle Matrix (constant) ──────────────────────────────────────────────────
def build_middle_matrix():
    return ", ".join([f'"{i:02d}"' for i in range(100)])


# ── Format as quoted CSV string ───────────────────────────────────────────────
def fmt(lst):
    return ", ".join([f'"{x}"' for x in lst])


# ── Send to GAS ───────────────────────────────────────────────────────────────
def send_to_gas(tab_name, data_dict):
    payload = {"action": "insert", "tab_name": tab_name, "data": data_dict}
    try:
        resp = requests.post(GAS_WEBHOOK_URL, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=20)
        print(f"  GAS response: {resp.status_code} — {resp.text[:120]}")
    except Exception as e:
        print(f"  [ERROR] Failed to send to GAS: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not GAS_WEBHOOK_URL:
        print("ERROR: GAS_WEBHOOK_URL not set.")
        return

    today = datetime.now(IST)
    date_str  = today.strftime("%Y-%m-%d")
    day_str   = today.strftime("%A").upper()

    # Determine which draw to run for (mirrors lottery_fetcher.py logic)
    current_hour  = today.hour
    event_name    = os.environ.get("EVENT_NAME", "workflow_dispatch")
    schedule_cron = os.environ.get("SCHEDULE_CRON", "")

    target_draw = None
    if event_name == "schedule" and schedule_cron:
        if "7"  in schedule_cron: target_draw = DRAWS[0]   # 1 PM
        elif "12" in schedule_cron: target_draw = DRAWS[1] # 6 PM
        elif "14" in schedule_cron: target_draw = DRAWS[2] # 8 PM

    if not target_draw:
        # Manual trigger: run for the most-recent past draw
        mapping = {13: DRAWS[0], 18: DRAWS[1], 20: DRAWS[2]}
        past = [d for d in DRAWS if d["url_part"] in
                (["1pm"] if current_hour >= 13 else []) +
                (["6pm"] if current_hour >= 18 else []) +
                (["8pm"] if current_hour >= 20 else [])]
        if not past:
            past = [DRAWS[0]]  # fallback
        target_draw = past[-1]

    draw = target_draw
    results_tab = f"Results {draw['time']}"
    pred_tab    = draw["tab"]

    print(f"\n[DEAR PREDICTOR] Generating predictions for: {draw['time']} — {date_str}")
    print(f"  Reading historical data from: '{results_tab}'")

    historical = fetch_historical_fifth_prizes(results_tab, days=90)

    if len(historical) < 30:
        print(f"  [WARN] Not enough historical data ({len(historical)} numbers). Need at least 30.")
        print(f"  Generating with available data...")

    four_pred  = build_four_digit_prediction(historical)
    five_pred  = build_five_digit_prediction(four_pred, historical)
    super_vip  = build_super_vip(five_pred, four_pred)
    matrix     = build_middle_matrix()

    print(f"  4-Digit Prediction: {len(four_pred)} numbers")
    print(f"  5-Digit Prediction: {len(five_pred)} numbers")
    print(f"  SUPER VIP: {super_vip}")

    data = {
        "Date":                  date_str,
        "Time":                  f"'{draw['time']}",
        "Day":                   day_str,
        "Middle Matrix":         matrix,
        "5 Digit Prediction":    fmt(five_pred),
        "4 Digit Prediction":    fmt(four_pred),
        "SUPER VIP PREDICTION":  fmt(super_vip),
    }

    send_to_gas(pred_tab, data)
    print(f"  [DONE] Predictions posted to '{pred_tab}'")


if __name__ == "__main__":
    main()

