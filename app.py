#Import libraries and modules
from flask import Flask, render_template, request, jsonify
import threading
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, WebDriverException, NoSuchElementException
import time
import os
import imaplib
import email
import re
import shutil
import subprocess
from dotenv import load_dotenv
from typing import Optional
from groq import Groq
import datetime
import json
import warnings

# Flask app
app = Flask(__name__)
app.secret_key = 'volza_secret_key'

# Add timeout configuration
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Add this CORS handler
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Global state (replaces Streamlit session_state)
state = {
    'logged_in': False,
    'username': "",
    'analysis_complete': False,
    'chat_history': [],
    'company_name': "",
    'product_name': "",
    'extracted_data': "",
    'driver': None,
    'browser_logged_in': False,
    'wait': None,
    'status': "",
    'progress': 0
}

# Suppress warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# ==================== LOAD .env SECURELY (FIRST) ====================
load_dotenv()

# ==================== SECURE CREDENTIALS FROM .env ====================
VALID_USERNAME = os.getenv("VALID_USERNAME")
VALID_PASSWORD = os.getenv("VALID_PASSWORD")
LOGIN_EMAIL = os.getenv("LOGIN_EMAIL", "patel@globalkemya.com")
APP_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL = os.getenv("EMAIL")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = os.getenv("IMAP_PORT", 993)
OTP_SENDER_EMAIL = os.getenv("OTP_SENDER_EMAIL", "noreply@volza.com")
OTP_SUBJECT_KEYWORD = os.getenv("OTP_SUBJECT_KEYWORD", "Your OTP for Secure Login")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Validate critical credentials
missing_creds = []
if not VALID_USERNAME: missing_creds.append("VALID_USERNAME")
if not VALID_PASSWORD: missing_creds.append("VALID_PASSWORD") 
if not GROQ_API_KEY: missing_creds.append("GROQ_API_KEY")

if missing_creds:
    print(f"🚨 Missing credentials in .env: {', '.join(missing_creds)}")
    raise ValueError("Missing credentials")

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

# ==================== CONFIGURATION ====================
HISTORY_FILE = "company_analyses.json"
DATA_FILE = "data.txt"
EXTRACTED_DATA_FILE = "extracted_data.txt"
# 🚀 FASTER MODEL
LLAMA4_MODEL = "moonshotai/kimi-k2-instruct-0905"

print(f"✅ Credentials loaded: {VALID_USERNAME[:4]}****")

