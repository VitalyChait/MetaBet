import requests
import json

user_address = "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881"

endpoints = [
    f"https://data-api.polymarket.com/activity?user={user_address}&limit=20&offset=0",
    f"https://data-api.polymarket.com/traded?user={user_address}",
    f"https://data-api.polymarket.com/positions?user={user_address}&limit=20"
]

for url in endpoints:
    print(f"--- Fetching {url} ---")
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        print(json.dumps(data, indent=2)[:500]) # Print first 500 chars to avoid flooding
        if isinstance(data, list) and len(data) > 0:
             print("First item keys:", data[0].keys())
        elif isinstance(data, dict):
             print("Keys:", data.keys())
    except Exception as e:
        print(f"Error: {e}")

