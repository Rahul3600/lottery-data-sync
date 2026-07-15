import os
import json
import requests
from datetime import datetime

import io
from PIL import Image
import fitz  # PyMuPDF
import pytesseract
import re
from datetime import datetime, timedelta, timezone

# URL of your deployed Google Apps Script Web App
GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL")

def send_to_gas(tab_name, data_dict):
    """
    Sends the data to Google Apps Script.
    The Apps script will automatically create the tab and any missing columns.
    """
    payload = {
        "action": "insert",
        "tab_name": tab_name,
        "data": data_dict
    }
    
    print(f"Sending data to tab: {tab_name}...")
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(GAS_WEBHOOK_URL, json=payload, headers=headers)
        print(f"Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending data to GAS: {e}")

def process_lottery_image(url):
    """
    Downloads the PDF and extracts prize data using PyMuPDF's native text extraction.
    This is FAR more accurate than OCR for structured PDFs like lottery results.
    
    The Lottery Sambad PDF structure (verified by analysis) is:
    - Lines 0-99:    5th Prize   (100 x 4-digit numbers, one per line)
    - Lines 100-101: 2nd Prize   (5 x 5-digit numbers per line = 10 total)
    - Lines 102-103: 3rd Prize   (5 x 4-digit numbers per line = 10 total)
    - [TDS notice / seller info lines in between]
    - Lines 110-111: 4th Prize   (5 x 4-digit numbers per line = 10 total)
    - Line ~112:     1st Prize   (format: "XXH NNNNN" e.g., "85H 56406")
    
    Returns a dict with prizes or None if the PDF is not available yet.
    """
    try:
        response = requests.get(url, stream=True, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            print(f"File not available yet (HTTP {response.status_code}): {url}")
            return None
            
        print(f"Extracting prizes from PDF: {url}")
        
        doc = fitz.open(stream=response.content, filetype="pdf")
        page = doc.load_page(0)
        raw_text = page.get_text()
        
        # Split into non-empty lines
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        
        # --- Extract 1st Prize (e.g., "85H 56406") ---
        first_prize = "N/A"
        first_prize_series = ""
        # Pattern: letter series (like 85H, 91H, 95H) followed by 5-digit number
        fp_pattern = re.compile(r'\b([A-Z0-9]+H)\s+(\d{5})\b')
        for line in lines:
            m = fp_pattern.search(line)
            if m and "Prize" not in line and "Amount" not in line:
                first_prize_series = m.group(1)
                first_prize = f"{m.group(1)} {m.group(2)}"
                break
        # Fallback: just a standalone 5-digit number near the bottom
        if first_prize == "N/A":
            for line in reversed(lines[-20:]):
                m = re.search(r'^\d{5}$', line)
                if m:
                    first_prize = line
                    break
        
        # --- Extract 2nd Prize (5-digit numbers, NOT including the 1st prize number) ---
        five_digit_blocks = []
        for line in lines:
            nums = re.findall(r'\b\d{5}\b', line)
            if nums:
                # Exclude the line that contains the first prize series (e.g. "85H 56406")
                if not fp_pattern.search(line):
                    five_digit_blocks.extend(nums)
        second_prize = ", ".join(five_digit_blocks[:10]) if five_digit_blocks else "N/A"
        
        # --- Extract 4-digit number blocks ---
        # PDF structure: lines 0-99 are the 5th Prize (one 4-digit number per line)
        # After 5-digit blocks appear: 3rd prize rows, then 4th prize rows
        four_digit_single_lines = []  # Lines with exactly ONE 4-digit number (5th prize rows)
        four_digit_group_lines = []   # Lines with MULTIPLE 4-digit numbers (3rd/4th prize rows)
        
        for line in lines:
            # Skip lines with 5-digit numbers (those are 2nd/1st prize)
            if re.search(r'\b\d{5}\b', line):
                continue
            # Skip noisy text lines (TDS notice, dates with slashes, etc.)
            if '/' in line or any(word in line.upper() for word in ['TDS', 'PRIZE', 'AMOUNT', 'DEDUCTED', 'SELLER', 'SOLD', 'SECTION', 'ACT', 'LOTTERY', 'WEEKLY', 'SPARK', 'DEAR', 'W.E.F']):
                continue
            
            nums = re.findall(r'\b\d{4}\b', line)
            if not nums:
                continue
                
            # Exclude year-like numbers that are not prize numbers
            nums = [n for n in nums if n not in ('2025', '2026', '2024', '2023')]
            if not nums:
                continue
            
            if len(nums) == 1:
                four_digit_single_lines.append(nums[0])
            else:
                four_digit_group_lines.extend(nums)
        
        # The 5th prize is the large block of single 4-digit numbers (100 numbers)
        # Take first 100 from the single lines
        fifth_prize_list = four_digit_single_lines[:100]
        fifth_prize = ", ".join(fifth_prize_list) if fifth_prize_list else "N/A"
        
        # The group lines contain: 3rd prize (10 numbers) then 4th prize (10 numbers)
        third_prize = ", ".join(four_digit_group_lines[:10]) if len(four_digit_group_lines) >= 10 else ", ".join(four_digit_group_lines)
        fourth_prize = ", ".join(four_digit_group_lines[10:20]) if len(four_digit_group_lines) >= 20 else "N/A"
        
        print(f"  1st: {first_prize}")
        print(f"  2nd: {len(five_digit_blocks)} numbers")
        print(f"  3rd: {len(four_digit_group_lines[:10])} numbers")
        print(f"  4th: {len(four_digit_group_lines[10:20])} numbers")
        print(f"  5th: {len(fifth_prize_list)} numbers")
        
        return {
            "1st Prize": first_prize,
            "2nd Prize": second_prize,
            "3rd Prize": third_prize if third_prize else "N/A",
            "4th Prize": fourth_prize,
            "5th Prize": fifth_prize
        }
    except Exception as e:
        print(f"Exception for {url}: {e}")
        import traceback
        traceback.print_exc()
        return None



def main():
    if not GAS_WEBHOOK_URL:
        print("Error: GAS_WEBHOOK_URL environment variable is not set!")
        return
    
    ist = timezone(timedelta(hours=5, minutes=30))
    today_date = datetime.now(ist)
    
    # Save into Google Sheets as the REAL current date (e.g. 2026)
    date_str_sheets = today_date.strftime("%Y-%m-%d")
    date_str_url = today_date.strftime("%d-%m-%Y")
    day_str = today_date.strftime("%A").upper()

    draws = [
        {"time": "1:00 PM", "name": "DEAR MORNING", "url_part": "1pm", "hour": 13},
        {"time": "6:00 PM", "name": "DEAR DAY", "url_part": "6pm", "hour": 18},
        {"time": "8:00 PM", "name": "DEAR NIGHT", "url_part": "8pm", "hour": 20}
    ]

    current_hour = today_date.hour

    for draw in draws:
        if current_hour < draw["hour"]:
            print(f"Skipping {draw['time']}: It is currently {current_hour}:00, which is before the {draw['hour']}:00 draw time.")
            continue

        url = f"https://lottery.sambad.com/pdf/lottery-sambad-{draw['url_part']}-{date_str_url}.pdf"
        
        ocr_prizes = process_lottery_image(url)
        if ocr_prizes:
            data = {
                "Date": date_str_sheets,
                # Prepend a single quote to force Google Sheets to treat this as plain text, 
                # otherwise it auto-converts "1:00 PM" into 24-hour format (13:00)
                "Time": f"'{draw['time']}", 
                "Day": day_str,
                "Draw No": "Live",
                "Lottery Name": draw["name"],
                "source_url": url
            }
            # Merge the OCR extracted prizes into our payload
            data.update(ocr_prizes)
            send_to_gas(f"Results {draw['time']}", data)
        else:
            print(f"Skipping {draw['time']}: PDF not available yet or extraction failed.")

if __name__ == "__main__":
    main()
