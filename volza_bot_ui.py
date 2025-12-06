"""
╔════════════════════════════════════════════════════════════════╗
║   GLOBALKEMYA INTELLIGENCE - VOLZA BOT UI                      ║
║   Expert Error Handling & Visible Browser                      ║
║   AUTO-UPDATING CHROMEDRIVER                                   ║
║   PERSISTENT BROWSER SESSION                                   ║
║   FIXED COMPANY NAME EXTRACTION                                ║
║   USER AUTHENTICATION                                          ║
╚════════════════════════════════════════════════════════════════╝
"""
import streamlit as st
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

# Suppress warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'


# ==================== CREDENTIALS ====================
VALID_USERNAME = "Globalkemya"
VALID_PASSWORD = "Global@123"


# ==================== AUTO-UPDATE CHROMEDRIVER FUNCTION ====================
def get_chrome_version():
    """Detect installed Chrome version on Windows"""
    try:
        # Windows registry check
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        winreg.CloseKey(key)
        return version.split('.')[0]  # Return major version (e.g., "142")
    except:
        pass
    
    try:
        # Alternative: Check Chrome executable
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
    Clears cache and retries if version mismatch occurs.
    """
    import undetected_chromedriver as uc
    
    chrome_version = get_chrome_version()
    print(f"🔍 Detected Chrome version: {chrome_version}")
    
    for attempt in range(max_retries):
        try:
            if chrome_version:
                # Use detected Chrome version
                driver = uc.Chrome(
                    options=chrome_options,
                    version_main=int(chrome_version)
                )
            else:
                # Let UC auto-detect
                driver = uc.Chrome(options=chrome_options)
            
            print(f"✅ ChromeDriver initialized successfully!")
            return driver
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if it's a version mismatch error
            if "version" in error_msg or "chromedriver" in error_msg or "session not created" in error_msg:
                print(f"⚠️ Attempt {attempt + 1}: ChromeDriver version mismatch detected")
                print(f"🔄 Clearing cache and retrying...")
                
                # Clear the UC cache
                clear_uc_cache()
                
                # Wait a moment before retry
                time.sleep(2)
                
                if attempt == max_retries - 1:
                    print(f"❌ Failed after {max_retries} attempts: {e}")
                    raise
            else:
                # Different error, raise immediately
                raise
    
    raise Exception("Failed to initialize ChromeDriver after all retries")


# ==================== REST OF YOUR IMPORTS ====================
# Load Environment Variables
load_dotenv()

# Configuration
LOGIN_EMAIL = "patel@globalkemya.com"
APP_PASSWORD = os.getenv("APP_PASSWORD")
EMAIL = os.getenv("EMAIL")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = os.getenv("IMAP_PORT", 993)
OTP_SENDER_EMAIL = "noreply@volza.com"
OTP_SUBJECT_KEYWORD = "Your OTP for Secure Login"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
MEMORY_FILE = "volza_ai_memory.json"
DATA_FILE = "data.txt"
EXTRACTED_DATA_FILE = "extracted_data.txt"

# RAG Configuration
VECTOR_DB_DIR = "./volza_knowledge_base"
COLLECTION_NAME = "volza_trade_intelligence"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
LLAMA4_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


# ==================== LAZY LOADING FUNCTIONS ====================
@st.cache_resource
def get_embeddings():
    """Lazy load embeddings only when needed"""
    from langchain_huggingface import HuggingFaceEmbeddings
    
    print("🔄 Loading embeddings model...")
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

@st.cache_resource
def get_llm():
    """Get Groq LLM"""
    from langchain_groq import ChatGroq
    
    return ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=LLAMA4_MODEL,
        temperature=0.3,
        max_tokens=2000
    )

@st.cache_resource
def get_text_splitter():
    """Get text splitter"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len
    )


# ==================== EXPERT ERROR HANDLING WRAPPERS ====================

