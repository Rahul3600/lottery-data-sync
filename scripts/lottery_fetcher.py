import os
import json
import requests
from datetime import datetime

import io
from PIL import Image
import fitz  # PyMuPDF
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
    Downloads the PDF, converts the first page to an image using PyMuPDF, runs OCR, 
    and extracts the prizes using regex heuristics.
    Returns a dict with prizes or None if the PDF is not available yet.
    """
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code != 200:
            print(f"File not available yet: {url}")
            return None
            
        print(f"Running OCR on {url}...")
        
        # Load the PDF from bytes
        doc = fitz.open(stream=response.content, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap()
        
        # Convert to PIL Image for pytesseract
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
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



def main():
    if not GAS_WEBHOOK_URL:
        print("Error: GAS_WEBHOOK_URL environment variable is not set!")
        return
    
    today_date = datetime.now()
    
    # Save into Google Sheets as the REAL current date (e.g. 2026)
    date_str_sheets = today_date.strftime("%Y-%m-%d")
    date_str_url = today_date.strftime("%d-%m-%Y")
    day_str = today_date.strftime("%A").upper()

    draws = [
        {"time": "1:00 PM", "name": "DEAR MORNING", "url_part": "1pm", "hour": 13},
        {"time": "6:00 PM", "name": "DEAR DAY", "url_part": "6pm", "hour": 18},
        {"time": "8:00 PM", "name": "DEAR EVENING", "url_part": "8pm", "hour": 20}
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
            print(f"Skipping {draw['time']}: Image not uploaded yet or OCR failed.")

if __name__ == "__main__":
    main()
