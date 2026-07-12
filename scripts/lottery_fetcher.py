import os
import json
import requests
from datetime import datetime

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

def main():
    if not GAS_WEBHOOK_URL:
        print("Error: GAS_WEBHOOK_URL environment variable is not set!")
        return

    # =========================================================================
    # TODO: Replace the dummy data below with your actual scraping/API logic
    # =========================================================================
    
    today_date = datetime.now()
    date_str_sheets = today_date.strftime("%Y-%m-%d")
    date_str_url = today_date.strftime("%d-%m-%Y")
    day_str = today_date.strftime("%A").upper()

    # 1. Morning (1 PM)
    morning_url = f"https://lottery.sambad.com/images/mobile/lottery-sambad-1pm-{date_str_url}.avif"
    morning_data = {
        "Date": date_str_sheets,
        "Time": "1 PM",
        "Day": day_str,
        "Draw No": "123",
        "Lottery Name": "DEAR MORNING",
        "1st Prize": "89341",
        "2nd Prize": "12345, 67890",
        "3rd Prize": "1111, 2222, 3333",
        "4th Prize": "4444, 5555, 6666",
        "5th Prize": "7777, 8888, 9999",
        "source_url": morning_url
    }
    send_to_gas("Morning (1 PM)", morning_data)

    # 2. Day (6 PM)
    day_url = f"https://lottery.sambad.com/images/mobile/lottery-sambad-6pm-{date_str_url}.avif"
    day_data = {
        "Date": date_str_sheets,
        "Time": "6 PM",
        "Day": day_str,
        "Draw No": "124",
        "Lottery Name": "DEAR DAY",
        "1st Prize": "45678",
        "2nd Prize": "54321, 09876",
        "3rd Prize": "4444, 5555, 6666",
        "4th Prize": "7777, 8888, 9999",
        "5th Prize": "1111, 2222, 3333",
        "source_url": day_url
    }
    send_to_gas("Day (6 PM)", day_data)

    # 3. Evening (8 PM)
    evening_url = f"https://lottery.sambad.com/images/mobile/lottery-sambad-8pm-{date_str_url}.avif"
    evening_data = {
        "Date": date_str_sheets,
        "Time": "8 PM",
        "Day": day_str,
        "Draw No": "125",
        "Lottery Name": "DEAR EVENING",
        "1st Prize": "99999",
        "2nd Prize": "11111, 22222",
        "3rd Prize": "3333, 4444, 5555",
        "4th Prize": "6666, 7777, 8888",
        "5th Prize": "9999, 0000, 1111",
        "source_url": evening_url
    }
    send_to_gas("Evening (8 PM)", evening_data)

if __name__ == "__main__":
    main()
