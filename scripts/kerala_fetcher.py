import os
import json
import urllib.request
from datetime import datetime, date
import pytz
import fitz  # PyMuPDF
import re
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_kerala_draw_info():
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist)
    
    # Fallback: if running between midnight and 8 AM, check for yesterday's draw instead
    if today.hour < 8:
        from datetime import timedelta
        today = today - timedelta(days=1)
        
    date_str = today.strftime("%Y-%m-%d")
    day_str = today.strftime("%A").upper()
    target_date = today.strftime("%d-%m-%Y")
    
    # Scrape the official Kerala lottery site for today's draw
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        html = requests.get('https://www.lotteryagent.kerala.gov.in/result/public/', headers=headers, timeout=20, verify=False).text
        
        # Format in table:
        # <td>1</td> <td>SUVARNA KERALAM-10/11/2025 (SK-75)</td> <td>30-10-2026</td> ... data-item-id="uuid"
        pattern = r'<td>\s*(\d+)\s*</td>\s*<td>\s*([^<]+)\s*</td>\s*<td>\s*' + re.escape(target_date) + r'\s*</td>.*?data-item-id="([^"]+)"'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        
        # If today's draw is not found on Official Portal, try Backup Portal (result.keralalotteries.com)
        if not match:
            print("Today's draw not found on Official Government Portal, checking Backup Portal (result.keralalotteries.com)...")
            target_date_slash = today.strftime("%d/%m/%Y")
            try:
                html_backup = requests.get('https://result.keralalotteries.com/', headers=headers, timeout=15, verify=False).text
                match_backup = re.search(
                    r'<td[^>]*>\s*([A-Za-z\-\s]+)\s*\(\s*([^)]+)\s*\)\s*</td>\s*<td[^>]*>\s*' +
                    re.escape(target_date_slash) +
                    r'\s*</td>\s*<td[^>]*>.*?drawserial=(\d+)',
                    html_backup, re.DOTALL | re.IGNORECASE
                )
                if match_backup:
                    lottery_name = match_backup.group(1).strip().replace("-", " ")
                    draw_no = match_backup.group(2).strip()
                    m_num = re.search(r'(\d+)$', draw_no)
                    if m_num:
                        n = int(m_num.group(1))
                        suf = "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                        draw_no += suf
                    draw_serial = match_backup.group(3).strip()
                    print(f"Found on Backup Portal: {lottery_name} ({draw_no})")
                    return {
                        "item_id": draw_serial,
                        "pdf_url": f"https://result.keralalotteries.com/viewlotisresult.php?drawserial={draw_serial}",
                        "date_str": date_str,
                        "day_str": day_str,
                        "lottery_name": lottery_name,
                        "draw_no": draw_no
                    }
            except Exception as ex_b:
                print(f"Backup portal check skipped: {ex_b}")

        # If today's draw is not uploaded yet on either, fallback to yesterday's draw if running manual/delayed
        if not match:
            from datetime import timedelta
            yesterday = today - timedelta(days=1)
            target_date_prev = yesterday.strftime("%d-%m-%Y")
            pattern_prev = r'<td>\s*(\d+)\s*</td>\s*<td>\s*([^<]+)\s*</td>\s*<td>\s*' + re.escape(target_date_prev) + r'\s*</td>.*?data-item-id="([^"]+)"'
            match = re.search(pattern_prev, html, re.DOTALL | re.IGNORECASE)
            if match:
                date_str = yesterday.strftime("%Y-%m-%d")
                day_str = yesterday.strftime("%A").upper()
                print(f"Target date {target_date} not available yet. Falling back to previous draw: {target_date_prev}")
        
        if match:
            name_raw = match.group(2).strip()
            item_id = match.group(3).strip()
            
            m = re.search(r'^(.*?)(?:-\d{2}/\d{2}/\d{4})?\s*\(\s*([^)]+)\s*\)', name_raw)
            if m:
                lottery_name = m.group(1).strip().replace("-", " ")
                draw_no = m.group(2).strip()
                
                # Add ordinal suffix to Draw No (e.g. SS-535 -> SS-535th)
                m_num = re.search(r'(\d+)$', draw_no)
                if m_num:
                    n = int(m_num.group(1))
                    if 11 <= (n % 100) <= 13:
                        suf = "th"
                    else:
                        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                    draw_no += suf
            else:
                lottery_name = name_raw
                draw_no = "Live"
                
            pdf_url = f"https://www.lotteryagent.kerala.gov.in/results/{item_id}"
            
            return {
                "item_id": item_id,
                "pdf_url": pdf_url,
                "date_str": date_str,
                "day_str": day_str,
                "lottery_name": lottery_name,
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
            
        print("Target date not found on Kerala Lottery official site. It might be a holiday! Skipping data insertion.")
        return
        
    pdf_url = info['pdf_url']
    print(f"Fetching Kerala PDF: {pdf_url}")

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(pdf_url, headers=headers, timeout=30, verify=False)
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
