import requests
import json

user_address = "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881"

# Remove sizeThreshold to see if we get closed positions (size ~0)
url = f"https://data-api.polymarket.com/positions?user={user_address}&limit=50&offset=0"

print(f"--- Fetching Positions from {url} ---")
try:
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    closed_positions = [p for p in data if float(p.get('size', 0)) < 0.001]
    realized_pnl_positions = [p for p in data if float(p.get('realizedPnl', 0)) != 0]
    
    print(f"Total positions returned: {len(data)}")
    print(f"Positions with size ~0: {len(closed_positions)}")
    print(f"Positions with realized PnL != 0: {len(realized_pnl_positions)}")
    
    if realized_pnl_positions:
        print("Example realized PnL position:", json.dumps(realized_pnl_positions[0], indent=2))
        
except Exception as e:
    print(f"Error: {e}")

