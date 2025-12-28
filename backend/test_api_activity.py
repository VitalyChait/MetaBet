import requests
import json
import time

user_address = "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881"

url = f"https://data-api.polymarket.com/activity?user={user_address}&limit=50&offset=0"

print(f"--- Fetching Activity from {url} ---")
try:
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    unique_types = set()
    unique_sides = set()
    
    for item in data:
        unique_types.add(item.get('type'))
        unique_sides.add(item.get('side'))
        if item.get('type') == 'REDEEM' or item.get('side') == 'SELL':
             print("Found REDEEM or SELL:", json.dumps(item, indent=2))
             break
    
    print("Unique Types:", unique_types)
    print("Unique Sides:", unique_sides)

except Exception as e:
    print(f"Error: {e}")

