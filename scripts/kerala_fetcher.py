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
    date_str = today.strftime("%Y-%m-%d")
    day_str = today.strftime("%A").upper()
    target_date = today.strftime("%d/%m/%Y")
    
    # Scrape the official Kerala lottery site for today's draw
    try:
        html = requests.get('https://result.keralalotteries.com/', timeout=15).text
        # Find the row containing today's date, extract the name, and the drawserial
        # HTML format: <td>LOTTERY_NAME(XX-123)</td> <td>DD/MM/YYYY</td> <td><a href="viewlotisresult.php?drawserial=75380">View</a></td>
        match = re.search(r'<td[^>]*>\s*([A-Za-z\-\s]+)\s*\(\s*([^)]+)\s*\)\s*</td>\s*<td[^>]*>\s*' + re.escape(target_date) + r'\s*</td>\s*<td[^>]*>.*?drawserial=(\d+)', html, re.DOTALL | re.IGNORECASE)
        
        if match:
            lottery_name = match.group(1).strip()
            draw_no = match.group(2).strip()
            
            # Add ordinal suffix to Draw No (e.g. SS-535 -> SS-535th)
            m = re.search(r'(\d+)$', draw_no)
            if m:
                n = int(m.group(1))
                if 11 <= (n % 100) <= 13:
                    suf = "th"
                else:
                    suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                draw_no += suf
                
            draw_serial = int(match.group(3))
            
            return {
                "draw_serial": draw_serial,
                "date_str": date_str,
                "day_str": day_str,
                "lottery_name": lottery_name.replace("-", " "),
                "draw_no": draw_no
            }
        else:
            return None
    except Exception as e:
        print("Failed to scrape Kerala index:", e)
        return None

def main():
    webhook_url = os.environ.get("GAS_WEBHOOK_URL")
    if not webhook_url:
        print("Error: GAS_WEBHOOK_URL environment variable is not set.")
        return

    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist)
    
    info = get_kerala_draw_info()
    if not info:
        if today.hour < 16:
            print(f"Too early to check! It's currently {today.hour}:{today.minute} IST. Kerala results are usually published after 4:00 PM IST.")
            return
            
        print("Today's date not found on Kerala Lottery official site. It might be a holiday!")
        payload = {
            "action": "insert",
            "tab_name": "Kerala Results",
            "data": {
                "Date": today.strftime("%Y-%m-%d"),
                "Time": "'3:00 PM",
                "Day": today.strftime("%A").upper(),
                "Draw No": "HOLIDAY",
                "Lottery Name": "KERALA STATE LOTTERY",
                "1st Prize": "HOLIDAY",
                "Consolidate Prize": "",
                "2nd Prize": "",
                "3rd Prize": "",
                "4th Prize": "",
                "5th Prize": "",
                "6th Prize": "",
                "7th Prize": "",
                "8th Prize": "",
                "9th Prize": "",
                "Source URL": "HOLIDAY"
            }
        }
        
        print("Sending HOLIDAY to Google Sheet...")
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        json_data = json.dumps(payload).encode('utf-8')
        try:
            with urllib.request.urlopen(req, data=json_data) as f:
                print("GAS Response:", f.read().decode('utf-8'))
        except Exception as e:
            print("Failed to send HOLIDAY status:", e)
        return
        
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

        lottery_name = info['lottery_name']
        draw_no = info['draw_no']

        # Extract Prizes
        prizes = {
            "1st Prize": "", "Consolidate Prize": "", "2nd Prize": "", "3rd Prize": "",
            "4th Prize": "", "5th Prize": "", "6th Prize": "", "7th Prize": "", "8th Prize": "", "9th Prize": ""
        }
        current_prize = None
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if '1st Prize' in line or '1st  Prize' in line:
                current_prize = "1st Prize"
                continue
            elif 'Consolation Prize' in line or 'Consolation  Prize' in line or 'Cons Prize' in line:
                current_prize = "Consolidate Prize"
                continue
            elif '2nd Prize' in line or '2nd  Prize' in line:
                current_prize = "2nd Prize"
                continue
            elif '3rd Prize' in line or '3rd  Prize' in line:
                current_prize = "3rd Prize"
                continue
            elif '4th Prize' in line or '4th  Prize' in line:
                current_prize = "4th Prize"
                continue
            elif '5th Prize' in line or '5th  Prize' in line:
                current_prize = "5th Prize"
                continue
            elif '6th Prize' in line or '6th  Prize' in line:
                current_prize = "6th Prize"
                continue
            elif '7th Prize' in line or '7th  Prize' in line:
                current_prize = "7th Prize"
                continue
            elif '8th Prize' in line or '8th  Prize' in line:
                current_prize = "8th Prize"
                continue
            elif '9th Prize' in line or '9th  Prize' in line:
                current_prize = "9th Prize"
                continue
                
            if current_prize:
                # Skip page headers/footers and date lines
                if '/' in line or ':' in line or 'Page' in line:
                    continue
                    
                matches = re.findall(r'[A-Z]{2}\s*\d{6}|\d{4}', line)
                if matches:
                    is_ticket = current_prize in ["1st Prize", "Consolidate Prize", "2nd Prize", "3rd Prize"]
                    joined = " ".join(matches) if is_ticket else ", ".join(matches)
                    sep = " " if is_ticket else ", "
                    
                    if prizes[current_prize]:
                        prizes[current_prize] += sep + joined
                    else:
                        prizes[current_prize] = joined

        payload = {
            "action": "insert",
            "tab_name": "Kerala Results",
            "data": {
                "Date": info["date_str"],
                "Time": "'3:00 PM",
                "Day": info["day_str"],
                "Draw No": draw_no,
                "Lottery Name": lottery_name
            }
        }
        
        # Add all prizes to payload
        for key, val in prizes.items():
            if val:
                payload["data"][key] = val

        payload["data"]["Source URL"] = pdf_url

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