def safe_click(driver, by, value, wait_time=30, description="element"):
    """
    Expert-level safe click with multiple retry strategies
    """
    wait = WebDriverWait(driver, wait_time)
    
    for attempt in range(3):
        try:
            print(f"Attempt {attempt + 1}: Finding {description}...")
            
            # Strategy 1: Wait for clickable
            element = wait.until(EC.element_to_be_clickable((by, value)))
            
            # Strategy 2: Scroll into view
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(0.5)
            
            # Strategy 3: Try normal click
            try:
                element.click()
                print(f"✅ Clicked {description} (normal click)")
                return element
            except:
                # Strategy 4: JavaScript click
                driver.execute_script("arguments[0].click();", element)
                print(f"✅ Clicked {description} (JS click)")
                return element
                
        except TimeoutException:
            if attempt < 2:
                print(f"⚠️ Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(2)
            else:
                print(f"❌ Failed to find {description} after 3 attempts")
                raise
        except StaleElementReferenceException:
            if attempt < 2:
                print(f"⚠️ Stale element on attempt {attempt + 1}, retrying...")
                time.sleep(1)
            else:
                raise
    
    raise Exception(f"Failed to click {description} after all retry attempts")


def safe_find_and_send(driver, by, value, text, wait_time=30, description="input field"):
    """
    Expert-level safe find and send keys
    """
    wait = WebDriverWait(driver, wait_time)
    
    for attempt in range(3):
        try:
            print(f"Attempt {attempt + 1}: Finding {description}...")
            
            element = wait.until(EC.presence_of_element_located((by, value)))
            
            # Clear and send
            element.clear()
            time.sleep(0.3)
            element.send_keys(text)
            
            print(f"✅ Sent text to {description}")
            return element
            
        except TimeoutException:
            if attempt < 2:
                print(f"⚠️ Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(2)
            else:
                print(f"❌ Failed to find {description} after 3 attempts")
                raise
        except StaleElementReferenceException:
            if attempt < 2:
                print(f"⚠️ Stale element on attempt {attempt + 1}, retrying...")
                time.sleep(1)
            else:
                raise
    
    raise Exception(f"Failed to interact with {description} after all retry attempts")


def wait_for_url_change(driver, old_url, timeout=60, description="URL change"):
    """
    Wait for URL to change with better error handling
    """
    print(f"Waiting for {description}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        current_url = driver.current_url
        if current_url != old_url:
            print(f"✅ {description} detected: {current_url}")
            return current_url
        time.sleep(0.5)
    
    raise TimeoutException(f"Timeout waiting for {description}")


# ==================== NEW: IMPROVED COMPANY NAME EXTRACTION ====================
def extract_company_name_from_page(driver):
    """
    Extract company name using multiple strategies
    Returns the company name or 'Unknown Company' if not found
    """
    company_name = None
    
    # Strategy 1: Try to get from the blue-link-color span (original method)
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
    
    # Strategy 2: Try to get from search criteria display
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
    
    # Strategy 3: Try to get from page title or header
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
    
    # Strategy 4: Try to find from the first consignee/shipper name in results
    try:
        # Look for company names in the table
        table_cells = driver.find_elements(By.XPATH, "//td[contains(@class, 'ant-table-cell')]//a")
        for cell in table_cells[:5]:  # Check first 5 links
            text = cell.text.strip()
            if text and len(text) > 3:
                company_name = text
                print(f"✅ Strategy 4: Found company name from table: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 4 failed: {e}")
    
    # Strategy 5: Extract from URL if possible
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
    
    # Strategy 6: Try to get from breadcrumb or navigation
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
    
    # Strategy 7: Look for any prominent text that could be a company name
    try:
        prominent_elements = driver.find_elements(By.XPATH, 
            "//*[contains(@class, 'company') or contains(@class, 'title') or contains(@class, 'name')]"
        )
        for elem in prominent_elements[:10]:
            text = elem.text.strip()
            if text and len(text) > 3 and len(text) < 100:
                company_name = text.split('\n')[0]  # Take first line
                print(f"✅ Strategy 7: Found company name from prominent element: {company_name}")
                return company_name
    except Exception as e:
        print(f"⚠️ Strategy 7 failed: {e}")
    
    print("❌ All strategies failed to extract company name")
    return None


def extract_company_name_from_text(page_text):
    """
    Extract company name from page text using regex and pattern matching
    """
    # Look for common patterns
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


# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="GlobalKemya Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 30px;
    }
    .chat-message {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .user-message {
        background-color: #E3F2FD;
        border-left: 5px solid #2196F3;
    }
    .bot-message {
        background-color: #F1F8E9;
        border-left: 5px solid #4CAF50;
    }
    .stButton>button {
        width: 100%;
        background-color: #1E88E5;
        color: white;
        font-size: 18px;
        padding: 15px;
        border-radius: 10px;
        border: none;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #1565C0;
    }
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 40px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }
    .login-header {
        text-align: center;
        color: #1E88E5;
        margin-bottom: 30px;
        font-size: 2rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# ==================== SESSION STATE INITIALIZATION ====================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'vectorstore' not in st.session_state:
    st.session_state.vectorstore = None
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'product_name' not in st.session_state:
    st.session_state.product_name = ""
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = ""

# ==================== PERSISTENT BROWSER SESSION ====================
if 'driver' not in st.session_state:
    st.session_state.driver = None
if 'browser_logged_in' not in st.session_state:
    st.session_state.browser_logged_in = False
if 'wait' not in st.session_state:
    st.session_state.wait = None


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


def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"companies_analyzed": []}


def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


def initialize_vector_db():
    """Initialize vector DB - only loads embeddings when called"""
    from langchain_chroma import Chroma
    
    embeddings = get_embeddings()
    
    if os.path.exists(VECTOR_DB_DIR):
        vectorstore = Chroma(
            persist_directory=VECTOR_DB_DIR,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
        return vectorstore
    else:
        vectorstore = Chroma(
            persist_directory=VECTOR_DB_DIR,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME
        )
        return vectorstore


def add_to_knowledge_base(company_name: str, product_name: str, data_text: str, vectorstore):
    from langchain_core.documents import Document
    
    text_splitter = get_text_splitter()
    
    document = Document(
        page_content=data_text,
        metadata={
            "company_name": company_name.lower().strip(),
            "product_searched": product_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "source": "volza_trade_data",
            "data_type": "import_export_intelligence"
        }
    )
    
    chunks = text_splitter.split_documents([document])
    vectorstore.add_documents(chunks)
    return chunks


def extract_detailed_info_with_ai(full_page_text: str, company_name: str, product_name: str) -> str:
    """
    Extract ALL visible data from page in structured format
    """
    extraction_prompt = f"""You are a data extraction specialist. Extract ALL information from the text below and format it in a structured way.

Company: {company_name}
Product: {product_name}

FULL PAGE TEXT:
{full_page_text[:20000]}

YOUR TASK:
Extract EVERYTHING you see in the text and organize it in this EXACT format:

=== COMPANY OVERVIEW ===
Company Name: {company_name}
Product Searched: {product_name}
Analysis Date: {datetime.datetime.now().strftime('%d %B %Y')}

=== SUMMARY STATISTICS ===
[Extract numbers for:]
- Total Shipments: [find the number]
- Total Consignees: [find the number]
- Total Shippers: [find the number]
- HS Codes: [find the number]
- Countries of Origin: [find the number]
- Countries of Destination: [find the number]
- Ports of Origin: [find the number]

=== ALL CONSIGNEE NAMES ===
[List EVERY consignee name you find, numbered:]
1. [Name] - [Country if visible]
2. [Name] - [Country if visible]
... continue for ALL consignees

=== ALL SHIPPER NAMES ===
[List EVERY shipper name you find, numbered:]
1. [Name] - [Country if visible]
2. [Name] - [Country if visible]
... continue for ALL shippers

=== HS CODES & PRODUCTS ===
[List all HS codes with descriptions:]
- HS Code [number]: [Product description]
... continue for all HS codes found

=== TRADE ROUTES & COUNTRIES ===
Origin Countries: [list all]
Destination Countries: [list all]
Ports of Origin: [list all]
Ports of Destination: [list all]

=== SHIPMENT DETAILS (SAMPLES) ===
[Extract 10-15 shipment examples with full details:]

Shipment 1:
- Date: [date]
- Consignee: [name]
- Shipper: [name]
- Product: [description]
- HS Code: [code]
- Quantity: [amount]
- Origin: [country/port]
- Destination: [country/port]

Shipment 2:
[continue same format]
...

=== ADDITIONAL DATA FOUND ===
[Any other relevant information from the page like:]
- Notify parties
- Container numbers
- Vessel names
- Shipment values
- Weights/volumes
- etc.

CRITICAL RULES:
1. DO NOT write "Not found in data" - extract what you actually see
2. If you see numbers, names, dates - INCLUDE THEM ALL
3. Be thorough - this is trade intelligence data
4. Maintain the exact structure above
5. If a section truly has no data, write "No data visible in text" (but check carefully first!)
"""

    try:
        print("🤖 Starting AI extraction (this may take 30-60 seconds)...")
        
        completion = client.chat.completions.create(
            model=LLAMA4_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert data extraction specialist. Extract ALL information you see and organize it clearly. Be thorough and detailed."
                },
                {
                    "role": "user",
                    "content": extraction_prompt
                }
            ],
            temperature=0.2,
            max_completion_tokens=4000,
            top_p=0.95,
            stream=False
        )
        
        extracted_data = completion.choices[0].message.content.strip()
        print("✅ AI extraction complete")
        return extracted_data
        
    except Exception as e:
        print(f"❌ Error during AI extraction: {e}")
        return f"Error extracting data: {e}\n\nRaw page text (first 5000 chars):\n{full_page_text[:5000]}"


def query_rag_system(vectorstore, query: str, company_name: str, product_name: str) -> str:
    """
    Query RAG system with COMPANY-SPECIFIC filtering
    """
    try:
        print(f"\n🔍 Querying RAG for company: '{company_name}'")
        
        # Normalize company name for matching
        normalized_company = company_name.lower().strip()
        
        # Get retriever with metadata filter for THIS COMPANY ONLY
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 10,
                "filter": {"company_name": normalized_company}
            }
        )
        
        docs = retriever.invoke(query)
        
        print(f"📊 Retrieved {len(docs)} documents for {company_name}")
        
        if not docs:
            # Fallback: Try without filter but still check company name in content
            print(f"⚠️ No docs found with filter, trying broader search...")
            retriever_fallback = vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 10}
            )
            all_docs = retriever_fallback.invoke(query)
            
            # Manually filter by company name in content
            docs = [doc for doc in all_docs if normalized_company in doc.page_content.lower()]
            print(f"📊 Fallback search found {len(docs)} documents")
        
        if not docs:
            return f"No information found for company '{company_name}'. The knowledge base may not contain data for this company yet."
        
        # Build context from retrieved documents
        context = "\n\n".join([
            f"Document {i+1}:\n{doc.page_content[:1000]}"
            for i, doc in enumerate(docs[:5])
        ])
        
        complete_prompt = f"""You are a Senior International Trade Intelligence Expert.

IMPORTANT: Answer ONLY about the company "{company_name}". Do NOT include information about other companies.

Company: {company_name}
Product: {product_name}

RETRIEVED CONTEXT (ONLY ABOUT {company_name.upper()}):
{context}

USER QUESTION: {query}

INSTRUCTIONS:
1. Analyze ONLY the provided context above
2. Answer ONLY about {company_name} - ignore any other company names
3. Provide specific insights with ACTUAL NAMES, numbers, dates from {company_name}'s data
4. Be specific and actionable
5. If the context doesn't contain information to answer the question, say "No information available for {company_name} about this topic."

ANSWER:"""
        
        completion = client.chat.completions.create(
            model=LLAMA4_MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": f"You are a Senior International Trade Intelligence Expert. You ONLY provide information about {company_name}. Never mention other companies."
                },
                {"role": "user", "content": complete_prompt}
            ],
            temperature=0.3,
            max_completion_tokens=1500,
            stream=False
        )
        
        return completion.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"❌ Error in RAG query: {e}")
        return f"❌ Error querying knowledge base: {e}"


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
# [Previous run_volza_automation and continue_volza_analysis functions remain exactly the same]
# I'll include them but they're unchanged from your working code