# ==================== AUTO-UPDATE CHROMEDRIVER FUNCTION ====================
def get_chrome_version():
    """Detect installed Chrome version on Windows"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        winreg.CloseKey(key)
        return version.split('.')[0]
    except:
        pass
    
    try:
        result = subprocess.run(
            ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[-1]
            return version.split('.')[0]
    except:
        pass
    
    return None

def clear_uc_cache():
    """Clear undetected_chromedriver cache to force fresh driver download"""
    cache_paths = [
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "undetected_chromedriver"),
        os.path.join(os.path.expanduser("~"), ".local", "share", "undetected_chromedriver"),
        os.path.join(os.path.expanduser("~"), "appdata", "roaming", "undetected_chromedriver"),
    ]
    
    for cache_path in cache_paths:
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
                print(f"✅ Cleared UC cache: {cache_path}")
            except Exception as e:
                print(f"⚠️ Could not clear cache {cache_path}: {e}")

def get_uc_driver_with_auto_update(chrome_options=None, max_retries=2):
    """
    Get undetected_chromedriver with automatic version handling.
    🚀 OPTIMIZED: Persistent profile + No images
    """
    import undetected_chromedriver as uc
    
    if chrome_options is None:
        chrome_options = uc.ChromeOptions()
    
    # 🚀 PERSISTENT PROFILE (saves login forever)
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument("--profile-directory=Default")
    
    # 🚀 DISABLE IMAGES (faster loading)
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    })
    
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    chrome_version = get_chrome_version()
    print(f"🔍 Detected Chrome version: {chrome_version}")
    
    for attempt in range(max_retries):
        try:
            if chrome_version:
                driver = uc.Chrome(
                    options=chrome_options,
                    version_main=int(chrome_version)
                )
            else:
                driver = uc.Chrome(options=chrome_options)
            
            print(f"✅ ChromeDriver initialized successfully!")
            return driver
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "version" in error_msg or "chromedriver" in error_msg or "session not created" in error_msg:
                print(f"⚠️ Attempt {attempt + 1}: ChromeDriver version mismatch detected")
                print(f"🔄 Clearing cache and retrying...")
                clear_uc_cache()
                time.sleep(2)
                
                if attempt == max_retries - 1:
                    print(f"❌ Failed after {max_retries} attempts: {e}")
                    raise
            else:
                raise
    
    raise Exception("Failed to initialize ChromeDriver after all retries")


# ==================== HELPER FUNCTIONS ====================
def scream_message(message):
    """Play voice message"""
    if os.name == 'nt':
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = 2
            speaker.Volume = 100
            speaker.Speak(message)
        except:
            pass


def load_history():
    """Load analysis history from JSON"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_history(history):
    """Save analysis history to JSON"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_company_analysis(company_name: str, product_name: str, extracted_data: str):
    """Save company analysis to history"""
    history = load_history()
    
    history[company_name.lower()] = {
        "company_name": company_name,
        "product_searched": product_name,
        "analysis_date": datetime.datetime.now().isoformat(),
        "extracted_data": extracted_data
    }
    
    save_history(history)
    print(f"✅ Saved analysis for {company_name}")


def load_company_analysis(company_name: str) -> dict:
    """Load previous analysis if exists"""
    history = load_history()
    return history.get(company_name.lower())


def reset_zoom(driver):
    """Reset page zoom to 100% safely (used after zooming out for capture)."""
    try:
        driver.execute_script("document.body.style.zoom='100%';")
        driver.execute_script("""
            if (document.documentElement && document.documentElement.style) {
                document.documentElement.style.zoom = '100%';
            }
        """)
        time.sleep(0.3)
    except Exception as e:
        print(f"⚠️ reset_zoom failed: {e}")


# ==================== EXPERT ERROR HANDLING WRAPPERS ====================
def safe_click(driver, by, value, wait_time=30, description="element"):
    """Expert-level safe click with multiple retry strategies"""
    wait = WebDriverWait(driver, wait_time)
    
    for attempt in range(3):
        try:
            print(f"Attempt {attempt + 1}: Finding {description}...")
            element = wait.until(EC.element_to_be_clickable((by, value)))
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(0.3)
            
            try:
                element.click()
                print(f"✅ Clicked {description} (normal click)")
                return element
            except:
                driver.execute_script("arguments[0].click();", element)
                print(f"✅ Clicked {description} (JS click)")
                return element
                
        except TimeoutException:
            if attempt < 2:
                print(f"⚠️ Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(1)
            else:
                print(f"❌ Failed to find {description} after 3 attempts")
                raise
        except StaleElementReferenceException:
            if attempt < 2:
                print(f"⚠️ Stale element on attempt {attempt + 1}, retrying...")
                time.sleep(0.5)
            else:
                raise
    
    raise Exception(f"Failed to click {description} after all retry attempts")


def safe_find_and_send(driver, by, value, text, wait_time=30, description="input field"):
    """Expert-level safe find and send keys"""
    wait = WebDriverWait(driver, wait_time)
    
    for attempt in range(3):
        try:
            print(f"Attempt {attempt + 1}: Finding {description}...")
            element = wait.until(EC.presence_of_element_located((by, value)))
            element.clear()
            time.sleep(0.2)
            element.send_keys(text)
            print(f"✅ Sent text to {description}")
            return element
            
        except TimeoutException:
            if attempt < 2:
                print(f"⚠️ Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(1)
            else:
                print(f"❌ Failed to find {description} after 3 attempts")
                raise
        except StaleElementReferenceException:
            if attempt < 2:
                print(f"⚠️ Stale element on attempt {attempt + 1}, retrying...")
                time.sleep(0.5)
            else:
                raise
    
    raise Exception(f"Failed to interact with {description} after all retry attempts")


def wait_for_url_change(driver, old_url, timeout=60, description="URL change"):
    """Wait for URL to change with better error handling"""
    print(f"Waiting for {description}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        current_url = driver.current_url
        if current_url != old_url:
            print(f"✅ {description} detected: {current_url}")
            return current_url
        time.sleep(0.3)
    
    raise TimeoutException(f"Timeout waiting for {description}")


# ==================== IMPROVED COMPANY NAME EXTRACTION ====================
def extract_company_name_from_page(driver):
    """Extract company name using multiple strategies"""
    company_name = None
    
    try:
        company_text_element = driver.find_element(
            By.XPATH,
            "//tr[@data-row-key='0']//span[@class='blue-link-color']"
        )
        full_text = company_text_element.text.strip()
        if "All Company Start from" in full_text:
            company_name = full_text.replace("All Company Start from", "").strip()
        elif full_text:
            company_name = full_text
        if company_name:
            print(f"✅ Strategy 1: Found company name: {company_name}")
            return company_name
    except Exception as e:
        print(f"⚠️ Strategy 1 failed: {e}")
    
    try:
        search_criteria = driver.find_elements(By.XPATH, "//span[contains(@class, 'ant-tag')]")
        for tag in search_criteria:
            text = tag.text.strip()
            if text and len(text) > 3 and not text.startswith("HS") and not text.isdigit():
                company_name = text
                print(f"✅ Strategy 2: Found company name from tag: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 2 failed: {e}")
    
    try:
        headers = driver.find_elements(By.XPATH, "//h1 | //h2 | //h3 | //h4")
        for header in headers:
            text = header.text.strip()
            if text and len(text) > 3 and "volza" not in text.lower() and "search" not in text.lower():
                company_name = text
                print(f"✅ Strategy 3: Found company name from header: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 3 failed: {e}")
    
    try:
        table_cells = driver.find_elements(By.XPATH, "//td[contains(@class, 'ant-table-cell')]//a")
        for cell in table_cells[:5]:
            text = cell.text.strip()
            if text and len(text) > 3:
                company_name = text
                print(f"✅ Strategy 4: Found company name from table: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 4 failed: {e}")
    
    try:
        current_url = driver.current_url
        if "company=" in current_url or "q=" in current_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(current_url)
            params = urllib.parse.parse_qs(parsed.query)
            if 'company' in params:
                company_name = params['company'][0]
            elif 'q' in params:
                company_name = params['q'][0]
            if company_name:
                print(f"✅ Strategy 5: Found company name from URL: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 5 failed: {e}")
    
    try:
        breadcrumbs = driver.find_elements(By.XPATH, "//nav//a | //ol//li//a | //ul[contains(@class, 'breadcrumb')]//a")
        for crumb in breadcrumbs:
            text = crumb.text.strip()
            if text and len(text) > 3 and "home" not in text.lower() and "search" not in text.lower():
                company_name = text
                print(f"✅ Strategy 6: Found company name from breadcrumb: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 6 failed: {e}")
    
    try:
        prominent_elements = driver.find_elements(By.XPATH, 
            "//*[contains(@class, 'company') or contains(@class, 'title') or contains(@class, 'name')]"
        )
        for elem in prominent_elements[:10]:
            text = elem.text.strip()
            if text and len(text) > 3 and len(text) < 100:
                company_name = text.split('\n')[0]
                print(f"✅ Strategy 7: Found company name from prominent element: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 7 failed: {e}")
    
    print("❌ All strategies failed to extract company name")
    return None


def extract_company_name_from_text(page_text):
    """Extract company name from page text using regex"""
    patterns = [
        r"Company:\s*([A-Z][A-Za-z0-9\s\.\,\&\-]+(?:LTD|LLC|INC|CORP|CO|PVT|PRIVATE|LIMITED|CORPORATION|COMPANY)?)",
        r"Consignee:\s*([A-Z][A-Za-z0-9\s\.\,\&\-]+(?:LTD|LLC|INC|CORP|CO|PVT|PRIVATE|LIMITED|CORPORATION|COMPANY)?)",
        r"Shipper:\s*([A-Z][A-Za-z0-9\s\.\,\&\-]+(?:LTD|LLC|INC|CORP|CO|PVT|PRIVATE|LIMITED|CORPORATION|COMPANY)?)",
        r"([A-Z][A-Z\s\.\,\&\-]{5,50}(?:LTD|LLC|INC|CORP|CO|PVT|PRIVATE|LIMITED|CORPORATION|COMPANY))",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, page_text[:5000], re.IGNORECASE)
        if matches:
            company_name = matches[0].strip()
            if len(company_name) > 3:
                print(f"✅ Found company name from text: {company_name}")
                return company_name
    
    return None


def extract_detailed_info_with_ai(full_page_text: str, company_name: str, product_name: str) -> str:
    """
    🎯 FOCUSED: Quick assessment of supplier legitimacy
    """
    
    # Concise extraction prompt
    extraction_prompt = f"""Analyze trade data for {company_name} trading {product_name}.

