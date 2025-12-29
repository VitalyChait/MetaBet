import os
import time
import re
import argparse
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables
load_dotenv()

def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Uncomment to run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Mask automation to avoid some basic detection (optional but good practice)
    options.add_argument("--disable-blink-features=AutomationControlled") 
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def parse_arguments():
    parser = argparse.ArgumentParser(description="Analyze Polymarket user betting history.")
    parser.add_argument("--user-limit", type=int, default=None, help="Limit the number of users to scan from the CSV.")
    parser.add_argument("--bet-limit", type=int, default=None, help="Limit the number of bets to scan per user. Default is all bets.")
    parser.add_argument("--csv-file", type=str, default="polymarket_leaderboard_monthly.csv", help="Path to the leaderboard CSV file.")
    parser.add_argument("--output-file", type=str, default="backend/polymarket_user_stats.csv", help="Path to save the analysis output CSV.")
    return parser.parse_args()

def extract_and_analyze_bets(driver, bet_limit):
    print("Extracting bets...")
    
    # Wait for at least one bet to appear or timeout
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Won') or contains(text(), 'Lost')]"))
        )
    except:
        print("No closed bets found or timeout.")
        return {}

    unique_rows = []
    seen_ids = set() # Use web element ID or a stable hash if possible, but elements change on scroll. 
                     # Better to track processed texts or indices if list is stable.
                     # However, on infinite scroll, DOM elements might be recycled or added.
                     # A safer way for scraping infinite scroll is to extract data as we go and track uniqueness by content.
    
    extracted_bets = [] # List of dicts
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    max_scroll_attempts = 3 # Stop if no new content after 3 tries
    
    while True:
        # Find current visible rows
        # Strategy: Find status elements, get parent rows
        status_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Won') or contains(text(), 'Lost')]")
        
        found_new_on_this_scroll = False
        
        for status_el in status_elements:
            try:
                # Traverse up to find the row container
                row = status_el.find_element(By.XPATH, "./ancestor::a | ./ancestor::div[contains(@class, 'grid') or contains(@class, 'flex')][position() < 6]")
                
                # Check if we've seen this row element (by ID) or content?
                # Element IDs change. Let's parse immediately and check for uniqueness of the *bet instance*.
                # But duplicates are allowed! So how do we distinguish "seen this DOM element" vs "duplicate bet"?
                # We can check if the element is already in our current 'unique_rows' list (Selenium objects)
                # But scrolling might invalidate them.
                
                # Best approach for infinite scroll: 
                # 1. Parse the data.
                # 2. Add to a list if we haven't processed this exact *row index/position*? Hard to track.
                # 3. Often easier: Collect all, then dedupe?
                #    If duplicates are "valid" data (user bet twice), we can't simple-dedupe by content.
                #    We need to dedupe by "Identity of the bet event".
                #    Polymarket doesn't show bet IDs easily.
                
                # Compromise:
                # We assume that scrolling down reveals NEW bets.
                # We keep track of the text of the *last few* bets processed to avoid overlapping processing
                # OR we just collect everything we see, and assume the script manages the flow.
                
                # Actually, Selenium `find_elements` returns current DOM.
                # If we scroll, top elements might be removed (virtualization) or stay.
                # If they stay, we will see them again.
                # We can use `row.text` + `row.location` (y-coordinate) maybe? No, location changes.
                
                # Let's try to track by a unique attribute if available, or just full text + index relative to something?
                # Simple approach: content hash. But identical bets have identical content.
                # If I bet twice identically, the row text is identical.
                # How does a human know? Position in list.
                # We can rely on the fact that we append new ones.
                
                # Let's use a set of (text, index_in_current_batch) ? No.
                
                # Allow redundancy processing: 
                # If we collect all visible rows, how do we know which ones we already collected?
                # We can't easily unless we know the total order.
                
                # For now, let's assume we can grab all visible, process them.
                # If bet_limit is None (infinite), we scroll and grab more.
                # To avoid re-adding the top ones, we might need to rely on the fact that we are scrolling.
                # If the list is virtualized, old ones disappear.
                # If not, they stay.
                
                # Let's try to use the `data-id` or `href` if available.
                # The rows are often `<a>` tags or contain links. The profile URL is generic.
                # Does the bet have a transaction hash link?
                # Usually yes! "View on block explorer" or similar might be in the row or clickable.
                # If we can find a unique link (tx hash), that's perfect.
                # If not, we might over-count.
                
                # Let's just do a single pass of "scroll to bottom until end", then "collect all"?
                # If list is virtualized, "collect all at end" won't work.
                # We must collect as we go.
                
                # To handle "identical bets" vs "same row seen twice":
                # We can track the WebElements seen so far in this session?
                # Selenium IDs are stable for the lifetime of the DOM element.
                # If the DOM doesn't trash elements, `row.id` works.
                
                if row in unique_rows:
                    continue
                
                unique_rows.append(row)
                found_new_on_this_scroll = True
                
                if bet_limit and len(unique_rows) >= bet_limit:
                    break
                    
            except:
                continue

        if bet_limit and len(unique_rows) >= bet_limit:
            break
            
        # Scroll logic
        if not bet_limit or len(unique_rows) < bet_limit:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= max_scroll_attempts:
                    break
            else:
                last_height = new_height
                scroll_attempts = 0
                
        else:
            break
            
    print(f"Found {len(unique_rows)} bet rows.")
    
    processed_bets = 0
    wins = 0
    losses = 0
    total_won = 0.0
    total_lost = 0.0
    
    # Dictionary to track duplicates: { (title, outcome): [details] }
    # Also track markets to detect hedging: { title: set(outcomes) }
    bet_history = {} 
    market_outcomes = {}
    
    for row in unique_rows:
        try:
            text_content = row.text
            lines = text_content.split('\n')
            
            if not lines: continue
            
            title = lines[0].strip()
            
            status = "Unknown"
            amount_str = "0"
            outcome = "Unknown"
            
            full_text = " ".join(lines)
            
            if "Won" in full_text:
                status = "Won"
                wins += 1
                try:
                    # Regex to find "Won <amount> <outcome> at" or "Lost <amount> <outcome> at"
                    match = re.search(r'(Won|Lost)\s+([\d\.,]+)\s+(.*?)\s+at', full_text)
                    if match:
                        amount_str = match.group(2).replace(',', '')
                        outcome = match.group(3)
                        val = float(amount_str)
                        total_won += val
                except Exception as e:
                    # print(f"Regex error: {e}")
                    pass

            elif "Lost" in full_text:
                status = "Lost"
                losses += 1
                try:
                    match = re.search(r'(Won|Lost)\s+([\d\.,]+)\s+(.*?)\s+at', full_text)
                    if match:
                        amount_str = match.group(2).replace(',', '')
                        outcome = match.group(3)
                        val = float(amount_str)
                        total_lost += val
                except:
                    pass
            else:
                # Skip if neither won nor lost (e.g. pending/redeemed?)
                continue

            # Track for duplicates (Same Title + Same Outcome)
            key = (title, outcome)
            if key not in bet_history:
                bet_history[key] = []
            
            bet_history[key].append({
                "title": title,
                "outcome": outcome,
                "status": status,
                "amount": amount_str
            })
            
            # Track for Hedging (Same Title, Any Outcome)
            if title not in market_outcomes:
                market_outcomes[title] = set()
            market_outcomes[title].add(outcome)
            
        except Exception as e:
            print(f"Error parsing row: {e}")
            continue

    # Analyze duplicates
    duplicates_info = []
    
    # Check for actual duplicates (same title, same outcome, count > 1)
    for (title, outcome), bets in bet_history.items():
        if len(bets) > 1:
            duplicates_info.append({
                "title": title,
                "outcome": outcome,
                "count": len(bets),
                "type": "DUPLICATE", # Exact duplicate
                "details": bets
            })

    # Check for Hedging (Same Title, Different Outcomes)
    # We iterate over market_outcomes to see if any market has > 1 outcome
    # Note: This is separate from "Duplicate Bets" count
    hedged_markets = []
    for title, outcomes in market_outcomes.items():
        if len(outcomes) > 1:
            hedged_markets.append({
                "title": title,
                "outcomes": list(outcomes)
            })

    return {
        "wins": wins,
        "losses": losses,
        "total_won": total_won,
        "total_lost": total_lost,
        "duplicates": duplicates_info,
        "hedged_markets": hedged_markets
    }

