import os
import time
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

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL") # Sometimes required for verification
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not all([TWITTER_USERNAME, TWITTER_PASSWORD, GEMINI_API_KEY]):
    raise ValueError("Please set TWITTER_USERNAME, TWITTER_PASSWORD, and GEMINI_API_KEY in .env file")

# Configure Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

def setup_driver():
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Uncomment to run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled") # Reduce detection
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Stealth settings
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    
    return driver

def login_twitter(driver):
    print("Logging into Twitter...")
    driver.get("https://x.com/i/flow/login")
    
    # Wait for username field
    username_field = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='username']"))
    )
    username_field.send_keys(TWITTER_USERNAME)
    username_field.send_keys(Keys.RETURN)
    
    # Check for unusual activity check (asking for email/phone)
    try:
        # Short wait to see if it asks for email
        email_field = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='text']"))
        )
        if TWITTER_EMAIL:
            print("Twitter asked for email/phone verification...")
            email_field.send_keys(TWITTER_EMAIL)
            email_field.send_keys(Keys.RETURN)
        else:
            print("Twitter asked for verification but TWITTER_EMAIL is not set.")
    except:
        # Proceed if no email check
        pass
        
    # Wait for password field
    password_field = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='current-password']"))
    )
    password_field.send_keys(TWITTER_PASSWORD)
    password_field.send_keys(Keys.RETURN)
    
    # Wait for home feed or search bar to confirm login
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='AppTabBar_Home_Link']"))
    )
    print("Login successful.")

def search_twitter(driver):
    print("Searching for Polymarket posts...")
    # Search for Polymarket and "80%" or similar terms
    # Using specific query to pre-filter
    query = 'Polymarket "80%" OR "win rate" min_faves:5'
    encoded_query = query.replace(" ", "%20").replace('"', '%22')
    search_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live" # f=live for latest
    
    driver.get(search_url)
    time.sleep(5)  # Allow initial load

def scroll_feed(driver, num_scrolls=5):
    print(f"Scrolling feed {num_scrolls} times...")
    body = driver.find_element(By.TAG_NAME, "body")
    for _ in range(num_scrolls):
        body.send_keys(Keys.END)
        time.sleep(4)  # Wait for content to load (Twitter can be slower)

def extract_tweets(driver):
    print("Extracting tweets...")
    tweets_data = []
    
    # Find all tweet articles
    articles = driver.find_elements(By.CSS_SELECTOR, "article[data-testid='tweet']")
    print(f"Found {len(articles)} potential tweets.")
    
    for article in articles:
        try:
            # Extract Text
            try:
                text_element = article.find_element(By.CSS_SELECTOR, "div[data-testid='tweetText']")
                text = text_element.text
            except:
                text = ""
            
            if not text:
                continue

            # Extract Author
            try:
                user_element = article.find_element(By.CSS_SELECTOR, "div[data-testid='User-Name']")
                author = user_element.text.replace("\n", " ")
            except:
                author = "Unknown"

            # Extract Link
            try:
                # The time element usually links to the status
                time_element = article.find_element(By.TAG_NAME, "time")
                link_element = time_element.find_element(By.XPATH, "..")
                post_url = link_element.get_attribute("href")
            except:
                post_url = "Unknown"

            tweets_data.append({
                "author": author,
                "text": text,
                "url": post_url
            })
            
        except Exception as e:
            continue
            
    return tweets_data

def validate_with_gemini(post_text):
    prompt = f"""
    Analyze the following Twitter post and determine if it meets these criteria:
    1. It is related to a Polymarket user or trader.
    2. It mentions a win rate, success rate, or similar metric that is greater than 80% (or implies a very high success rate).

    Post Text:
    "{post_text}"

    Respond with ONLY "TRUE" if it meets both criteria, or "FALSE" if it does not.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview', 
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
        login_twitter(driver)
        search_twitter(driver)
        scroll_feed(driver, num_scrolls=8)
        
        raw_tweets = extract_tweets(driver)
        
        # Additional keyword filtering (optional since we used search query, but good as backup)
        keywords = ["80%", "rate", "win", "profit"]
        keyword_filtered = [
            p for p in raw_tweets 
            if any(k in p['text'].lower() for k in keywords)
        ]
        print(f"Retained {len(keyword_filtered)} tweets after initial filtering.")
        
        final_posts = []
        print("Validating with Gemini...")
        for post in keyword_filtered:
            if validate_with_gemini(post['text']):
                print(f"Found match: {post['author']}")
                final_posts.append(post)
            else:
                pass
        
        # Save to CSV
        if final_posts:
            output_file = "backend/twitter_high_rate_posts.csv"
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