def run_volza_automation(product_name, status_placeholder, progress_bar):
    """Main automation with expert-level error handling - FIRST TIME WITH LOGIN"""
    
    driver = None
    wait = None
    
    try:
        # Initialize vectorstore
        status_placeholder.info("🧠 Initializing RAG system...")
        vectorstore = initialize_vector_db()
        st.session_state.vectorstore = vectorstore
        
        status_placeholder.info("🤖 Initializing Chrome browser (AUTO-UPDATE ENABLED)...")
        progress_bar.progress(10)
        
        # Import here to avoid issues
        import undetected_chromedriver as uc
        
        # Initialize Chrome with AUTO-UPDATE capability
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Use the auto-update function instead of direct uc.Chrome()
        driver = get_uc_driver_with_auto_update(chrome_options=options)
        
        driver.implicitly_wait(15)
        driver.maximize_window()
        wait = WebDriverWait(driver, 60)
        
        status_placeholder.info("🌐 Navigating to Volza...")
        progress_bar.progress(20)
        driver.get("https://app.volza.com/workspace/search/0")
        time.sleep(3)
        
        # Login with expert error handling
        status_placeholder.info("📧 Logging in...")
        progress_bar.progress(30)
        
        # Step 1: Enter email
        safe_find_and_send(
            driver, 
            By.NAME, 
            "emailAddress", 
            LOGIN_EMAIL, 
            wait_time=30,
            description="Email field"
        )
        time.sleep(1)
        
        # Step 2: Click Send OTP
        safe_click(
            driver,
            By.XPATH,
            "//div[@class='child-sign-up-button' and text()='Send OTP']",
            wait_time=30,
            description="Send OTP button"
        )
        time.sleep(2)
        
        # Step 3: Click OK on popup
        safe_click(
            driver,
            By.CLASS_NAME,
            "next-btn-swal",
            wait_time=30,
            description="OK button"
        )
        time.sleep(2)
        
        # Step 4: Close SVG popup (if exists)
        try:
            print("Checking for SVG popup...")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//svg[@stroke='currentColor' and @height='20' and @width='20']"))
            )
            popup = driver.find_element(By.XPATH, "//svg[@stroke='currentColor' and @height='20' and @width='20']")
            driver.execute_script("arguments[0].click();", popup)
            print("✅ Closed SVG popup")
        except TimeoutException:
            print("ℹ️ No SVG popup found (this is normal)")
        except Exception as e:
            print(f"ℹ️ SVG popup handling: {e} (continuing anyway)")
        
        time.sleep(1)
        
        # Step 5: Get OTP
        status_placeholder.info("🔐 Retrieving OTP...")
        otp_code = fetch_latest_otp(OTP_SENDER_EMAIL, OTP_SUBJECT_KEYWORD)
        
        if otp_code:
            safe_find_and_send(
                driver,
                By.NAME,
                "password",
                otp_code,
                wait_time=30,
                description="OTP field"
            )
            time.sleep(2)
        else:
            status_placeholder.warning("⚠️ Could not retrieve OTP. Please enter manually in browser.")
            time.sleep(15)
        
        # Step 6: Click Sign In
        login_page_url = driver.current_url
        safe_click(
            driver,
            By.XPATH,
            "//div[@class='child-sign-up-button' and text()='Sign In']",
            wait_time=30,
            description="Sign In button"
        )
        
        # Step 7: Wait for URL change
        wait_for_url_change(driver, login_page_url, timeout=60, description="Login redirect")
        time.sleep(2)
        
        # Step 8: Select company
        company_select_url = driver.current_url
        safe_click(
            driver,
            By.XPATH,
            "//button[contains(text(), 'Global Kemya India Llp')]",
            wait_time=30,
            description="Company selection"
        )
        
        wait_for_url_change(driver, company_select_url, timeout=60, description="Company selection redirect")
        
        status_placeholder.success("✅ Login successful!")
        progress_bar.progress(50)
        time.sleep(5)
        
        # Setup search
        status_placeholder.info("🔧 Setting up search...")
        
        # Click New Search
        safe_click(
            driver,
            By.XPATH,
            "//span[@class='ml10 main-header-text' and text()='New Search']",
            wait_time=30,
            description="New Search button"
        )
        time.sleep(3)
        
        # Select Country
        safe_click(
            driver,
            By.XPATH,
            "//span[text()='Select Country']",
            wait_time=30,
            description="Select Country dropdown"
        )
        time.sleep(1)
        
        safe_click(
            driver,
            By.XPATH,
            "//span[@class='country-name' and text()='All Country (Global Search)']",
            wait_time=30,
            description="Global Search option"
        )
        time.sleep(2)
        
        # Set date range
        period_dropdown = driver.find_element(By.ID, "periodList")
        period_dropdown.send_keys("Custom")
        time.sleep(1)
        
        start_date_input = driver.find_element(By.ID, "globalDataFromDate")
        start_date_input.send_keys(Keys.CONTROL, 'a', Keys.BACK_SPACE)
        start_date_input.send_keys("01/01/2019")
        time.sleep(1)
        
        # Set search field
        search_field_dropdown = driver.find_element(By.NAME, "field")
        Select(search_field_dropdown).select_by_value("GlobalCompany")
        time.sleep(2)
        
        # WAIT FOR USER TO ENTER COMPANY NAME
        status_placeholder.warning("⏸️ PLEASE ENTER COMPANY NAME IN BROWSER")
        scream_message("PLEASE ENTER COMPANY NAME")
        
        progress_bar.progress(60)
        
        # Wait for Apply button to be clicked
        status_placeholder.info("⏳ Waiting for you to click 'Apply' button...")
        
        # Monitor for Search button to appear (means Apply was clicked)
        max_wait_time = 300
        start_wait = time.time()
        
        while True:
            try:
                search_button = driver.find_element(
                    By.XPATH,
                    "//button[contains(@class, 'custom-search') and text()='Search']"
                )
                if search_button.is_displayed() and search_button.is_enabled():
                    print("✅ Apply button was clicked - Search button is now visible")
                    break
            except:
                pass
            
            if time.time() - start_wait > max_wait_time:
                status_placeholder.error("❌ Timeout waiting for Apply button click")
                return
            
            time.sleep(2)
        
        # ==================== IMPROVED COMPANY NAME EXTRACTION ====================
        status_placeholder.info("🔍 Extracting company name...")
        
        # Try multiple strategies to get company name
        company_name = extract_company_name_from_page(driver)
        
        if not company_name:
            # Fallback: Ask AI to extract from visible text
            try:
                visible_text = driver.find_element(By.TAG_NAME, 'body').text[:3000]
                company_name = extract_company_name_from_text(visible_text)
            except:
                pass
        
        if not company_name:
            # Last resort: Prompt user
            status_placeholder.warning("⚠️ Could not auto-detect company name. Please check the browser.")
            # Try one more time after user interaction
            time.sleep(3)
            company_name = extract_company_name_from_page(driver)
        
        if company_name:
            st.session_state.company_name = company_name
            print(f"✅ Final company name: {company_name}")
        else:
            # If still no company name, try to get from first result row
            try:
                first_result = driver.find_element(By.XPATH, "//table//tr[2]//td[1]")
                company_name = first_result.text.strip()
                if company_name:
                    st.session_state.company_name = company_name
                else:
                    st.session_state.company_name = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            except:
                st.session_state.company_name = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        status_placeholder.success(f"✅ Company detected: {st.session_state.company_name}")
        progress_bar.progress(70)
        
        # Click Search and wait for data
        status_placeholder.info("🔍 Clicking Search button...")
        print("\n🔍 Clicking Search button...")
        
        search_button_xpath = "//button[contains(@class, 'custom-search') and text()='Search']"
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, search_button_xpath)))
        driver.execute_script("arguments[0].click();", search_button)
        print("✅ Search button clicked")
        
        status_placeholder.info("⏳ Waiting for search results to load (30-60 seconds)...")
        print("\n⏳ WAITING FOR SEARCH RESULTS TO LOAD...")
        
        try:
            print("⏳ Waiting for data table to appear...")
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'ant-table-tbody')]"))
            )
            print("✅ Data table loaded successfully")
            time.sleep(5)
        except TimeoutException:
            print("⚠️ Timeout waiting for table, but continuing...")
        
        progress_bar.progress(75)
        
        # ==================== TRY TO GET COMPANY NAME FROM RESULTS ====================
        # After search results load, try again to get accurate company name
        if st.session_state.company_name.startswith("Company_") or st.session_state.company_name == "Unknown Company":
            try:
                # Look for company name in results
                result_company = extract_company_name_from_page(driver)
                if result_company and not result_company.startswith("Company_"):
                    st.session_state.company_name = result_company
                    print(f"✅ Updated company name from results: {result_company}")
            except:
                pass
        
        # Scroll to load all data
        print("\n📜 Scrolling page to load ALL consignee names...")
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5
        
        while scroll_attempts < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"📜 Scroll {scroll_attempts + 1}/{max_scrolls}...")
            time.sleep(3)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                print("✅ Reached end of page - all content loaded")
                break
            
            last_height = new_height
            scroll_attempts += 1
        
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        print("⏳ Final wait for all data to fully render...")
        time.sleep(5)
        
        print("\n✅ SEARCH RESULTS FULLY LOADED - Ready to collect data")
        
        progress_bar.progress(80)  #this is last line 
        # Capture page
        status_placeholder.info("📄 Capturing complete page data...")
        print("\n📄 COPYING ENTIRE PAGE CONTENT...")
        
        full_page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        print(f"📊 Captured {len(full_page_text):,} characters from page")
        print(f"📊 First 800 chars preview:\n{'-'*80}\n{full_page_text[:800]}\n{'-'*80}")
        
        # ==================== FINAL ATTEMPT TO EXTRACT COMPANY NAME FROM PAGE TEXT ====================
        if st.session_state.company_name.startswith("Company_") or st.session_state.company_name == "Unknown Company":
            extracted_name = extract_company_name_from_text(full_page_text)
            if extracted_name:
                st.session_state.company_name = extracted_name
                print(f"✅ Final company name from page text: {extracted_name}")
        
        # Verify data quality
        has_shipments = "Shipments" in full_page_text or "shipments" in full_page_text
        has_consignee = "Consignee" in full_page_text or "consignee" in full_page_text
        
        if has_shipments and has_consignee:
            print("✅ DATA VERIFIED: Page contains shipment/consignee information")
            status_placeholder.success("✅ High-quality data captured!")
        else:
            print("⚠️ WARNING: Page text might not contain expected data")
            status_placeholder.warning("⚠️ Limited data found")
        
        # Save raw data
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write("=== COMPLETE PAGE CONTENT ===\n")
            f.write(f"Company: {st.session_state.company_name}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Captured at: {datetime.datetime.now()}\n")
            f.write(f"Total characters: {len(full_page_text):,}\n")
            f.write("="*80 + "\n\n")
            f.write(full_page_text)
        
        print(f"✅ Saved {len(full_page_text):,} characters to {DATA_FILE}")
        
        progress_bar.progress(85)
        
        # AI Extraction
        status_placeholder.info("🤖 Extracting data with AI (30-60 seconds)...")
        extracted_data = extract_detailed_info_with_ai(
            full_page_text,
            st.session_state.company_name,
            product_name
        )
        
        with open(EXTRACTED_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== EXTRACTED TRADE INTELLIGENCE ===\n")
            f.write(f"Company: {st.session_state.company_name}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Extracted at: {datetime.datetime.now()}\n")
            f.write("="*80 + "\n\n")
            f.write(extracted_data)
        
        st.session_state.extracted_data = extracted_data
        progress_bar.progress(90)
        
        # Add to RAG
        status_placeholder.info("🧠 Adding to knowledge base...")
        chunks = add_to_knowledge_base(
            st.session_state.company_name,
            product_name,
            extracted_data,
            vectorstore
        )
        
        progress_bar.progress(100)
        status_placeholder.success(f"✅ Analysis complete for {st.session_state.company_name}! {len(chunks)} chunks added.")
        
        st.session_state.analysis_complete = True
        st.session_state.product_name = product_name
        
        # Save to memory
        memory = load_memory()
        memory["companies_analyzed"].append({
            "name": st.session_state.company_name,
            "product": product_name,
            "date": datetime.datetime.now().isoformat(),
            "chunks_created": len(chunks),
            "rag_enabled": True,
            "model": LLAMA4_MODEL
        })
        save_memory(memory)
        
        # SAVE BROWSER TO SESSION STATE - DON'T CLOSE
        st.session_state.driver = driver
        st.session_state.wait = wait
        st.session_state.browser_logged_in = True
        
    except Exception as e:
        status_placeholder.error(f"❌ Error: {str(e)}")
        print(f"Error Details: {e}")
        import traceback
        traceback.print_exc()
        # Save driver even on error if it exists
        if driver:
            st.session_state.driver = driver
            st.session_state.wait = wait


def continue_volza_analysis(product_name, status_placeholder, progress_bar):
    """Continue analysis using existing browser session - NO new browser opened"""
    
    driver = st.session_state.driver
    wait = st.session_state.wait
    
    if driver is None:
        status_placeholder.error("❌ Browser session lost. Please restart.")
        st.session_state.browser_logged_in = False
        return
    
    try:
        # Check if browser is still alive
        try:
            _ = driver.current_url
        except:
            status_placeholder.error("❌ Browser was closed. Please restart.")
            st.session_state.driver = None
            st.session_state.browser_logged_in = False
            return
        
        status_placeholder.info("🧠 Initializing RAG system...")
        progress_bar.progress(10)
        
        vectorstore = initialize_vector_db()
        st.session_state.vectorstore = vectorstore
        
        # Click New Search button
        status_placeholder.info("🔧 Starting new search...")
        progress_bar.progress(20)
        
        safe_click(
            driver,
            By.XPATH,
            "//span[@class='ml10 main-header-text' and text()='New Search']",
            wait_time=30,
            description="New Search button"
        )
        time.sleep(3)
        
        # Select Country
        safe_click(
            driver,
            By.XPATH,
            "//span[text()='Select Country']",
            wait_time=30,
            description="Select Country dropdown"
        )
        time.sleep(1)
        
        safe_click(
            driver,
            By.XPATH,
            "//span[@class='country-name' and text()='All Country (Global Search)']",
            wait_time=30,
            description="Global Search option"
        )
        time.sleep(2)
        
        # Set date range
        period_dropdown = driver.find_element(By.ID, "periodList")
        period_dropdown.send_keys("Custom")
        time.sleep(1)
        
        start_date_input = driver.find_element(By.ID, "globalDataFromDate")
        start_date_input.send_keys(Keys.CONTROL, 'a', Keys.BACK_SPACE)
        start_date_input.send_keys("01/01/2019")
        time.sleep(1)
        
        # Set search field
        search_field_dropdown = driver.find_element(By.NAME, "field")
        Select(search_field_dropdown).select_by_value("GlobalCompany")
        time.sleep(2)
        
        # WAIT FOR USER TO ENTER COMPANY NAME
        status_placeholder.warning("⏸️ PLEASE ENTER COMPANY NAME IN BROWSER")
        scream_message("PLEASE ENTER COMPANY NAME")
        
        progress_bar.progress(40)
        
        # Wait for Apply button to be clicked
        status_placeholder.info("⏳ Waiting for you to click 'Apply' button...")
        
        max_wait_time = 300
        start_wait = time.time()
        
        while True:
            try:
                search_button = driver.find_element(
                    By.XPATH,
                    "//button[contains(@class, 'custom-search') and text()='Search']"
                )
                if search_button.is_displayed() and search_button.is_enabled():
                    print("✅ Apply button was clicked - Search button is now visible")
                    break
            except:
                pass
            
            if time.time() - start_wait > max_wait_time:
                status_placeholder.error("❌ Timeout waiting for Apply button click")
                return
            
            time.sleep(2)
        
        # ==================== IMPROVED COMPANY NAME EXTRACTION ====================
        status_placeholder.info("🔍 Extracting company name...")
        
        # Try multiple strategies to get company name
        company_name = extract_company_name_from_page(driver)
        
        if not company_name:
            # Fallback: Ask AI to extract from visible text
            try:
                visible_text = driver.find_element(By.TAG_NAME, 'body').text[:3000]
                company_name = extract_company_name_from_text(visible_text)
            except:
                pass
        
        if not company_name:
            # Last resort: Prompt user
            status_placeholder.warning("⚠️ Could not auto-detect company name. Please check the browser.")
            # Try one more time after user interaction
            time.sleep(3)
            company_name = extract_company_name_from_page(driver)
        
        if company_name:
            st.session_state.company_name = company_name
            print(f"✅ Final company name: {company_name}")
        else:
            # If still no company name, try to get from first result row
            try:
                first_result = driver.find_element(By.XPATH, "//table//tr[2]//td[1]")
                company_name = first_result.text.strip()
                if company_name:
                    st.session_state.company_name = company_name
                else:
                    st.session_state.company_name = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            except:
                st.session_state.company_name = "Company_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        status_placeholder.success(f"✅ Company detected: {st.session_state.company_name}")
        progress_bar.progress(50)
        
        # Click Search and wait for data
        status_placeholder.info("🔍 Clicking Search button...")
        print("\n🔍 Clicking Search button...")
        
        search_button_xpath = "//button[contains(@class, 'custom-search') and text()='Search']"
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, search_button_xpath)))
        driver.execute_script("arguments[0].click();", search_button)
        print("✅ Search button clicked")
        
        status_placeholder.info("⏳ Waiting for search results to load (30-60 seconds)...")
        print("\n⏳ WAITING FOR SEARCH RESULTS TO LOAD...")
        
        try:
            print("⏳ Waiting for data table to appear...")
            wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'ant-table-tbody')]"))
            )
            print("✅ Data table loaded successfully")
            time.sleep(5)
        except TimeoutException:
            print("⚠️ Timeout waiting for table, but continuing...")
        
        progress_bar.progress(60)
        
        # ==================== TRY TO GET COMPANY NAME FROM RESULTS ====================
        # After search results load, try again to get accurate company name
        if st.session_state.company_name.startswith("Company_") or st.session_state.company_name == "Unknown Company":
            try:
                # Look for company name in results
                result_company = extract_company_name_from_page(driver)
                if result_company and not result_company.startswith("Company_"):
                    st.session_state.company_name = result_company
                    print(f"✅ Updated company name from results: {result_company}")
            except:
                pass
        
        # Scroll to load all data
        print("\n📜 Scrolling page to load ALL consignee names...")
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5
        
        while scroll_attempts < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print(f"📜 Scroll {scroll_attempts + 1}/{max_scrolls}...")
            time.sleep(3)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                print("✅ Reached end of page - all content loaded")
                break
            
            last_height = new_height
            scroll_attempts += 1
        
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        print("⏳ Final wait for all data to fully render...")
        time.sleep(5)
        
        print("\n✅ SEARCH RESULTS FULLY LOADED - Ready to collect data")
        
        progress_bar.progress(70)
        
        # Capture page
        status_placeholder.info("📄 Capturing complete page data...")
        print("\n📄 COPYING ENTIRE PAGE CONTENT...")
        
        full_page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        print(f"📊 Captured {len(full_page_text):,} characters from page")
        print(f"📊 First 800 chars preview:\n{'-'*80}\n{full_page_text[:800]}\n{'-'*80}")
        
        # ==================== FINAL ATTEMPT TO EXTRACT COMPANY NAME FROM PAGE TEXT ====================
        if st.session_state.company_name.startswith("Company_") or st.session_state.company_name == "Unknown Company":
            extracted_name = extract_company_name_from_text(full_page_text)
            if extracted_name:
                st.session_state.company_name = extracted_name
                print(f"✅ Final company name from page text: {extracted_name}")
        
        # Verify data quality
        has_shipments = "Shipments" in full_page_text or "shipments" in full_page_text
        has_consignee = "Consignee" in full_page_text or "consignee" in full_page_text
        
        if has_shipments and has_consignee:
            print("✅ DATA VERIFIED: Page contains shipment/consignee information")
            status_placeholder.success("✅ High-quality data captured!")
        else:
            print("⚠️ WARNING: Page text might not contain expected data")
            status_placeholder.warning("⚠️ Limited data found")
        
        # Save raw data
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write("=== COMPLETE PAGE CONTENT ===\n")
            f.write(f"Company: {st.session_state.company_name}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Captured at: {datetime.datetime.now()}\n")
            f.write(f"Total characters: {len(full_page_text):,}\n")
            f.write("="*80 + "\n\n")
            f.write(full_page_text)
        
        print(f"✅ Saved {len(full_page_text):,} characters to {DATA_FILE}")
        
        progress_bar.progress(80)
        
        # AI Extraction
        status_placeholder.info("🤖 Extracting data with AI (30-60 seconds)...")
        extracted_data = extract_detailed_info_with_ai(
            full_page_text,
            st.session_state.company_name,
            product_name
        )
        
        with open(EXTRACTED_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== EXTRACTED TRADE INTELLIGENCE ===\n")
            f.write(f"Company: {st.session_state.company_name}\n")
            f.write(f"Product: {product_name}\n")
            f.write(f"Extracted at: {datetime.datetime.now()}\n")
            f.write("="*80 + "\n\n")
            f.write(extracted_data)
        
        st.session_state.extracted_data = extracted_data
        progress_bar.progress(90)
        
        # Add to RAG
        status_placeholder.info("🧠 Adding to knowledge base...")
        chunks = add_to_knowledge_base(
            st.session_state.company_name,
            product_name,
            extracted_data,
            vectorstore
        )
        
        progress_bar.progress(100)
        status_placeholder.success(f"✅ Analysis complete for {st.session_state.company_name}! {len(chunks)} chunks added.")
        
        st.session_state.analysis_complete = True
        st.session_state.product_name = product_name
        
        # Save to memory
        memory = load_memory()
        memory["companies_analyzed"].append({
            "name": st.session_state.company_name,
            "product": product_name,
            "date": datetime.datetime.now().isoformat(),
            "chunks_created": len(chunks),
            "rag_enabled": True,
            "model": LLAMA4_MODEL
        })
        save_memory(memory)
        
        # DON'T CLOSE BROWSER - Keep it open for next analysis
        
    except Exception as e:
        status_placeholder.error(f"❌ Error: {str(e)}")
        print(f"Error Details: {e}")
        import traceback
        traceback.print_exc()
        # DON'T CLOSE BROWSER on error either


# ==================== UPDATED LOGIN PAGE (EXACTLY LIKE YOUR IMAGE) ====================
def show_login_page():
    """Display beautiful blue-themed login page exactly like the screenshot"""
    
    # Full blue background
    st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%);
        }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div class="login-box">
            <div class="lock-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
            </div>
            <h2 class="login-title" style="color: white;">Welcome Back</h2>
            <p class="login-subtitle" style="color: white;">Please login to access GlobalKemya Intelligence</p>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            st.text_input("User ID", placeholder="Enter your user ID", key="uid")
            st.text_input("Password", type="password", placeholder="Enter your password", key="pwd")
            
            login_btn = st.form_submit_button("Login", use_container_width=True)
            
            if login_btn:
                if st.session_state.uid == VALID_USERNAME and st.session_state.pwd == VALID_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.username = VALID_USERNAME
                    st.success("Login successful! Redirecting...")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("Invalid User ID or Password")

        st.markdown("</div>", unsafe_allow_html=True)
        
        # Footer
        st.markdown("""
        <div style="text-align: center; margin-top: 50px; color: rgba(255,255,255,0.8); font-size: 14px;">
            © 2025 GlobalKemya Intelligence • Secure Access
        </div>
        """, unsafe_allow_html=True)


