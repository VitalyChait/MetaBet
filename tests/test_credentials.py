import os
import sys
from dotenv import load_dotenv
from google import genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Ensure backend module can be imported if needed, or we just replicate minimal logic
# sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

def env_vars():
    """Validates that environment variables are present."""
    linkedin_user = os.getenv("LINKEDIN_USERNAME")
    linkedin_pass = os.getenv("LINKEDIN_PASSWORD")
    gemini_key = os.getenv("GEMINI_API_KEY")
    twitter_user = os.getenv("TWITTER_USERNAME")
    twitter_pass = os.getenv("TWITTER_PASSWORD")
    
    missing = []
    if not linkedin_user: missing.append("LINKEDIN_USERNAME")
    if not linkedin_pass: missing.append("LINKEDIN_PASSWORD")
    if not gemini_key: missing.append("GEMINI_API_KEY")
    if not twitter_user: missing.append("TWITTER_USERNAME")
    if not twitter_pass: missing.append("TWITTER_PASSWORD")
    
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        
    return {
        "LINKEDIN_USERNAME": linkedin_user,
        "LINKEDIN_PASSWORD": linkedin_pass,
        "GEMINI_API_KEY": gemini_key,
        "TWITTER_USERNAME": twitter_user,
        "TWITTER_PASSWORD": twitter_pass,
        "TWITTER_EMAIL": os.getenv("TWITTER_EMAIL")
    }

def test_gemini_api_connection(env_vars):
    """
    Tests the Gemini API key by making a simple generation request.
    """
    print("\nTesting Gemini API connection...")
    client = genai.Client(api_key=env_vars["GEMINI_API_KEY"])
    
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview', 
            contents="Say 'Hello' if you can read this."
        )
        assert response is not None
        assert response.text is not None
        print("Gemini API connection successful.")
    except Exception as e:
        raise Exception(f"Gemini API test failed: {str(e)}")

import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Test timed out after 30 seconds")

def with_timeout(func):
    def wrapper(*args, **kwargs):
        # Set signal handler for SIGALRM
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)  # Set alarm for 30 seconds
        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)  # Disable alarm
    return wrapper

@with_timeout
def test_linkedin_login(env_vars):
    """
    Tests LinkedIn login credentials using Selenium.
    Note: This test opens a browser.
    """
    print("\nTesting LinkedIn login...")
    
    # Setup Driver (Headless recommended for CI, but maybe headful for debugging?)
    # Using headless to avoid interrupting user, but user asked to check if THEY can log in.
    options = webdriver.ChromeOptions()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Suppress logging
    options.add_argument("--log-level=3")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get("https://www.linkedin.com/login")
        
        # Enter Username
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        username_field.send_keys(env_vars["LINKEDIN_USERNAME"])
        
        # Enter Password
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(env_vars["LINKEDIN_PASSWORD"])
        password_field.send_keys(Keys.RETURN)
        
        # Check for successful login indicators
        # 1. URL change (usually goes to /feed)
        # 2. Search bar presence
        # 3. Absence of error message
        
        try:
            # Wait for either the search bar (success) or an error message (failure)
            WebDriverWait(driver, 15).until(
                lambda d: 
                d.find_elements(By.ID, "global-nav-search") or 
                d.find_elements(By.ID, "error-for-username") or
                d.find_elements(By.ID, "error-for-password") or
                d.find_elements(By.CLASS_NAME, "login__form_action_container") # sometimes captcha/challenge
            )
            
            # Check if we are logged in
            if driver.find_elements(By.ID, "global-nav-search") or "feed" in driver.current_url:
                print("LinkedIn login successful.")
            else:
                # Check for specific errors
                error_user = driver.find_elements(By.ID, "error-for-username")
                error_pass = driver.find_elements(By.ID, "error-for-password")
                
                if error_user:
                    raise Exception(f"Login failed: {error_user[0].text}")
                elif error_pass:
                    raise Exception(f"Login failed: {error_pass[0].text}")
                else:
                    # Captcha or challenge or unhandled state
                    raise Exception("Login failed or required manual verification (CAPTCHA/Challenge).")
                    
        except Exception as e:
            raise Exception(f"Timeout waiting for login response or error: {str(e)}")
            
    finally:
        driver.quit()

@with_timeout
def test_twitter_login(env_vars):
    """
    Tests Twitter login credentials using Selenium.
    """
    print("\nTesting Twitter login...")
    
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless") # Twitter often blocks headless
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get("https://x.com/i/flow/login")
        
        # Username
        username_field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='username']"))
        )
        username_field.send_keys(env_vars["TWITTER_USERNAME"])
        username_field.send_keys(Keys.RETURN)
        
        # Check for email challenge
        try:
            # Short wait for email field or password field
            WebDriverWait(driver, 5).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "input[name='text']") or
                          d.find_elements(By.CSS_SELECTOR, "input[autocomplete='current-password']")
            )
            
            email_fields = driver.find_elements(By.CSS_SELECTOR, "input[name='text']")
            if email_fields:
                print("Twitter asked for verification info...")
                if env_vars.get("TWITTER_EMAIL"):
                    email_fields[0].send_keys(env_vars["TWITTER_EMAIL"])
                    email_fields[0].send_keys(Keys.RETURN)
                else:
                    raise Exception("Twitter requested email verification but none provided.")
        except Exception:
            pass
            
        # Password
        password_field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='current-password']"))
        )
        password_field.send_keys(env_vars["TWITTER_PASSWORD"])
        password_field.send_keys(Keys.RETURN)
        
        # Check success
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='AppTabBar_Home_Link']"))
            )
            print("Twitter login successful.")
        except:
            raise Exception("Twitter login failed or timed out waiting for home screen.")
            
    finally:
        driver.quit()


if __name__ == "__main__":
    env_vars = env_vars()
    test_gemini_api_connection(env_vars)
    test_linkedin_login(env_vars)
    test_twitter_login(env_vars)