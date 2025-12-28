import requests
import pandas as pd
import json
import time
import os
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

class PolymarketAnalyzer:
    def __init__(self, leaderboard_csv_path, output_csv_path):
        self.leaderboard_csv_path = leaderboard_csv_path
        self.output_csv_path = output_csv_path
        self.base_url = "https://data-api.polymarket.com"
        self.session = requests.Session()

    def load_users(self):
        try:
            df = pd.read_csv(self.leaderboard_csv_path)
            # Extract wallet from Profile URL
            # URL format: https://polymarket.com/profile/0x...
            df['wallet'] = df['Profile URL'].apply(lambda x: x.split('/')[-1].strip() if isinstance(x, str) else None)
            return df
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return pd.DataFrame()

    def fetch_user_activity(self, wallet):
        activities = []
        limit = 100
        offset = 0
        
        while True:
            url = f"{self.base_url}/activity"
            params = {
                "user": wallet,
                "limit": limit,
                "offset": offset
            }
            try:
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code == 429:
                    print(f"Rate limited for {wallet}, sleeping...")
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                data = resp.json()
                
                if not data:
                    break
                
                activities.extend(data)
                
                if len(data) < limit:
                    break
                
                offset += limit
                print(f"Fetched {offset} items for {wallet}...", end='\r')
                time.sleep(0.1) # Gentle rate limit
            except Exception as e:
                print(f"Error fetching activity for {wallet}: {e}")
                break
        
        return activities

    def fetch_user_positions(self, wallet):
        positions = []
        limit = 100
        offset = 0
        
        while True:
            url = f"{self.base_url}/positions"
            params = {
                "user": wallet,
                "limit": limit,
                "offset": offset
            }
            try:
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code == 429:
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                data = resp.json()
                
                if not data:
                    break
                
                positions.extend(data)
                
                if len(data) < limit:
                    break
                
                offset += limit
                time.sleep(0.1)
            except Exception as e:
                print(f"Error fetching positions for {wallet}: {e}")
                break
        
        return positions

    def analyze_user(self, wallet, name, profile_url):
        print(f"Analyzing {name} ({wallet})...")
        
        activities = self.fetch_user_activity(wallet)
        positions = self.fetch_user_positions(wallet)
        
        market_cashflow = defaultdict(float)
        market_outcomes = defaultdict(set)
        market_buys = defaultdict(int)
        market_slugs = set()

        # Process Activity
        for item in activities:
            slug = item.get('slug')
            if not slug:
                continue
            
            market_slugs.add(slug)
            
            type_ = item.get('type')
            side = item.get('side')
            usdc = float(item.get('usdcSize', 0))
            
            if type_ == 'TRADE' and side == 'BUY':
                market_cashflow[slug] -= usdc
                market_buys[slug] += 1
                outcome = item.get('outcome')
                if outcome:
                    market_outcomes[slug].add(outcome)
            
            elif type_ == 'TRADE' and side == 'SELL':
                market_cashflow[slug] += usdc
                
            elif type_ == 'REDEEM':
                market_cashflow[slug] += usdc
                
            elif type_ == 'MERGE':
                market_cashflow[slug] += usdc

        # Process Positions (Add current value)
        for pos in positions:
            slug = pos.get('slug') or pos.get('eventSlug')
            if not slug:
                continue
            
            current_value = float(pos.get('currentValue', 0))
            market_cashflow[slug] += current_value
            # Also count held positions as a 'buy' if missing from activity (though unlikely)

        # Calculate Metrics
        wins = 0
        losses = 0
        total_won = 0
        total_lost = 0
        duplicated_bets_count = 0
        duplicated_diff_outcome = 0
        duplicated_details = []

        for slug in market_slugs:
            pnl = market_cashflow[slug]
            
            # Wins/Losses
            if pnl > 0.01:
                wins += 1
                total_won += pnl
            elif pnl < -0.01:
                losses += 1
                total_lost += abs(pnl) # Keep positive for "amount lost"
            
            # Duplicated Bets
            # "bid on the same bet more than once" -> Multiple BUYS
            if market_buys[slug] > 1:
                duplicated_bets_count += 1
                outcomes = market_outcomes[slug]
                diff_outcome = len(outcomes) > 1
                
                if diff_outcome:
                    duplicated_diff_outcome += 1
                    duplicated_details.append(f"{slug}: Different outcomes ({', '.join(outcomes)})")
                else:
                    # Same outcome multiple times
                    pass

        return {
            "Name": name,
            "Wallet": wallet,
            "Profile URL": profile_url,
            "Wins": wins,
            "Losses": losses,
            "Total Won": round(total_won, 2),
            "Total Lost": round(total_lost, 2),
            "Duplicated Bets": duplicated_bets_count,
            "Diff Outcome Count": duplicated_diff_outcome,
            "Diff Outcome Details": "; ".join(duplicated_details)
        }

    def run(self, limit=None):
        df = self.load_users()
        if df.empty:
            print("No users found.")
            return

        if limit:
            print(f"Limiting analysis to first {limit} users.")
            df = df.head(limit)

        results = []
        
        # Use ThreadPool to speed up
        # Polymarket API might rate limit, so limit workers
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_user = {
                executor.submit(self.analyze_user, row['wallet'], row['Name'], row['Profile URL']): row 
                for index, row in df.iterrows() 
                if row['wallet']
            }
            
            for future in as_completed(future_to_user):
                try:
                    data = future.result()
                    results.append(data)
                except Exception as e:
                    print(f"Exception for a user: {e}")

        # Save results
        out_df = pd.DataFrame(results)
        out_df.to_csv(self.output_csv_path, index=False)
        print(f"Analysis saved to {self.output_csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Polymarket users.")
    parser.add_argument("--limit", type=int, help="Number of users to process from the top of the CSV")
    args = parser.parse_args()

    analyzer = PolymarketAnalyzer(
        leaderboard_csv_path="polymarket_leaderboard_monthly.csv",
        output_csv_path="backend/polymarket_user_analysis.csv"
    )
    analyzer.run(limit=args.limit)
