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

    unique_bets_data = [] # List of dicts storing extracted data
    processed_texts = [] # To help with overlap detection if needed, or just use the full list
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    max_scroll_attempts = 3
    
    # We will try to rely on the order of elements.
    # To avoid overlap duplicates:
    # We can keep track of the list of bet texts we have already added.
    # But since duplicates are allowed, we can't just check "if text in list".
    # We need to check if the *new batch* overlaps with the *end of the old batch*.
    
    # Simpler approach for now:
    # 1. Scroll to top.
    # 2. Extract visible.
    # 3. Scroll down.
    # 4. Extract visible.
    # 5. Filter out the ones that match the *tail* of the previous extraction?
    # Actually, often standard scrolling + `set` of WebElements (by ID) works if we don't hold them too long.
    # But IDs change on re-render.
    
    # Let's try: Extract text immediately.
    # Maintain a list of all extracted bet texts.
    # To prevent overlap (seeing same bet twice due to partial scroll):
    # We need a unique ID.
    # Let's look for a link with a unique ID in the row.
    
    while True:
        # Find all visible rows
        status_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Won') or contains(text(), 'Lost')]")
        
        current_batch_data = []
        
        for status_el in status_elements:
            try:
                row = status_el.find_element(By.XPATH, "./ancestor::a | ./ancestor::div[contains(@class, 'grid') or contains(@class, 'flex')][position() < 6]")
                text_content = row.text
                
                # Try to get a unique link or ID
                try:
                    href = row.get_attribute("href")
                except:
                    href = None
                    
                current_batch_data.append({
                    "text": text_content,
                    "href": href,
                    "element_location": row.location['y'] # Y-coord to help sort/dedupe in current view
                })
            except:
                continue
        
        # Sort current batch by Y location to ensure order
        current_batch_data.sort(key=lambda x: x['element_location'])
        
        # Deduplicate overlap with previous data
        # We assume new bets appear at the bottom.
        # We just need to append the *new* ones.
        # Naive check: if we have seen this (text+href) in the *last N* items, skip?
        # Better: iterate through current batch. If item matches the *last added item*, skip.
        # But what if I have 2 identical bets in a row?
        # The overlap will likely be a *sequence*.
        
        # Robust Infinite Scroll Scraping:
        # Just use a Set of (href, text) if we assume (href+text) is unique enough for a *bet*.
        # If I bet twice on same market -> same Text, same Href (to market).
        # So Set deduction removes valid duplicates!
        
        # Fallback:
        # We append ONLY items that are visually below the previous extraction?
        # No, we scroll.
        
        # Let's assume that if we see the EXACT SAME LIST of bets as last time, we are done.
        # We will optimistically append *all* bets from the first screen.
        # For subsequent screens, we check if the first K items match the last K items of previous.
        
        # Simplest valid strategy for this task:
        # Just collect everything seen. If we over-count due to overlap, it's an error but safer than missing.
        # But we can try to minimize overlap:
        # We can track the index of the last processed element? No.
        
        # Let's use a "Seen Signature" of the last 5 added bets.
        # When processing new batch, find where this signature occurs (if at all), and add everything after.
        
        new_items = []
        if not unique_bets_data:
            new_items = current_batch_data
        else:
            # Try to find overlap
            # Look for the last item of unique_bets_data in current_batch_data
            # Be careful of identical items.
            
            # Reverse search current batch for the last added item
            last_item = unique_bets_data[-1]
            match_index = -1
            
            # We look for the *sequence* of last 3 items to be safer
            check_len = min(len(unique_bets_data), 3)
            tail_signature = [ (x['text'], x['href']) for x in unique_bets_data[-check_len:] ]
            
            # Scan current batch for this signature
            # We want to find the *first* occurrence of this signature? 
            # Or the occurrence that aligns with the top?
            
            # Naive: Just find the last item's match in current batch
            for i, item in enumerate(current_batch_data):
                if item['text'] == last_item['text'] and item['href'] == last_item['href']:
                    # Potential match. Check previous items if possible.
                    match = True
                    for k in range(1, check_len):
                        prev_idx = i - k
                        if prev_idx < 0:
                            # If we run off start of current batch, we assume match (overlap start)
                            break
                        
                        hist_item = unique_bets_data[-(1+k)]
                        curr_item = current_batch_data[prev_idx]
                        if not (curr_item['text'] == hist_item['text'] and curr_item['href'] == hist_item['href']):
                            match = False
                            break
                    
                    if match:
                        match_index = i
            
            # If match found, take everything after match_index
            if match_index != -1:
                new_items = current_batch_data[match_index+1:]
            else:
                # No overlap found? Maybe we scrolled too far? 
                # Or completely new set?
                # Append all.
                new_items = current_batch_data
                
        # Add new items
        for item in new_items:
            unique_bets_data.append(item)
            
        if bet_limit and len(unique_bets_data) >= bet_limit:
            break
            
        # Scroll logic
        if not bet_limit or len(unique_bets_data) < bet_limit:
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
            
    print(f"Found {len(unique_bets_data)} bets.")
    
    processed_bets = 0
    wins = 0
    losses = 0
    total_won = 0.0
    total_lost = 0.0
    
    bet_history = {} 
    market_outcomes = {}
    
    # Process the extracted data
    for item in unique_bets_data:
        try:
            text_content = item['text']
            lines = text_content.split('\n')
            
            if not lines: continue
            
            title = lines[0].strip()
            status = "Unknown"
            amount_str = "0"
            outcome = "Unknown"
            
            full_text = " ".join(lines)
            
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
        first_write = True
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

            # Save incrementally
            try:
                mode = 'w' if first_write else 'a'
                pd.DataFrame([user_stat]).to_csv(args.output_file, mode=mode, header=first_write, index=False)
                first_write = False
            except Exception as e:
                print(f"Error saving incremental CSV: {e}")

            count += 1
            
        print(f"\nAnalysis complete. Statistics saved to {args.output_file}")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