def navigate_and_sort_bets(driver, profile_url):
    print(f"Navigating to {profile_url}...")
    driver.get(profile_url)
    
    try:
        wait = WebDriverWait(driver, 15)
        
        # 1. Click "Closed" tab
        # Use exact text match or robust contains
        closed_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Closed'] | //button[contains(text(), 'Closed')]")))
        closed_tab.click()
        print("Clicked 'Closed' tab.")
        time.sleep(3)
        
        # 2. Find and Click Sort Dropdown
        # We look for a button that has specific ARIA attributes or contains the sort text.
        # Common sort states: Profit/Loss, Date, Value, Alphabetically
        sort_keywords = ["Profit/Loss", "Date", "Value", "Alphabetically", "Sort"]
        
        sort_button = None
        
        # Try finding by ARIA attribute first (most robust for UI components like Radix)
        try:
            # Find all buttons that are menu triggers
            candidates = driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu'] | //button[@data-slot='dropdown-menu-trigger']")
            for btn in candidates:
                txt = btn.text
                # If the button text matches one of our expected states, use it
                if any(k in txt for k in sort_keywords):
                    sort_button = btn
                    break
        except Exception as e:
            print(f"Debug: Error finding buttons by attributes: {e}")
            pass
            
        if not sort_button:
            print("Debug: Fallback to text search for sort button...")
            # Fallback to strict text search in buttons
            # We construct a robust XPath that looks for a button containing the text
            xpath_conditions = " or ".join([f"contains(., '{k}')" for k in sort_keywords])
            try:
                sort_button = wait.until(EC.element_to_be_clickable((By.XPATH, f"//button[{xpath_conditions}]")))
            except:
                print("Debug: Could not find sort button by text.")
                # As a last resort, list all buttons to see what's there (for debugging if this fails)
                # buttons = driver.find_elements(By.TAG_NAME, "button")
                # print("Available buttons:", [b.text for b in buttons if b.is_displayed()])
                raise Exception("Sort button not found")
            
        # Check current state
        current_text = sort_button.text
        if "Date" in current_text and "Sort" not in current_text: # "Sort" might be a label "Sort by: Date"
             # If strictly "Date", it might be already sorted.
             pass
        
        # We click it anyway to be sure or if it's not Date
        if "Date" not in current_text or True: # Force click to ensure we see the menu to select Date
            sort_button.click()
            print(f"Clicked Sort dropdown (Text: '{current_text}').")
            time.sleep(1)
            
            # 3. Select "Date"
            # It's usually in a role='menu' or role='listbox'
            # We look for "Date" in a clickable element that is NOT the sort button itself
            
            try:
                # Look for the menu item specifically
                # Radix UI often puts items in a div with role="menuitem"
                date_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem' and contains(., 'Date')] | //div[@role='option' and contains(., 'Date')]")))
                date_option.click()
                print("Selected 'Date' option.")
            except:
                print("Debug: Standard menuitem selector failed. Trying broad text match.")
                # Fallback: Find any visible element with text "Date" that appeared recently
                date_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Date')]")
                clicked = False
                for el in date_elements:
                    if el.is_displayed() and el != sort_button:
                        try:
                            el.click()
                            clicked = True
                            print("Selected 'Date' option (broad match).")
                            break
                        except:
                            continue
                if not clicked:
                     raise Exception("Could not click Date option")

            time.sleep(3)
            
    except Exception as e:
        print(f"Error navigating/sorting: {e}")
        return False
        
    return True

