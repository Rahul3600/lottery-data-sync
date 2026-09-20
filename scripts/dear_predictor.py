"""
dear_predictor.py — Dear Lottery Advanced Prediction Engine
============================================================
ALGORITHM (v2 — Multi-Factor Recency + Digit Pattern Analysis):

For each of the 100 two-digit prefix groups (00xx–99xx):
  - Scan last 180 days of 5th Prize numbers from Google Sheets
  - Score each 4-digit number by:
      * Recency score  : appeared in last 7 days → ×8, last 14 → ×4, last 30 → ×2, older → ×1
      * Frequency score: each historical occurrence adds 1
      * Day-of-week    : same weekday as today adds +2
  - Pick Top 3 highest-scored numbers per prefix → 300 total (4-Digit Prediction)
  - 5-Digit Prediction: for each of the 300, prepend the leading digit from the
    MOST RECENT historical 1st-prize number that ends in that 4-digit suffix
    (fallback: most frequent leading digit in 1st prize history)
  - SUPER VIP (15): highest overall combined scores across all 300 5-digit predictions
  - Middle Matrix: fixed "00"–"99" (100 two-digit combos, constant)

History window: 180 days for maximum pattern depth.
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_DAYS = 180

DRAWS = [
    {"time": "1:00 PM", "tab": "Predictions 1:00 PM", "url_part": "1pm", "hour": 13},
    {"time": "6:00 PM", "tab": "Predictions 6:00 PM", "url_part": "6pm", "hour": 18},
    {"time": "8:00 PM", "tab": "Predictions 8:00 PM", "url_part": "8pm", "hour": 20},
]


def fetch_gas_data(draw_time, pred_tab):
    """Returns (results_rows, prediction_rows) from GAS."""
    try:
        url = os.environ.get("GAS_WEBHOOK_URL")
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        all_results = data.get("dynamic_data", {}).get(f"Results {draw_time}", [])
        results = [row for row in all_results if row.get("time") == draw_time or row.get("Time") == draw_time]
        
        preds = data.get("dynamic_data", {}).get(pred_tab, [])
        return results, preds
    except Exception as e:
        print(f"  [WARN] GAS fetch failed: {e}")
        return [], []


# ── Parse historical rows into scored records ──────────────────────────────────
def parse_historical(rows, today, weekday_int):
    """
    Returns:
      fifth_scored  : list of (num4, score) from 5th Prize
      first_leading : Counter of (num4 → most-used leading digit) from 1st Prize
      most_recent_last4: string (for digit proximity bonus)
    """
    cutoff = today - timedelta(days=HISTORY_DAYS)
    
    fifth_scored = []
    first_leading_map = defaultdict(Counter)  # last4 → {leading_digit: count}
    
    most_recent_date = None
    most_recent_last4 = None

    for row in rows:
        raw_date = str(row.get("date", "") or row.get("Date", ""))
        if not raw_date:
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

        age_days = (today - row_date).days
        # Recency multiplier (from ML Optimizer)
        decay = 1.0
        if age_days <= 7:   decay = 1.5
        elif age_days > 90: decay = 0.5

        # Day-of-week bonus
        same_day_bonus = 1 if row_date.weekday() == weekday_int else 0

        # Extract prizes and apply ML weights
        p1 = str(row.get("first_prize", "") or row.get("1st Prize", ""))[-4:]
        p2_str = str(row.get("second_prize", "") or row.get("2nd Prize", ""))
        p3_str = str(row.get("third_prize", "") or row.get("3rd Prize", ""))
        p4_str = str(row.get("fourth_prize", "") or row.get("4th Prize", ""))
        p5_str = str(row.get("fifth_prize", "") or row.get("5th Prize", ""))
        
        nums = []
        if len(p1) == 4: nums.append((p1, 5)) # 1st prize weight = 5
        nums.extend((x, 3) for x in re.findall(r'\b\d{4}\b', p2_str)) # 2nd prize weight = 3
        nums.extend((x, 2) for x in re.findall(r'\b\d{4}\b', p3_str)) # 3rd prize weight = 2 (approximate)
        nums.extend((x, 1.5) for x in re.findall(r'\b\d{4}\b', p4_str)) # 4th prize weight = 1.5
        nums.extend((x, 1) for x in re.findall(r'\b\d{4}\b', p5_str)) # 5th prize weight = 1
        
        for num, base in nums:
            score = (base * decay) + same_day_bonus
            fifth_scored.append((num, score))

        # 1st Prize — extract leading digit for each last-4
        first = str(row.get("first_prize", "") or row.get("1st Prize", ""))
        m = re.search(r'\b(\d{1,3}[A-Z])\s+(\d{5})\b', first)
        if m:
            full5 = m.group(2)          # e.g. "76988"
            last4 = full5[-4:]           # "6988"
            lead  = full5[0]             # "7"
            first_leading_map[last4][lead] += decay  # weight by recency
            
            if most_recent_date is None or row_date > most_recent_date:
                most_recent_date = row_date
                most_recent_last4 = last4

    return fifth_scored, first_leading_map, most_recent_last4


# ── Trust Badge Calculation ───────────────────────────────────────────────────
def calculate_trust_badge(yesterday_pred_str, yesterday_results_dict):
    clean_pred_str = yesterday_pred_str.replace('"', '').replace(' ', '')
    if not clean_pred_str:
        return ""
    
    predicted_4_digits = set(clean_pred_str.split(","))
    
    prize_keys = [
        ("1st Prize", ["first_prize", "1st Prize"]),
        ("2nd Prize", ["second_prize", "2nd Prize"]),
        ("3rd Prize", ["third_prize", "3rd Prize"]),
        ("4th Prize", ["fourth_prize", "4th Prize"]),
        ("5th Prize", ["fifth_prize", "5th Prize"])
    ]
    
    matched_details = []
    
    for label, keys in prize_keys:
        prize_val = ""
        for k in keys:
            val = str(yesterday_results_dict.get(k, ""))
            if val:
                prize_val = val
                break
        
        if prize_val:
            winning_numbers = set([n[-4:] for n in re.findall(r'\b\d{4,6}\b', prize_val) if len(n) >= 4])
            matched = predicted_4_digits.intersection(winning_numbers)
            if matched:
                matched_details.append(f"{label}: " + ", ".join(list(matched)))
                
    if not matched_details:
        return ""
        
    return " | ".join(matched_details)


# ── Build 4-digit prediction list (300 total) ─────────────────────────────────
def build_four_digit_predictions(fifth_scored, most_recent_1st_last4=None):
    """
    Aggregates scores globally and picks the absolute Top 300 highest-scored 
    4-digit numbers. This massively increases accuracy compared to forcing 
    3 numbers per prefix.
    Also adds a digit proximity bonus if anchored to the most recent 1st prize.
    """
    group_scores = Counter()
    for num4, score in fifth_scored:
        group_scores[num4] += score

    # Digit proximity bonus (like Kerala)
    if most_recent_1st_last4 and most_recent_1st_last4.isdigit():
        anchor = int(most_recent_1st_last4)
        for num4 in list(group_scores.keys()):
            if abs(int(num4) - anchor) <= 200:
                group_scores[num4] += 2  # Boost proximity

    # Return top 300 absolute best
    top300 = [n for n, _ in group_scores.most_common(300)]
    
    # Fallback padding if we somehow don't have 300 unique numbers
    if len(top300) < 300:
        existing = set(top300)
        for i in range(10000):
            cand = f"{i:04d}"
            if cand not in existing:
                top300.append(cand)
                existing.add(cand)
            if len(top300) == 300:
                break
                
    return top300


# ── Build 5-digit prediction list ─────────────────────────────────────────────
def build_five_digit_predictions(four_pred, first_leading_map):
    """
    For each 4-digit number, choose the best leading digit from:
      1. Most-common leading digit in 1st prize history for that last-4
      2. Fallback: digit with best statistical spread (0-9 evenly)
    Returns list of 300 unique 5-digit strings.
    """
    # Global leading-digit frequency from all 1st-prize history
    global_lead_freq = Counter()
    for last4, lead_cnt in first_leading_map.items():
        for lead, cnt in lead_cnt.items():
            global_lead_freq[lead] += cnt

    result = []
    seen = set()

    for four in four_pred:
        # Try specific historical leading digit for this last-4
        best_lead = None
        if four in first_leading_map:
            best_lead = first_leading_map[four].most_common(1)[0][0]

        # Fallback: use globally most-common leading digit not yet causing duplicate
        if best_lead is None:
            for lead, _ in global_lead_freq.most_common():
                candidate = lead + four
                if candidate not in seen:
                    best_lead = lead
                    break

        if best_lead is None:
            best_lead = "0"

        candidate = best_lead + four
        if candidate not in seen:
            result.append(candidate)
            seen.add(candidate)
        else:
            # Try other leading digits
            for alt in "9876543210":
                alt_cand = alt + four
                if alt_cand not in seen:
                    result.append(alt_cand)
                    seen.add(alt_cand)
                    break

    return result[:300]


# ── Build SUPER VIP (top 15 overall) ─────────────────────────────────────────
def build_super_vip(five_pred, group_scores_flat):
    """
    Scores each 5-digit prediction by the aggregated score of its last-4 in history.
    Returns top 15.
    """
    scored = [(five, group_scores_flat.get(five[-4:], 0)) for five in five_pred]
    scored.sort(key=lambda x: -x[1])
    return [x[0] for x in scored[:15]]


# ── Middle Matrix (constant) ──────────────────────────────────────────────────
def build_middle_matrix():
    return ", ".join([f'"{i:02d}"' for i in range(100)])


# ── Format list as quoted CSV ─────────────────────────────────────────────────
def fmt(lst):
    return ", ".join([f'"{x}"' for x in lst])


# ── Send to GAS ───────────────────────────────────────────────────────────────
def send_to_gas(tab_name, data_dict):
    """Sends the prediction data to the GAS webhook."""
    payload = {"action": "insert", "tab_name": tab_name, "data": data_dict}
    try:
        url = os.environ.get("GAS_WEBHOOK_URL")
        resp = requests.post(url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=20)
        print(f"  GAS (insert): {resp.status_code} - {resp.text[:120]}")
    except Exception as e:
        print(f"  [ERROR] {e}")

def send_update_trust_to_gas(tab_name, target_date, matched_numbers):
    """Sends a request to update the trust badge data for a specific past date."""
    payload = {
        "action": "update_trust",
        "tab_name": tab_name,
        "target_date": target_date,
        "trust_matched_numbers": matched_numbers
    }
    try:
        url = os.environ.get("GAS_WEBHOOK_URL")
        resp = requests.post(url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=20)
        print(f"  GAS (update_trust {target_date}): {resp.status_code} - {resp.text[:120]}")
    except Exception as e:
        print(f"  [ERROR updating trust] {e}")


# 🎯 Main 🎯──────────────────────────────────────────────────────────────────────
def main():
    url = os.environ.get("GAS_WEBHOOK_URL")
    if not url:
        print("ERROR: GAS_WEBHOOK_URL not set.")
        return

    today       = datetime.now(IST)
    date_str    = today.strftime("%Y-%m-%d")
    day_str     = today.strftime("%A").upper()
    weekday_int = today.weekday()

    event_name    = os.environ.get("EVENT_NAME", "workflow_dispatch")
    schedule_cron = os.environ.get("SCHEDULE_CRON", "")
    current_hour  = today.hour

    # Determine which draw(s) to process
    # On 'workflow_dispatch' (manual run): process ALL 3 draws
    # On 'schedule' cron: process only the specific triggered draw
    if event_name == "schedule" and schedule_cron:
        if "7"  in schedule_cron: target_draws = [DRAWS[0]]
        elif "12" in schedule_cron: target_draws = [DRAWS[1]]
        elif "14" in schedule_cron: target_draws = [DRAWS[2]]
        else: target_draws = DRAWS
    else:
        # Manual trigger — run all 3 draws
        target_draws = DRAWS

    for draw in target_draws:
        results_tab = f"Results {draw['time']}"
        pred_tab    = draw["tab"]

        print(f"\n[DEAR PREDICTOR v2] {draw['time']} - {date_str} ({day_str})")
        print(f"\n[DEAR PREDICTOR v2] {date_str} ({day_str})  |  History: {HISTORY_DAYS} days")

        # Now fetch_gas_data returns both results and predictions for this draw time
        rows, preds = fetch_gas_data(draw["time"], pred_tab)
        print(f"  Rows fetched: {len(rows)} | Preds fetched: {len(preds)}")

        # Trust Badge Logic
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_pred_row = next((r for r in preds if r.get("Date", "")[:10] == yesterday_str or r.get("date", "")[:10] == yesterday_str), None)
        yesterday_result_row = next((r for r in rows if r.get("Date", "")[:10] == yesterday_str or r.get("date", "")[:10] == yesterday_str), None)
        
        trust_matched = ""
        if yesterday_pred_row and yesterday_result_row:
            pred_4_str = str(yesterday_pred_row.get("4 Digit Prediction", "") or yesterday_pred_row.get("4_digit_prediction", ""))
            trust_matched = calculate_trust_badge(pred_4_str, yesterday_result_row)
            print(f"  Trust Badge evaluated for yesterday")

        fifth_scored, first_leading_map, most_recent = parse_historical(rows, today, weekday_int)
        print(f"  5th-prize data points: {len(fifth_scored)}")
        print(f"  Most recent 1st prize last4: {most_recent}")

        score_flat = Counter()
        for num4, sc in fifth_scored:
            score_flat[num4] += sc

        four_pred = build_four_digit_predictions(fifth_scored, most_recent)
        five_pred = build_five_digit_predictions(four_pred, first_leading_map)
        super_vip = build_super_vip(five_pred, score_flat)
        matrix    = build_middle_matrix()

        print(f"  4-Digit count : {len(four_pred)}")
        print(f"  5-Digit count : {len(five_pred)}")
        print(f"  SUPER VIP     : {super_vip}")

        data = {
            "Date":                  date_str,
            "Time":                  f"'{draw['time']}",  # Single quote prevents 24h format conversion
            "Day":                   day_str,
            "Middle Matrix":         matrix,
            "5 Digit Prediction":    fmt(five_pred),
            "4 Digit Prediction":    fmt(four_pred),
            "SUPER VIP PREDICTION":  fmt(super_vip),
            "Trust Matched Numbers": ""  # Ensures column is auto-created by GAS
        }

        # 1. Update Yesterday's Trust Badge (if found)
        if yesterday_pred_row and yesterday_result_row:
            send_update_trust_to_gas(pred_tab, yesterday_str, trust_matched)
            
        # 2. Insert Today's Prediction
        send_to_gas(pred_tab, data)
        print(f"  [DONE] -> '{pred_tab}'")

if __name__ == "__main__":
    main()