FULL PAGE TEXT:
{full_page_text[:15000]}

Extract ONLY:
1. Total number of consignees (buyers)
2. List of destination countries
3. Total shipments count
4. Date range of shipments"""

    try:
        print("🔍 Extracting key trade data...")
        
        extraction_response = client.chat.completions.create(
            model=LLAMA4_MODEL,
            messages=[
                {"role": "system", "content": "You are a data extraction specialist. Extract only the specific information requested."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=0.3,
            max_completion_tokens=1500,
            stream=False
        )
        
        raw_data = extraction_response.choices[0].message.content.strip()
        print("✅ Raw data extracted")
        
        # Focused analysis prompt
        analysis_prompt = f"""You are analyzing supplier {company_name} for {product_name}.

EXTRACTED DATA:
{raw_data}

ANSWER THIS CRITICAL QUESTION:

**Has this manufacturer supplied the same product to MULTIPLE countries and MULTIPLE consignees?**

Respond in this EXACT format:

---

## 🎯 CRITICAL QUESTION & ANSWER

**Question:** Has {company_name} supplied {product_name} to MULTIPLE countries and MULTIPLE consignees?

**Answer:** [YES or NO]

**Reason:**
[In 2-3 sentences explain why - include specific numbers: how many consignees, how many countries, shipment count]

