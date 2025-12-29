import requests
import pandas as pd

# Base URL for Polymarket's Official Data API
BASE_URL = "https://gamma-api.polymarket.com"

def get_top_markets():
    # Fetch top active markets by volume
    url = f"{BASE_URL}/markets"
    params = {
        "limit": 10,
        "active": "true",
        "closed": "false",
        "order": "volume",
        "ascending": "false"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def get_recent_trades(market_id):
    # Fetch recent trades for a specific market to find active users
    # Note: Gamma doesn't have a simple "Get All Users" endpoint, 
    # so we find users by looking at active markets.
    url = f"{BASE_URL}/events"
    params = {
        "limit": 20,
        "market": market_id,
        "type": "trade" # specifically looking for trades
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return []

# --- MAIN EXECUTION ---
print("Fetching Top Markets...")
markets = get_top_markets()

user_set = set()
data = []

if markets:
    # Look at the top 3 markets to harvest user addresses
    for market in markets[:3]: 
        print(f"Scanning market: {market.get('question', 'Unknown')}")
        market_id = market.get('id')
        
        trades = get_recent_trades(market_id)
        for trade in trades:
            # The 'maker' or 'taker' is the user address
            user = trade.get('taker_address') # Taker is usually the active bettor
            if user and user not in user_set:
                user_set.add(user)
                data.append({
                    'Market': market.get('question'),
                    'User Address': user,
                    'Trade Amount': trade.get('amount'),
                    'Outcome': trade.get('outcome_index')
                })

    df = pd.DataFrame(data)
    print("\n--- Potential 'Whales' Found ---")
    print(df.head())
    
    # Save to CSV for your next step (Win Rate Analysis)
    df.to_csv("potential_whales.csv", index=False)
    print(f"\nSaved {len(df)} unique interactions to potential_whales.csv")

else:
    print("No markets found.")