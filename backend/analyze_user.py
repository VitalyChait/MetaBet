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
    parser.add_argument("--bet-limit", type=int, default=10, help="Limit the number of bets to scan per user.")
    parser.add_argument("--csv-file", type=str, default="polymarket_leaderboard_monthly.csv", help="Path to the leaderboard CSV file.")
    parser.add_argument("--output-file", type=str, default="backend/polymarket_user_stats.csv", help="Path to save the analysis output CSV.")
    return parser.parse_args()

def extract_and_analyze_bets(driver, bet_limit):
    print("Extracting bets...")
    bets_data = []
    
    # Locate bet containers.
    # We look for elements that look like rows in the list.
    # A robust way is to find elements containing "Won" or "Lost" and "Shares" or currency.
    # Or common class prefixes if available. 
    # Let's try to find the list items by a broad selector and filter.
    
    # Wait for at least one bet to appear or timeout (if user has no closed bets)
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Won') or contains(text(), 'Lost')]"))
        )
    except:
        print("No closed bets found or timeout.")
        return {}

    # Find all potential bet rows
    # Assuming standard table or list divs
    # Strategy: Find the container of the list, then children.
    # Often simpler: Find all elements that contain the title structure or the status.
    
    # Let's look for the main identifiers "Won" / "Lost" labels which seem to be in a badge or specific text element.
    # Then traverse up to the row container.
    
    status_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Won') or contains(text(), 'Lost')]")
    
    # We might need to scroll to load more if bet_limit is high, 
    # but for now let's assume we just take what's visible or do simple scrolling.
    # The user asked to "limit the amount of bets to scan", so we iterate up to that limit.
    
    processed_bets = 0
    wins = 0
    losses = 0
    total_won = 0.0
    total_lost = 0.0
    
    # Dictionary to track duplicates: { "Bet Title": [ { "outcome": "...", "result": "...", "amount": ... } ] }
    bet_history = {} 
    
    # Scroll logic if needed could go here, but for now we process what we find, assuming dynamic loading handling is complex without seeing the site.
    # We will try to find rows.
    
    # Using a common container class selector guess or traversing up from status
    # Let's try to identify the row element. 
    # Usually a <div> or <a> tag wrapping the bet details.
    
    # We will iterate through status elements as they are distinct markers of a closed bet
    # Note: status_elements might contain noise, so we validate.
    
    # To ensure we get the latest, we might need to re-query if the DOM updates, but simple iteration is a start.
    
    unique_rows = []
    # Deduplicate elements based on location or parent
    seen_parents = set()
    
    for status_el in status_elements:
        try:
            # Traverse up to find the row container (e.g., 3-5 levels up)
            # Adjust 'xpath_parent' based on actual structure. 
            # A good heuristic is a container that has the Title as well.
            row = status_el.find_element(By.XPATH, "./ancestor::a | ./ancestor::div[contains(@class, 'grid') or contains(@class, 'flex')][position() < 6]")
            
            if row in seen_parents:
                continue
            
            seen_parents.add(row)
            unique_rows.append(row)
            
            if len(unique_rows) >= bet_limit:
                break
        except:
            continue
            
    print(f"Found {len(unique_rows)} bet rows.")
    
    for row in unique_rows:
        try:
            text_content = row.text
            lines = text_content.split('\n')
            
            # Simple parsing based on text structure
            # Example: 
            # "Spread: Texans (-9.5)"
            # "Won 1.9 Chargers at 46¢"
            
            # OR
            # "Spread: Texans (-9.5)"
            # "Lost 212.4 Texans at 52¢"
            
            title = lines[0].strip()
            
            # Parsing status and amount
            # Searching for Won/Lost line
            status = "Unknown"
            amount_str = "0"
            outcome = "Unknown"
            
            full_text = " ".join(lines)
            
            if "Won" in full_text:
                status = "Won"
                wins += 1
                # Parse amount won
                # Usually "Won $100" or "Won 100 USDC" or "Won 1.9 Chargers" ??
                # The screenshot shows: "Won 1.9 Chargers at 46c" -> This implies 1.9 SHARES were won? Or 1.9 $? 
                # "Lost 212.4 Texans at 52c" -> Lost $212.4? or shares?
                # Usually Profit/Loss column shows the $ value.
                # If the text says "Won 1.9 ...", it might be the profit.
                # Let's look for a currency symbol or just parse the number after Won/Lost.
                
                # Regex or split might be needed.
                # Let's try to find the number immediately following "Won" or "Lost".
                parts = full_text.split()
                if "Won" in parts:
                    idx = parts.index("Won")
                    if idx + 1 < len(parts):
                        val_str = parts[idx+1].replace('$', '').replace(',', '')
                        try:
                            val = float(val_str)
                            total_won += val
                            amount_str = str(val)
                        except:
                            pass
                            
                # Outcome extraction
                # In "Won 1.9 Chargers at 46c", "Chargers" is the outcome.
                # In "Spread: Texans (-9.5)", the market is the spread.
                # If I bet on Texans and it says "Won ... Chargers", maybe I bet on Chargers?
                # The screenshot shows "Spread: Texans (-9.5)" and below "Won 1.9 Chargers...". 
                # This implies the market is "Spread: Texans (-9.5)" but the outcome held was "Chargers" (the other side?).
                # Or maybe the market title is just the event name.
                # Let's assume the word after the amount is the outcome, or distinct line.
                
                # We need to capture the specific Outcome Scenario.
                # Screenshot 1: "Spread: Texans (-9.5)" -> "Won 1.9 Chargers at 46c". Outcome: Chargers.
                # Screenshot 2: "Spread: Texans (-9.5)" -> "Lost 212.4 Texans at 52c". Outcome: Texans.
                
                # Heuristic: Outcome is the text between the amount and "at".
                try:
                    # Regex to find "Won <amount> <outcome> at" or "Lost <amount> <outcome> at"
                    match = re.search(r'(Won|Lost)\s+([\d\.,]+)\s+(.*?)\s+at', full_text)
                    if match:
                        amount_str = match.group(2).replace(',', '')
                        outcome = match.group(3)
                        val = float(amount_str)
                        if status == "Won":
                            total_won += val
                        else:
                            total_lost += val
                except Exception as e:
                    print(f"Regex error: {e}")

            elif "Lost" in full_text:
                status = "Lost"
                losses += 1
                # Similar logic for lost
                try:
                    match = re.search(r'(Won|Lost)\s+([\d\.,]+)\s+(.*?)\s+at', full_text)
                    if match:
                        amount_str = match.group(2).replace(',', '') # Amount lost
                        outcome = match.group(3)
                        val = float(amount_str)
                        total_lost += val
                except:
                    pass

            # Track for duplicates
            if title not in bet_history:
                bet_history[title] = []
            
            bet_history[title].append({
                "outcome": outcome,
                "status": status,
                "amount": amount_str
            })
            
        except Exception as e:
            print(f"Error parsing row: {e}")
            continue

    # Analyze duplicates
    duplicates_info = []
    for title, bets in bet_history.items():
        if len(bets) > 1:
            # Check if outcomes differ
            outcomes = set(b['outcome'] for b in bets)
            is_hedged = len(outcomes) > 1
            
            duplicates_info.append({
                "title": title,
                "count": len(bets),
                "outcomes": list(outcomes),
                "hedged": is_hedged,
                "details": bets
            })

    return {
        "wins": wins,
        "losses": losses,
        "total_won": total_won,
        "total_lost": total_lost,
        "duplicates": duplicates_info
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
                         print(f"  Found {len(results['duplicates'])} duplicate bets:")
                         dup_count = len(results['duplicates'])
                         hedged_count = sum(1 for d in results['duplicates'] if d['hedged'])
                         
                         user_stat["Duplicate Bets"] = dup_count
                         user_stat["Hedged Bets"] = hedged_count
                         
                         notes = []
                         for dup in results['duplicates']:
                             hedged_str = " (HEDGED)" if dup['hedged'] else ""
                             print(f"    - '{dup['title']}' appeared {dup['count']} times{hedged_str}")
                             notes.append(f"{dup['title']} (x{dup['count']}){hedged_str}")
                             if dup['hedged']:
                                 print(f"      Outcomes: {', '.join(dup['outcomes'])}")
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