---

## 📊 Quick Facts

- **Total Consignees (Buyers):** [number]
- **Countries Served:** [list all countries]
- **Total Shipments:** [number]
- **Date Range:** [earliest to latest]

---

## ✅ Legitimacy Assessment

**Status:** [LEGITIMATE / SUSPICIOUS / INSUFFICIENT DATA]

**Why:**
[2-3 sentences: If multiple countries + multiple buyers = legitimate international supplier. If only 1-2 buyers or 1 country = potential red flag]

---

## 🚨 Red Flags (if any)

[List any concerning patterns in 1-2 bullet points, or write "None detected"]

---

## 💡 Quick Recommendation

[1-2 sentences: Should they proceed with verification? What's the next step?]

---

CRITICAL INSTRUCTIONS:
1. Be DIRECT and CONCISE
2. Use actual numbers from the data
3. If data shows multiple countries + multiple consignees → Answer is YES
4. If data shows limited trading → Answer is NO
5. Keep total response under 300 words
"""

        print("🤖 Generating focused analysis...")
        
        analysis_response = client.chat.completions.create(
            model=LLAMA4_MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a Senior Trade Analyst. Provide CONCISE, DIRECT answers with specific numbers. No fluff."
                },
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.5,
            max_completion_tokens=1200,
            stream=False
        )
        
        intelligent_analysis = analysis_response.choices[0].message.content.strip()
        print("✅ Focused analysis complete")
        
        return intelligent_analysis
        
    except Exception as e:
        print(f"❌ Error generating analysis: {e}")
        return f"""## ❌ Analysis Error

Error: {e}

**Raw Data (if available):**
{raw_data if 'raw_data' in locals() else 'No data extracted'}

Please try again."""


def query_company_data_direct(query: str, company_name: str, extracted_data: str) -> str:
    """
    🚀 DIRECT AI QUERY - No RAG needed!
    Much faster and simpler for single company analysis
    """
    try:
        print(f"\n🔍 Direct query for company: '{company_name}'")
        
        prompt = f"""You are a Senior International Trade Intelligence Expert analyzing {company_name}.

COMPLETE EXTRACTED DATA:
{extracted_data}

USER QUESTION: {query}

INSTRUCTIONS:
1. Answer ONLY using the data provided above about {company_name}
2. Be specific - use actual names, numbers, dates from the data
3. Provide actionable insights and analysis
4. If information isn't in the data, say so clearly
5. Focus on {company_name} only - do not mention other companies

ANSWER:"""

        completion = client.chat.completions.create(
            model=LLAMA4_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a Senior International Trade Intelligence Expert. You ONLY provide information about {company_name}. Use only the provided data."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_completion_tokens=1500,
            stream=False
        )
        
        answer = completion.choices[0].message.content.strip()
        print("✅ Direct query complete")
        return answer
        
    except Exception as e:
        print(f"❌ Error in query: {e}")
        return f"❌ Error querying data: {e}"


def fetch_latest_otp(sender_email: str, subject_keyword: str, max_attempts: int = 3, wait_between_attempts: int = 5) -> Optional[str]:
    if not all([APP_PASSWORD, EMAIL, IMAP_SERVER, IMAP_PORT]):
        return None

    for attempt in range(1, max_attempts + 1):
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, int(IMAP_PORT))
            mail.login(EMAIL, APP_PASSWORD)
            mail.select("inbox")
            
            search_criteria = f'(FROM "{sender_email}" SUBJECT "{subject_keyword}" UNSEEN)'
            status, messages = mail.search(None, search_criteria)
            
            if status != 'OK' or not messages[0]:
                search_criteria = f'(FROM "{sender_email}" SUBJECT "{subject_keyword}")'
                status, messages = mail.search(None, search_criteria)
            
            if status != 'OK' or not messages[0]:
                mail.logout()
                if attempt < max_attempts:
                    time.sleep(wait_between_attempts)
                continue
            
            latest_message_id = messages[0].split()[-1]
            status, msg_data = mail.fetch(latest_message_id, '(RFC822)')
            
            if status != 'OK':
                mail.logout()
                continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            email_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get_content_disposition())
                    if ctype in ["text/plain", "text/html"] and "attachment" not in cdispo:
                        email_body = part.get_payload(decode=True).decode()
                        break
            else:
                email_body = msg.get_payload(decode=True).decode()
            
            patterns = [r'(\d{6})', r'OTP[:\s]+(\d+)', r'code[:\s]+(\d+)']
            otp_code = None
            for pattern in patterns:
                otp_match = re.search(pattern, email_body, re.IGNORECASE)
                if otp_match:
                    otp_code = otp_match.group(1)
                    break
            
            mail.logout()
            
            if otp_code:
                return otp_code
            else:
                if attempt < max_attempts:
                    time.sleep(wait_between_attempts)
                continue
                
        except Exception as e:
            if attempt < max_attempts:
                time.sleep(wait_between_attempts)
            continue
    
    return None
# ==================== MAIN AUTOMATION FUNCTIONS ====================
def run_volza_automation(product_name):
    """Main automation - FIRST TIME WITH LOGIN"""
    
    driver = None
    wait = None
    
    try:
        state['status'] = "🤖 Initializing Chrome browser (AUTO-UPDATE ENABLED)..."
        state['progress'] = 10
        
        import undetected_chromedriver as uc
        
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        driver = get_uc_driver_with_auto_update(chrome_options=options)
        
        driver.implicitly_wait(15)
        driver.maximize_window()
        wait = WebDriverWait(driver, 60)
        
        state['status'] = "🌐 Navigating to Volza..."
        state['progress'] = 20
        driver.get("https://app.volza.com/workspace/search/0")
        time.sleep(2)
        
        # Login
        state['status'] = "🔐 Logging in..."
        state['progress'] = 30
        
        safe_find_and_send(driver, By.NAME, "emailAddress", LOGIN_EMAIL, wait_time=30, description="Email field")
        time.sleep(0.5)
        
        safe_click(driver, By.XPATH, "//div[@class='child-sign-up-button' and text()='Send OTP']", wait_time=30, description="Send OTP button")
        time.sleep(1)
        
        safe_click(driver, By.CLASS_NAME, "next-btn-swal", wait_time=30, description="OK button")
        time.sleep(1)
        
        # Close SVG popup
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//svg[@stroke='currentColor' and @height='20' and @width='20']"))
            )
            popup = driver.find_element(By.XPATH, "//svg[@stroke='currentColor' and @height='20' and @width='20']")
            driver.execute_script("arguments[0].click();", popup)
            print("✅ Closed SVG popup")
        except:
            print("ℹ️ No SVG popup found")
        
        time.sleep(0.5)
        
        # Get OTP
        state['status'] = "📧 Retrieving OTP..."
        otp_code = fetch_latest_otp(OTP_SENDER_EMAIL, OTP_SUBJECT_KEYWORD)
        
        if otp_code:
            safe_find_and_send(driver, By.NAME, "password", otp_code, wait_time=30, description="OTP field")
            time.sleep(1)
        else:
            state['status'] = "⚠️ Could not retrieve OTP. Please enter manually."
            time.sleep(15)
        
        # Sign In
        login_page_url = driver.current_url
        safe_click(driver, By.XPATH, "//div[@class='child-sign-up-button' and text()='Sign In']", wait_time=30, description="Sign In button")
        
        wait_for_url_change(driver, login_page_url, timeout=60, description="Login redirect")
        time.sleep(1)
        
        # Select company
        company_select_url = driver.current_url
        safe_click(driver, By.XPATH, "//button[contains(text(), 'Global Kemya India Llp')]", wait_time=30, description="Company selection")
        
        wait_for_url_change(driver, company_select_url, timeout=60, description="Company selection redirect")
        
        state['status'] = "✅ Login successful!"
        state['progress'] = 50
        time.sleep(2)
        
        # Setup search
        state['status'] = "🔧 Setting up search..."
        
        safe_click(driver, By.XPATH, "//span[@class='ml10 main-header-text' and text()='New Search']", wait_time=30, description="New Search button")
        time.sleep(2)
        
        safe_click(driver, By.XPATH, "//span[text()='Select Country']", wait_time=30, description="Select Country dropdown")
        time.sleep(0.5)
        
        safe_click(driver, By.XPATH, "//span[@class='country-name' and text()='All Country (Global Search)']", wait_time=30, description="Global Search option")
        time.sleep(1)
        
        # Date range
        period_dropdown = driver.find_element(By.ID, "periodList")
        period_dropdown.send_keys("Custom")
        time.sleep(0.5)
        
        start_date_input = driver.find_element(By.ID, "globalDataFromDate")
        start_date_input.send_keys(Keys.CONTROL, 'a', Keys.BACK_SPACE)
        start_date_input.send_keys("01/01/2019")
        time.sleep(0.5)
        
        # Search field
        search_field_dropdown = driver.find_element(By.NAME, "field")
        Select(search_field_dropdown).select_by_value("GlobalCompany")
        time.sleep(1)
        
        # WAIT FOR USER INPUT
        state['status'] = "⏸️ PLEASE ENTER COMPANY NAME IN BROWSER"
        scream_message("PLEASE ENTER COMPANY NAME")
        state['progress'] = 60
        
        state['status'] = "⳿ Waiting for you to click 'Apply' button..."
        
        max_wait_time = 300
        start_wait = time.time()
        
        while True:
            try:
                search_button = driver.find_element(By.XPATH, "//button[contains(@class, 'custom-search') and text()='Search']")
                if search_button.is_displayed() and search_button.is_enabled():
                    print("✅ Apply button clicked")
                    break
            except:
                pass
            
            if time.time() - start_wait > max_wait_time:
                state['status'] = "❌ Timeout waiting for Apply button click"
                return
            time.sleep(1)
        
        # Extract company name
        state['status'] = "🔍 Extracting company name..."
        company_name = extract_company_name_from_page(driver)
        
        if not company_name:
            try:
                visible_text = driver.find_element(By.TAG_NAME, 'body').text[:3000]
                company_name = extract_company_name_from_text(visible_text)
            except:
                pass
        
        if not company_name:
            state['status'] = "⚠️ Could not auto-detect company name."
            time.sleep(2)
            company_name = extract_company_name_from_page(driver)
        
        if company_name:
            state['company_name'] = company_name
        else:
            try:
                first_result = driver.find_element(By.XPATH, "//table//tr[2]//td[1]")
                company_name = first_result.text.strip()
                if company_name:
                    state['company_name'] = company_name
                else:
                    state['company_name'] = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            except:
                state['company_name'] = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        state['status'] = f"✅ Company detected: {state['company_name']}"
        state['progress'] = 70
        
        # Click Search
        state['status'] = "🔍 Clicking Search button..."
        search_button_xpath = "//button[contains(@class, 'custom-search') and text()='Search']"
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, search_button_xpath)))
        driver.execute_script("arguments[0].click();", search_button)
        
        state['status'] = "⚡ Loading results (smart wait)..."
        
        # 🚀 SMART WAIT: Check for results faster with multiple indicators
        result_loaded = False
        max_smart_wait = 15  # Reduced from 60s
        start_smart_wait = time.time()
        
        while time.time() - start_smart_wait < max_smart_wait:
            try:
                # Check multiple indicators that data is loaded
                table_present = len(driver.find_elements(By.XPATH, "//div[contains(@class, 'ant-table-tbody')]")) > 0
                rows_present = len(driver.find_elements(By.XPATH, "//tr[@data-row-key]")) > 0
                data_visible = len(driver.find_elements(By.XPATH, "//td[contains(@class, 'ant-table-cell')]")) > 5
                
                # If ANY indicator shows data is ready, proceed immediately
                if table_present and (rows_present or data_visible):
                    print(f"✅ Results loaded in {time.time() - start_smart_wait:.1f}s")
                    result_loaded = True
                    break
                
                time.sleep(0.3)  # Check every 300ms
                
            except:
                time.sleep(0.3)
        
        if not result_loaded:
            print("⚠️ Smart wait timeout - proceeding anyway (data might still be loading)")
        
        # Small buffer to ensure rendering is complete
        time.sleep(1)
        
        state['progress'] = 75
        
        # Update company name from results
        if state['company_name'].startswith("Company_"):
            try:
                result_company = extract_company_name_from_page(driver)
                if result_company and not result_company.startswith("Company_"):
                    state['company_name'] = result_company
            except:
                pass
        
        # Zoom out for capture
        print("🔍 Zooming out to capture page...")
        state['status'] = "📸 Capturing page..."
        driver.execute_script("document.body.style.zoom='25%'")
        time.sleep(1)
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        # Capture
        full_page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Reset zoom
        reset_zoom(driver)
        
        print(f"✅ Captured {len(full_page_text):,} characters")
        state['progress'] = 80
        
        # Update company name from text
        if state['company_name'].startswith("Company_"):
            extracted_name = extract_company_name_from_text(full_page_text)
            if extracted_name:
                state['company_name'] = extracted_name
        
        # Verify data
        has_shipments = "Shipments" in full_page_text or "shipments" in full_page_text
        has_consignee = "Consignee" in full_page_text or "consignee" in full_page_text
        
        if has_shipments and has_consignee:
            state['status'] = "✅ High-quality data captured!"
        else:
            state['status'] = "⚠️ Limited data found"
        
        # Save raw data
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write("=== COMPLETE PAGE CONTENT ===\n")
            f.write(f"Company: {state['company_name']}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Captured at: {datetime.datetime.now()}\n")
            f.write("="*80 + "\n\n")
            f.write(full_page_text)
        
        state['progress'] = 85
        
        # AI Extraction - CHATGPT-STYLE ANALYSIS
        state['status'] = "🤖 Generating intelligent analysis..."
        extracted_data = extract_detailed_info_with_ai(full_page_text, state['company_name'], product_name)
        
        with open(EXTRACTED_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(extracted_data)
        
        state['extracted_data'] = extracted_data
        state['progress'] = 90
        
        # Save to history
        state['status'] = "💾 Saving to history..."
        save_company_analysis(state['company_name'], product_name, extracted_data)
        
        state['progress'] = 100
        state['status'] = f"✅ Analysis complete for {state['company_name']}!"
        
        state['analysis_complete'] = True
        state['product_name'] = product_name
        
        # Save browser session
        state['driver'] = driver
        state['wait'] = wait
        state['browser_logged_in'] = True
        
    except Exception as e:
        state['status'] = f"❌ Error: {str(e)}"
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        if driver:
            state['driver'] = driver
            state['wait'] = wait


def continue_volza_analysis(product_name):
    """Continue analysis using existing browser - NO new browser"""
    
    driver = state['driver']
    wait = state['wait']
    
    if driver is None:
        state['status'] = "❌ Browser session lost. Please restart."
        state['browser_logged_in'] = False
        return
    
    try:
        # Check browser
        try:
            _ = driver.current_url
        except:
            state['status'] = "❌ Browser was closed. Please restart."
            state['driver'] = None
            state['browser_logged_in'] = False
            return
        
        state['status'] = "🔧 Starting new search..."
        state['progress'] = 20
        
        safe_click(driver, By.XPATH, "//span[@class='ml10 main-header-text' and text()='New Search']", wait_time=30, description="New Search button")
        time.sleep(2)
        
        safe_click(driver, By.XPATH, "//span[text()='Select Country']", wait_time=30, description="Select Country dropdown")
        time.sleep(0.5)
        
        safe_click(driver, By.XPATH, "//span[@class='country-name' and text()='All Country (Global Search)']", wait_time=30, description="Global Search option")
        time.sleep(1)
        
        period_dropdown = driver.find_element(By.ID, "periodList")
        period_dropdown.send_keys("Custom")
        time.sleep(0.5)
        
        start_date_input = driver.find_element(By.ID, "globalDataFromDate")
        start_date_input.send_keys(Keys.CONTROL, 'a', Keys.BACK_SPACE)
        start_date_input.send_keys("01/01/2019")
        time.sleep(0.5)
        
        search_field_dropdown = driver.find_element(By.NAME, "field")
        Select(search_field_dropdown).select_by_value("GlobalCompany")
        time.sleep(1)
        
        state['status'] = "⏸️ PLEASE ENTER COMPANY NAME IN BROWSER"
        scream_message("PLEASE ENTER COMPANY NAME")
        state['progress'] = 40
        
        state['status'] = "⳿ Waiting for 'Apply' button..."
        
        max_wait_time = 300
        start_wait = time.time()
        
        while True:
            try:
                search_button = driver.find_element(By.XPATH, "//button[contains(@class, 'custom-search') and text()='Search']")
                if search_button.is_displayed() and search_button.is_enabled():
                    break
            except:
                pass
            
            if time.time() - start_wait > max_wait_time:
                state['status'] = "❌ Timeout"
                return
            time.sleep(1)
        
        state['status'] = "🔍 Extracting company name..."
        company_name = extract_company_name_from_page(driver)
        
        if not company_name:
            try:
                visible_text = driver.find_element(By.TAG_NAME, 'body').text[:3000]
                company_name = extract_company_name_from_text(visible_text)
            except:
                pass
        
        if company_name:
            state['company_name'] = company_name
        else:
            state['company_name'] = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        state['status'] = f"✅ Company: {state['company_name']}"
        state['progress'] = 50
        
        search_button_xpath = "//button[contains(@class, 'custom-search') and text()='Search']"
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, search_button_xpath)))
        driver.execute_script("arguments[0].click();", search_button)
        
        state['status'] = "⚡ Loading results (smart wait)..."
        
        # 🚀 SMART WAIT: Check for results faster
        result_loaded = False
        max_smart_wait = 15  # Reduced from 60s
        start_smart_wait = time.time()
        
        while time.time() - start_smart_wait < max_smart_wait:
            try:
                table_present = len(driver.find_elements(By.XPATH, "//div[contains(@class, 'ant-table-tbody')]")) > 0
                rows_present = len(driver.find_elements(By.XPATH, "//tr[@data-row-key]")) > 0
                data_visible = len(driver.find_elements(By.XPATH, "//td[contains(@class, 'ant-table-cell')]")) > 5
                
                if table_present and (rows_present or data_visible):
                    print(f"✅ Results loaded in {time.time() - start_smart_wait:.1f}s")
                    result_loaded = True
                    break
                
                time.sleep(0.3)
                
            except:
                time.sleep(0.3)
        
        if not result_loaded:
            print("⚠️ Smart wait timeout - proceeding anyway")
        
        time.sleep(1)  # Small buffer
        
        state['progress'] = 60
        
        # Zoom and capture
        driver.execute_script("document.body.style.zoom='25%'")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        full_page_text = driver.find_element(By.TAG_NAME, 'body').text
        reset_zoom(driver)
        
        state['progress'] = 70
        
        # Update company name
        if state['company_name'].startswith("Company_"):
            extracted_name = extract_company_name_from_text(full_page_text)
            if extracted_name:
                state['company_name'] = extracted_name
        
        # Save raw
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write("=== COMPLETE PAGE CONTENT ===\n")
            f.write(f"Company: {state['company_name']}\n")
            f.write(f"Product: {product_name}\n")
            f.write("="*80 + "\n\n")
            f.write(full_page_text)
        
        state['progress'] = 80
        
        # Extract - CHATGPT-STYLE ANALYSIS
        state['status'] = "🤖 Generating intelligent analysis..."
        extracted_data = extract_detailed_info_with_ai(full_page_text, state['company_name'], product_name)
        
        with open(EXTRACTED_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(extracted_data)
        
        state['extracted_data'] = extracted_data
        state['progress'] = 90
        
        save_company_analysis(state['company_name'], product_name, extracted_data)
        
        state['progress'] = 100
        state['status'] = f"✅ Complete: {state['company_name']}!"
        
        state['analysis_complete'] = True
        state['product_name'] = product_name
        
    except Exception as e:
        state['status'] = f"❌ Error: {str(e)}"
        import traceback
        traceback.print_exc()


# ==================== FLASK ROUTES ====================
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error loading template: {e}"

@app.route('/is_logged_in')
def is_logged_in():
    print("✅ /is_logged_in called")  # Debug log
    return jsonify({'logged_in': state['logged_in']})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('uid')
    pwd = data.get('pwd')
    if uid == VALID_USERNAME and pwd == VALID_PASSWORD:
        state['logged_in'] = True
        state['username'] = uid
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/logout', methods=['POST'])
def logout():
    global state
    
    if state['driver']:
        try:
            state['driver'].quit()
        except:
            pass
    
    state = {
        'logged_in': False,
        'username': "",
        'analysis_complete': False,
        'chat_history': [],
        'company_name': "",
        'product_name': "",
        'extracted_data': "",
        'driver': None,
        'browser_logged_in': False,
        'wait': None,
        'status': "",
        'progress': 0
    }
    return jsonify({'success': True})

@app.route('/start_analysis', methods=['POST'])
def start_analysis():
    data = request.json
    product_name = data.get('product_name')
    if not product_name:
        return jsonify({'success': False, 'message': 'Please enter product name'})
    state['product_name'] = product_name
    state['status'] = 'Starting...'
    state['progress'] = 0
    if state['browser_logged_in'] and state['driver']:
        thread = threading.Thread(target=continue_volza_analysis, args=(product_name,))
    else:
        thread = threading.Thread(target=run_volza_automation, args=(product_name,))
    thread.start()
    return jsonify({'success': True})

@app.route('/query', methods=['POST'])
def query():
    data = request.json
    question = data.get('question')
    if not state['analysis_complete']:
        return jsonify({'response': 'Analysis not complete'})
    response = query_company_data_direct(question, state['company_name'], state['extracted_data'])
    state['chat_history'].append({"role": "user", "content": question})
    state['chat_history'].append({"role": "bot", "content": response})
    return jsonify({'response': response})

@app.route('/get_chat_history')
def get_chat_history():
    return jsonify({'chat_history': state['chat_history']})

@app.route('/get_status')
def get_status():
    return jsonify({
        'status': state['status'],
        'progress': state['progress'],
        'analysis_complete': state['analysis_complete'],
        'company_name': state['company_name'],
        'product_name': state['product_name'],
        'extracted_data': state['extracted_data'],
        'browser_logged_in': state['browser_logged_in'],
        'username': state['username']
    })

@app.route('/get_history')
def get_history():
    history = load_history()
    recent = list(history.values())[-5:]
    return jsonify({'recent': recent})

@app.route('/new_analysis', methods=['POST'])
def new_analysis():
    state['analysis_complete'] = False
    state['chat_history'] = []
    state['company_name'] = ""
    state['product_name'] = ""
    state['extracted_data'] = ""
    state['status'] = ""
    state['progress'] = 0
    return jsonify({'success': True})

@app.route('/close_browser', methods=['POST'])
def close_browser():
    if state['driver']:
        try:
            state['driver'].quit()
        except:
            pass
    state['driver'] = None
    state['browser_logged_in'] = False
    return jsonify({'success': True})

if __name__ == "__main__":
    app.run(debug=True, threaded=True, use_reloader=False)