def main():
    args = parse_arguments()
    print(f"Starting analysis with User Limit: {args.user_limit}, Bet Limit: {args.bet_limit}")
    
    # Placeholder for main logic
    if not os.path.exists(args.csv_file):
        print(f"Error: CSV file '{args.csv_file}' not found.")
        return

    try:
        df = pd.read_csv(args.csv_file)
        print(f"Loaded {len(df)} users from {args.csv_file}")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return


    driver = setup_driver()
    try:
        count = 0
        limit = args.user_limit
        
        all_stats = []
        
        # Iterate through users
        for index, row in df.iterrows():
            if limit and count >= limit:
                break
                
            profile_url = row.get('Profile URL')
            name = row.get('Name', 'Unknown')
            if not profile_url or pd.isna(profile_url):
                continue
                
            print(f"--- Processing User {index + 1}: {name} ---")
            
            user_stat = {
                "Rank": row.get('Rank'),
                "Name": name,
                "Profile URL": profile_url,
                "Wins": 0,
                "Losses": 0,
                "Total Won": 0.0,
                "Total Lost": 0.0,
                "Win Rate": 0.0,
                "Duplicate Bets": 0,
                "Hedged Bets": 0,
                "Notes": ""
            }
            
            if navigate_and_sort_bets(driver, profile_url):
                 results = extract_and_analyze_bets(driver, args.bet_limit)
                 if results:
                     print(f"  Results for {name}:")
                     print(f"  Wins: {results['wins']}, Losses: {results['losses']}")
                     print(f"  Total Won: ${results['total_won']:.2f}, Total Lost: ${results['total_lost']:.2f}")
                     
                     user_stat["Wins"] = results['wins']
                     user_stat["Losses"] = results['losses']
                     user_stat["Total Won"] = results['total_won']
                     user_stat["Total Lost"] = results['total_lost']
                     
                     total_bets = results['wins'] + results['losses']
                     if total_bets > 0:
                         user_stat["Win Rate"] = (results['wins'] / total_bets) * 100
                     
                     if results['duplicates']:
                         print(f"  Found {len(results['duplicates'])} duplicate bet groups:")
                         dup_count = sum(d['count'] - 1 for d in results['duplicates']) # Count of extra bets
                         
                         user_stat["Duplicate Bets"] = len(results['duplicates']) # Number of groups
                         
                         notes = []
                         for dup in results['duplicates']:
                             print(f"    - '{dup['title']}' ({dup['outcome']}) appeared {dup['count']} times")
                             notes.append(f"{dup['title']}/{dup['outcome']} (x{dup['count']})")
                         
                         # Add hedging info to notes
                         if results['hedged_markets']:
                             print(f"  Found {len(results['hedged_markets'])} hedged markets:")
                             for h in results['hedged_markets']:
                                 print(f"    - '{h['title']}' with outcomes: {', '.join(h['outcomes'])}")
                                 notes.append(f"HEDGED: {h['title']} ({', '.join(h['outcomes'])})")
                                 
                         user_stat["Hedged Bets"] = len(results['hedged_markets'])
                         user_stat["Notes"] = "; ".join(notes)
                 else:
                     print("  No results found.")
            else:
                user_stat["Notes"] = "Navigation/Sort Error"

            all_stats.append(user_stat)
            count += 1
            
        # Save to CSV
        if all_stats:
            stats_df = pd.DataFrame(all_stats)
            stats_df.to_csv(args.output_file, index=False)
            print(f"\nAnalysis complete. Saved statistics to {args.output_file}")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

