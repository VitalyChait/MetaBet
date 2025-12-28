import requests
import json
import csv
import time

def find_redeem_structure():
    with open('polymarket_leaderboard_monthly.csv', 'r') as f:
        reader = csv.DictReader(f)
        users = list(reader)

    for user in users[:20]: # Check first 20 users
        profile_url = user['Profile URL']
        wallet = profile_url.split('/')[-1]
        print(f"Checking user {wallet}...")
        
        url = f"https://data-api.polymarket.com/activity?user={wallet}&limit=100"
        try:
            resp = requests.get(url)
            if resp.status_code != 200:
                continue
            data = resp.json()
            
            for item in data:
                if item['type'] == 'REDEEM':
                    print("FOUND REDEEM ITEM:")
                    print(json.dumps(item, indent=2))
                    return
                if item['type'] != 'TRADE' and item['type'] != 'REDEEM':
                     print("FOUND UNKNOWN TYPE:", item['type'])
            time.sleep(0.2)
        except Exception as e:
            print(e)

if __name__ == "__main__":
    find_redeem_structure()

