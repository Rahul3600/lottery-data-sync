import os
import json
import urllib.request
from datetime import datetime, date
import pytz
import fitz  # PyMuPDF
import re
import requests

def get_kerala_draw_info():
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist)
    
    # Base date: 2026-07-13 corresponds to draw serial 75318
    base_date = date(2026, 7, 13)
    today_date = today.date()
    diff_days = (today_date - base_date).days
    draw_serial = 75318 + diff_days
    
    return {
        "draw_serial": draw_serial,
        "date_str": today.strftime("%Y-%m-%d"),
        "day_str": today.strftime("%A").upper(),
    }

def main():
    webhook_url = os.environ.get("GAS_WEBHOOK_URL")
    if not webhook_url:
        print("Error: GAS_WEBHOOK_URL environment variable is not set.")
        return

    info = get_kerala_draw_info()
    pdf_url = f"https://result.keralalotteries.com/viewlotisresult.php?drawserial={info['draw_serial']}"
    print(f"Fetching Kerala PDF: {pdf_url}")

    try:
        response = requests.get(pdf_url, timeout=30)
        if response.status_code != 200 or 'application/pdf' not in response.headers.get('Content-Type', ''):
            print(f"Failed to fetch PDF. Status: {response.status_code}. Content-Type: {response.headers.get('Content-Type', '')}")
            return
            
        # Write PDF to temp file
        pdf_path = "kerala_temp.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
            
        # Read text with PyMuPDF
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # Clean up temp file
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        # Extract details
        # Looking for something like: BHAGYATHARA   LOTTERY NO.BT-62nd DRAW
        lottery_name = "KERALA STATE LOTTERY"
        draw_no = ""
        
        # Extract lottery name and draw no from text
        header_match = re.search(r'([A-Z\s]+)\s+LOTTERY NO\.([A-Z0-9\-]+)', text)
        if header_match:
            lottery_name = header_match.group(1).strip()
            draw_no = header_match.group(2).strip()

        # Extract 1st Prize
        first_prize = "N/A"
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if '1st Prize' in line or '1st  Prize' in line:
                if i + 1 < len(lines):
                    winner_line = lines[i+1]
                    # Matches 2 letters and 6 digits, e.g., BP 540430
                    matches = re.findall(r'[A-Z]{2}\s*\d{6}', winner_line)
                    if matches:
                        first_prize = matches[0]
                break

        if first_prize == "N/A":
            print("Could not extract first prize from PDF.")
            
        print(f"Extracted -> Name: {lottery_name}, Draw: {draw_no}, 1st Prize: {first_prize}")

        payload = {
            "action": "insert",
            "tab_name": "Kerala Results",
            "data": {
                "Date": info["date_str"],
                "Time": "'3:00 PM",
                "Day": info["day_str"],
                "Draw No": draw_no,
                "Lottery Name": lottery_name,
                "1st Prize": first_prize,
                "Source URL": pdf_url
            }
        }

        print("Sending to Google Sheet...")
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        json_data = json.dumps(payload).encode('utf-8')
        
        with urllib.request.urlopen(req, data=json_data) as f:
            resp_body = f.read().decode('utf-8')
            print("GAS Response:", resp_body)

    except Exception as e:
        print(f"Error fetching/parsing Kerala PDF: {e}")

if __name__ == "__main__":
    main()
