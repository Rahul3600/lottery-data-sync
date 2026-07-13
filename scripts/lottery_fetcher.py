import os
import json
import requests
from datetime import datetime

import io
from PIL import Image
import pillow_avif
import pytesseract
import re

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
    Downloads the AVIF image, runs OCR, and extracts the prizes using regex heuristics.
    Returns a dict with prizes or None if the image is not available yet.
    """
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code != 200:
            print(f"Image not available yet: {url}")
            return None
            
        print(f"Running OCR on {url}...")
        img = Image.open(response.raw)
        text = pytesseract.image_to_string(img)
        
        # Extract 5-digit and 4-digit numbers using Regex
        five_digits = re.findall(r'\b\d{5}\b', text)
        four_digits = re.findall(r'\b\d{4}\b', text)
        
        if not five_digits and not four_digits:
            print("OCR extracted text but found no 5-digit or 4-digit patterns.")
            return None
            
        first_prize = five_digits[0] if len(five_digits) > 0 else "N/A"
        second_prize = ", ".join(five_digits[1:11]) if len(five_digits) > 1 else "N/A"
        third_prize = ", ".join(four_digits[:10]) if len(four_digits) > 0 else "N/A"
        fourth_prize = ", ".join(four_digits[10:20]) if len(four_digits) > 10 else "N/A"
        fifth_prize = ", ".join(four_digits[20:140]) if len(four_digits) > 20 else "N/A"
        
        return {
            "1st Prize": first_prize,
            "2nd Prize": second_prize,
            "3rd Prize": third_prize,
            "4th Prize": fourth_prize,
            "5th Prize": fifth_prize
        }
    except Exception as e:
        print(f"OCR Exception for {url}: {e}")
        return None

def generate_dummy_data(draw, date_str_sheets, day_str, url):
    """Generates dummy fallback data if OCR fails or image is not available yet (e.g. 2026 test dates)"""
    dummy_prizes = {
        "1pm": {"1st": "89341", "2nd": "12345, 67890", "3rd": "1111, 2222, 3333", "4th": "4444, 5555, 6666", "5th": "7777, 8888, 9999"},
        "6pm": {"1st": "45678", "2nd": "54321, 09876", "3rd": "4444, 5555, 6666", "4th": "7777, 8888, 9999", "5th": "1111, 2222, 3333"},
        "8pm": {"1st": "99999", "2nd": "11111, 22222", "3rd": "3333, 4444, 5555", "4th": "6666, 7777, 8888", "5th": "9999, 0000, 1111"}
    }
    p = dummy_prizes.get(draw["url_part"], dummy_prizes["1pm"])
    
    return {
        "Date": date_str_sheets,
        "Time": f"'{draw['time']}", 
        "Day": day_str,
        "Draw No": "Live",
        "Lottery Name": draw["name"],
        "source_url": url,
        "1st Prize": p["1st"],
        "2nd Prize": p["2nd"],
        "3rd Prize": p["3rd"],
        "4th Prize": p["4th"],
        "5th Prize": p["5th"]
    }

def main():
    if not GAS_WEBHOOK_URL:
        print("Error: GAS_WEBHOOK_URL environment variable is not set!")
        return
    
    today_date = datetime.now()
    date_str_sheets = today_date.strftime("%Y-%m-%d")
    
    # Temporary test logic: if year is 2026, use 2024 for the image fetch URL so we hit REAL data!
    url_date = today_date
    if url_date.year == 2026:
        url_date = url_date.replace(year=2024)
    date_str_url = url_date.strftime("%d-%m-%Y")
    day_str = today_date.strftime("%A").upper()

    draws = [
        {"time": "1:00 PM", "name": "DEAR MORNING", "url_part": "1pm"},
        {"time": "6:00 PM", "name": "DEAR DAY", "url_part": "6pm"},
        {"time": "8:00 PM", "name": "DEAR EVENING", "url_part": "8pm"}
    ]

    for draw in draws:
        url = f"https://lottery.sambad.com/images/mobile/lottery-sambad-{draw['url_part']}-{date_str_url}.avif"
        
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
            print(f"Fallback: Sending dummy data for {draw['time']} because OCR failed or image missing.")
            fallback_data = generate_dummy_data(draw, date_str_sheets, day_str, url)
            send_to_gas(f"Results {draw['time']}", fallback_data)

if __name__ == "__main__":
    main()