# ==================== MAIN APP UI ====================
def show_main_app():
    """Display main application after login"""
    
    # Header
    st.markdown('<h1 class="main-header">🔍 GLOBALKEMYA INTELLIGENCE</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">AI-Powered Supplier Intelligence System</p>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("👤 User Info")
        st.info(f"**Logged in as:** {st.session_state.username}")
        
        if st.button("🚪 Logout"):
            # Close browser if open
            if st.session_state.driver:
                try:
                    st.session_state.driver.quit()
                except:
                    pass
            
            # Reset all session state
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.driver = None
            st.session_state.browser_logged_in = False
            st.session_state.wait = None
            st.session_state.analysis_complete = False
            st.session_state.chat_history = []
            st.session_state.company_name = ""
            st.session_state.product_name = ""
            st.session_state.extracted_data = ""
            
            st.success("Logged out successfully!")
            time.sleep(1)
            st.rerun()
        
        st.markdown("---")
        st.header("📊 System Status")
        
        if st.session_state.analysis_complete:
            st.success("✅ Analysis Complete")
            st.info(f"**Company:** {st.session_state.company_name}")
            st.info(f"**Product:** {st.session_state.product_name}")
        else:
            st.warning("⏳ Waiting for analysis...")
        
        # Show browser status
        st.markdown("---")
        st.header("🌐 Browser Status")
        if st.session_state.browser_logged_in:
            st.success("✅ Browser Active & Logged In")
            if st.button("❌ Close Browser"):
                if st.session_state.driver:
                    try:
                        st.session_state.driver.quit()
                    except:
                        pass
                st.session_state.driver = None
                st.session_state.browser_logged_in = False
                st.session_state.wait = None
                st.success("Browser closed!")
                st.rerun()
        else:
            st.warning("⏳ Browser not started")
        
        st.markdown("---")
        st.header("📁 Recent Analyses")
        
        memory = load_memory()
        recent = memory.get("companies_analyzed", [])[-5:]
        
        for item in reversed(recent):
            with st.expander(f"{item.get('name', 'Unknown')}"):
                st.write(f"**Product:** {item.get('product', 'N/A')}")
                st.write(f"**Date:** {item.get('date', 'N/A')[:10]}")
        
        if st.button("🗑️ Clear History"):
            st.session_state.analysis_complete = False
            st.session_state.chat_history = []
            st.success("History cleared!")
            st.rerun()
    
    # Main content
    if not st.session_state.analysis_complete:
        st.markdown("### 📦 Enter Product Information")
        
        # Show browser status
        if st.session_state.browser_logged_in:
            st.success("🌐 Browser is ready - Enter company name in browser when prompted")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            product_input = st.text_input(
                "Enter Product Name or HS Code:",
                placeholder="e.g., spare parts, chemicals, HS Code 8413",
                help="What product are you searching for?"
            )
        
        with col2:
            st.write("")
            st.write("")
            start_button = st.button("🚀 Start Analysis", type="primary")
        
        if start_button and product_input:
            st.session_state.product_name = product_input
            
            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            
            # CHECK IF BROWSER ALREADY LOGGED IN
            if st.session_state.browser_logged_in and st.session_state.driver is not None:
                # Use existing browser - don't open new one
                status_placeholder.info("🔄 Using existing browser session...")
                continue_volza_analysis(product_input, status_placeholder, progress_bar)
            else:
                # First time - open new browser and login
                run_volza_automation(product_input, status_placeholder, progress_bar)
            
            st.rerun()
        
        elif start_button:
            st.error("⚠️ Please enter a product name!")
    
    else:
        st.markdown("### 💬 Intelligence Chat")
        
        # Show current company being analyzed
        st.info(f"📊 Currently analyzing: **{st.session_state.company_name}**")
        
        with st.expander("📊 View Extracted Data Summary", expanded=False):
            st.text_area("Extracted Intelligence", st.session_state.extracted_data, height=300)
        
        chat_container = st.container()
        
        with chat_container:
            for chat in st.session_state.chat_history:
                if chat['role'] == 'user':
                    st.markdown(f'<div class="chat-message user-message"><strong>You:</strong> {chat["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="chat-message bot-message"><strong>🤖 AI:</strong> {chat["content"]}</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([5, 1])
        
        with col1:
            user_question = st.text_input(
                "Ask a question about the company:",
                placeholder="e.g., Who are the top consignees?",
                key="user_input"
            )
        
        with col2:
            st.write("")
            st.write("")
            send_button = st.button("Send", type="primary")
        
        if send_button and user_question:
            st.session_state.chat_history.append({"role": "user", "content": user_question})
            
            with st.spinner("🤖 Thinking..."):
                response = query_rag_system(
                    st.session_state.vectorstore,
                    user_question,
                    st.session_state.company_name,
                    st.session_state.product_name
                )
            
            st.session_state.chat_history.append({"role": "bot", "content": response})
            st.rerun()
        
        st.markdown("### 💡 Quick Questions")
        quick_questions = [
            "Who are the top consignees?",
            "What are the main trade routes?",
            "What are the risks?",
            "Product match score?",
            "Partnership recommendation?"
        ]
        
        cols = st.columns(len(quick_questions))
        for i, q in enumerate(quick_questions):
            with cols[i]:
                if st.button(q, key=f"quick_{i}"):
                    st.session_state.chat_history.append({"role": "user", "content": q})
                    response = query_rag_system(
                        st.session_state.vectorstore,
                        q,
                        st.session_state.company_name,
                        st.session_state.product_name
                    )
                    st.session_state.chat_history.append({"role": "bot", "content": response})
                    st.rerun()
        
        # Start New Analysis button
        st.markdown("---")
        if st.button("🔄 Start New Analysis"):
            st.session_state.analysis_complete = False
            st.session_state.chat_history = []
            st.session_state.company_name = ""
            st.session_state.product_name = ""
            st.session_state.extracted_data = ""
            # DON'T reset browser_logged_in - keep browser session
            st.rerun()


# ==================== MAIN ENTRY POINT ====================
if __name__ == "__main__":
    if not st.session_state.logged_in:
        show_login_page()
    else:
        show_main_app()

