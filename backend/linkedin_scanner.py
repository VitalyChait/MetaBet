import os
import time
import csv
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from google import genai

# Load environment variables
load_dotenv()

LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not all([LINKEDIN_USERNAME, LINKEDIN_PASSWORD, GEMINI_API_KEY]):
    raise ValueError("Please set LINKEDIN_USERNAME, LINKEDIN_PASSWORD, and GEMINI_API_KEY in .env file")

# Configure Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Uncomment to run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def login_linkedin(driver):
    print("Logging into LinkedIn...")
    driver.get("https://www.linkedin.com/login")
    
    username_field = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "username"))
    )
    username_field.send_keys(LINKEDIN_USERNAME)
    
    password_field = driver.find_element(By.ID, "password")
    password_field.send_keys(LINKEDIN_PASSWORD)
    password_field.send_keys(Keys.RETURN)
    
    # Wait for login to complete (check for search bar or home feed)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "global-nav-search"))
    )
    print("Login successful.")

def search_polymarket_posts(driver):
    print("Searching for Polymarket posts...")

    base_url = "https://www.linkedin.com/search/results/content/"

    date_posted = '"past-month"' # past-week, past-month, past-year
    date_selection = "?" if not date_posted else "?datePosted=" + date_posted

    search_term = ["polymarket", "whale", "win"]
    keywords_selection = "keywords=" + "%20".join(search_term)

    extra_selection = 'sortBy="date_posted"&origin=SWITCH_SEARCH_VERTICAL'




    search_url = base_url + date_selection + "&" + keywords_selection + "&" + extra_selection
    driver.get(search_url)
    time.sleep(5)  # Allow initial load

def scroll_feed(driver, num_scrolls=5):
    print(f"Scrolling feed {num_scrolls} times...")
    body = driver.find_element(By.TAG_NAME, "body")
    for _ in range(num_scrolls):
        body.send_keys(Keys.END)
        time.sleep(3)  # Wait for content to load

def extract_posts(driver):
    print("Extracting posts...")
    posts_data = []
    
    # Locate post containers (selectors might change, these are common LinkedIn selectors)
    # Using a broad selector and then narrowing down
    post_elements = driver.find_elements(By.CSS_SELECTOR, "div.update-components-text")
    
    # We need to find the parent container to get author and link
    # This part is tricky as LinkedIn structure is complex and dynamic.
    # A more robust way is to find the main feed list items.
    
    # Alternative strategy: Find all feed items
    feed_items = driver.find_elements(By.CSS_SELECTOR, "div.feed-shared-update-v2")
    
    print(f"Found {len(feed_items)} potential posts.")
    
    for item in feed_items:
        try:
            # Extract Text
            try:
                text_element = item.find_element(By.CSS_SELECTOR, "div.update-components-text span.break-words")
                text = text_element.text
            except:
                text = ""
            
            if not text:
                continue

            # Extract Author
            try:
                author_element = item.find_element(By.CSS_SELECTOR, "span.update-components-actor__name span[aria-hidden='true']")
                author = author_element.text
            except:
                author = "Unknown"

            # Extract Post Link
            # Usually found in the '...' menu or by clicking 'copy link', but sometimes the date is a link
            try:
                # The timestamp/date is usually a link to the post
                link_element = item.find_element(By.CSS_SELECTOR, "a.update-components-actor__sub-description")
                # Or sometimes class update-components-actor__meta-link
                if not link_element.get_attribute("href"):
                     link_element = item.find_element(By.CSS_SELECTOR, "a.app-aware-link") # Fallback
                
                post_url = link_element.get_attribute("href")
            except:
                post_url = "Unknown"

            posts_data.append({
                "author": author,
                "text": text,
                "url": post_url
            })
            
        except Exception as e:
            # print(f"Error parsing a post: {e}")
            continue
            
    return posts_data

def filter_with_keywords(posts):
    print("Filtering by keywords...")
    filtered = []
    keywords = ["80%", "rate", "win rate", "success rate", "profit"]
    
    for post in posts:
        text_lower = post['text'].lower()
        if any(keyword in text_lower for keyword in keywords):
            filtered.append(post)
            
    print(f"Retained {len(filtered)} posts after keyword filtering.")
    return filtered

def validate_with_gemini(post_text):
    prompt = f"""
    Analyze the following LinkedIn post and determine if it meets these criteria:
    1. It is related to a Polymarket user or trader.
    2. It mentions a win rate, success rate, or similar metric that is greater than 80%.

    Post Text:
    "{post_text}"

    Respond with ONLY "TRUE" if it meets both criteria, or "FALSE" if it does not.
    """
    
    try:
        response = client.models.generate_content(
            model='	gemini-3-flash-preview', 
            contents=prompt
        )
        result = response.text.strip().upper()
        return "TRUE" in result
    except Exception as e:
        print(f"Gemini API error: {e}")
        return False

def main():
    driver = setup_driver()
    try:
        login_linkedin(driver)
        search_polymarket_posts(driver)
        scroll_feed(driver, num_scrolls=20) # Adjust scrolls as needed
        
        raw_posts = extract_posts(driver)
        keyword_filtered_posts = filter_with_keywords(raw_posts)
        
        final_posts = []
        print("Validating with Gemini...")
        for post in keyword_filtered_posts:
            if validate_with_gemini(post['text']):
                print(f"Found match: {post['author']}")
                final_posts.append(post)
            else:
                # print(f"Rejected by Gemini: {post['text'][:50]}...")
                pass
        
        # Save to CSV
        if final_posts:
            output_file = "backend/polymarket_high_rate_posts.csv"
            df = pd.DataFrame(final_posts)
            df.to_csv(output_file, index=False)
            print(f"Saved {len(final_posts)} posts to {output_file}")
        else:
            print("No matching posts found.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
