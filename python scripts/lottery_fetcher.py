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
    
    # Example 1: Inserting into "Morning (1 PM)" Tab
    morning_data = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Time": "1 PM",
        "Day": "SUNDAY",
        "Draw No": "123",
        "Lottery Name": "DEAR MORNING",
        "1st Prize": "89341",
        "2nd Prize": "12345, 67890",
        "3rd Prize": "1111, 2222, 3333",
        "4th Prize": "4444, 5555, 6666",
        "5th Prize": "7777, 8888, 9999"
    }
    send_to_gas("Morning (1 PM)", morning_data)

    # Example 2: Inserting into a Prediction Tab with totally different columns
    prediction_data = {
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Time": "8 PM",
        "Day": "SUNDAY",
        "Middle Matrix": "00, 01, 02, 03, 04",
        "5 Digit Predicti": "34519, 14519, 94019",
        "4 Digit Predicti": "50314, 70026",
        "SUPER VIP PREDICTION": "92902, 31202, 51248"
    }
    send_to_gas("Predictions Evening (8 PM)", prediction_data)

if __name__ == "__main__":
    main()
