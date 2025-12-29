import requests
import csv
import time
import os

def scrape_polymarket_leaderboard():
    base_url = "https://data-api.polymarket.com/v1/leaderboard"
    output_file = "polymarket_leaderboard_monthly.csv"
    
    # Parameters for the request
    params = {
        "timePeriod": "month",
        "orderBy": "PNL",
        "limit": 20,
        "category": "overall"
    }

    all_users = []
    
    print("Starting scrape of Polymarket monthly leaderboard (Top 200)...")

    # Iterate through 10 pages (20 items per page * 10 = 200 items)
    for page in range(10):
        offset = page * 20
        params["offset"] = offset
        
        try:
            print(f"Fetching page {page + 1} (offset {offset})...")
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if not data:
                print("No more data found.")
                break
                
            for user in data:
                rank = user.get('rank', 'N/A')
                wallet_address = user.get('proxyWallet', '')
                
                # Use username if available, otherwise fallback to wallet address (or part of it)
                display_name = user.get('userName')
                if not display_name:
                    display_name = wallet_address
                
                profile_url = ""
                if wallet_address:
                    profile_url = f"https://polymarket.com/profile/{wallet_address}"
                
                all_users.append({
                    "Rank": rank,
                    "Name": display_name,
                    "Profile URL": profile_url
                })
            
            # Be nice to the API
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page + 1}: {e}")
            break

    # Save to CSV
    if all_users:
        # Resolve path relative to where script is likely run or absolute path
        # Using current working directory for simplicity as per request context
        with open(output_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=["Rank", "Name", "Profile URL"])
            writer.writeheader()
            writer.writerows(all_users)
        
        print(f"\nSuccessfully scraped {len(all_users)} users.")
        print(f"Data saved to {os.path.abspath(output_file)}")
    else:
        print("No users scraped.")

if __name__ == "__main__":
    scrape_polymarket_leaderboard()


