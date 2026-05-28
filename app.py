import streamlit as st
import time
import threading
import hashlib
import os
import json
import random
import sqlite3
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import requests

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

# Facebook Chat API imports
try:
    from facebook_chat_api import FacebookChatAPI
    from ws3_fca import ws3_fca
    FCA_AVAILABLE = True
except ImportError:
    FCA_AVAILABLE = False

# ==================== DATABASE SETUP ====================
DB_PATH = "automation.db"

def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  is_admin BOOLEAN DEFAULT 0,
                  appstate TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # User configs table
    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (user_id INTEGER PRIMARY KEY,
                  chat_id TEXT,
                  name_prefix TEXT,
                  delay INTEGER DEFAULT 10,
                  cookies TEXT,
                  messages TEXT,
                  automation_running BOOLEAN DEFAULT 0,
                  last_run TIMESTAMP,
                  total_messages_sent INTEGER DEFAULT 0,
                  use_fca BOOLEAN DEFAULT 1,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Automation sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS automation_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  start_time TIMESTAMP,
                  end_time TIMESTAMP,
                  messages_sent INTEGER,
                  status TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Create default admin
    c.execute("SELECT id FROM users WHERE username = ?", ("Ashiq Raj",))
    if not c.fetchone():
        hashed_admin = hashlib.sha256("Ashiq Raj".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, is_admin, appstate) VALUES (?, ?, ?, ?)",
                  ("Ashiq Raj", hashed_admin, 1, ""))
        admin_id = c.lastrowid
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages, use_fca) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (admin_id, "", "Ashiq Raj", 10, "", "Hello!\nHow are you?\nNice to meet you!\nHave a great day!", 1))
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username: str, password: str) -> Tuple[bool, str]:
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    try:
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters"
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters"
        
        hashed = hash_password(password)
        c.execute("INSERT INTO users (username, password, is_admin, appstate) VALUES (?, ?, ?, ?)", 
                  (username, hashed, 0, ""))
        user_id = c.lastrowid
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages, use_fca) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, "", "", 10, "", "Hello!\nHow are you?\nNice to meet you!", 1))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def verify_user(username: str, password: str) -> Optional[int]:
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    hashed = hash_password(password)
    c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, hashed))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_config(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages, total_messages_sent, use_fca FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 10,
            'cookies': row[3] or '',
            'messages': row[4] or '',
            'total_sent': row[5] or 0,
            'use_fca': row[6] if row[6] is not None else 1
        }
    return None

def update_user_config(user_id: int, chat_id: str, name_prefix: str, delay: int, cookies: str, messages: str, use_fca: bool = True):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?, use_fca = ? WHERE user_id = ?",
              (chat_id, name_prefix, delay, cookies, messages, 1 if use_fca else 0, user_id))
    conn.commit()
    conn.close()

def update_total_messages(user_id: int, additional: int):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET total_messages_sent = total_messages_sent + ? WHERE user_id = ?", (additional, user_id))
    conn.commit()
    conn.close()

def set_automation_running(user_id: int, is_running: bool):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET automation_running = ?, last_run = CURRENT_TIMESTAMP WHERE user_id = ?", 
              (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT automation_running FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def get_username(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Unknown"

def update_appstate(user_id: int, appstate: str):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET appstate = ? WHERE id = ?", (appstate, user_id))
    conn.commit()
    conn.close()

def get_appstate(user_id: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT appstate FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def log_automation_session(user_id: int, messages_sent: int, status: str):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("INSERT INTO automation_sessions (user_id, start_time, end_time, messages_sent, status) VALUES (?, datetime('now'), datetime('now'), ?, ?)",
              (user_id, messages_sent, status))
    conn.commit()
    conn.close()

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Ashiq Raj - Advanced Facebook Automation",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS ====================
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Poppins', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}

.main .block-container {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 30px;
    padding: 35px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    margin: 20px auto;
}

.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 3rem;
    border-radius: 30px;
    text-align: center;
    margin-bottom: 2rem;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.main-header h1 {
    color: white;
    font-size: 3.5rem;
    font-weight: 800;
    margin: 0;
}

.main-header p {
    color: rgba(255, 255, 255, 0.9);
    font-size: 1.3rem;
    margin-top: 1rem;
}

.stButton > button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 15px;
    padding: 0.8rem 2rem;
    font-weight: 600;
    transition: all 0.3s ease;
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: rgba(255, 255, 255, 0.9);
    border: 2px solid #667eea;
    border-radius: 12px;
    padding: 0.8rem;
}

label {
    color: #667eea !important;
    font-weight: 600 !important;
}

/* Console Output */
.console-output {
    background: #1a1a2e;
    border-radius: 15px;
    padding: 20px;
    font-family: 'Courier New', monospace;
    max-height: 500px;
    overflow-y: auto;
    border: 2px solid #667eea;
}

.console-line {
    color: #00ff88;
    margin-bottom: 8px;
    padding: 5px 10px;
    border-left: 3px solid #00ff88;
    background: rgba(0, 255, 136, 0.1);
    font-size: 12px;
}

.footer {
    text-align: center;
    padding: 2rem;
    color: #667eea;
    font-weight: 600;
    margin-top: 2rem;
}

.sidebar-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 20px;
    text-align: center;
    color: white;
    font-weight: 800;
    margin-bottom: 1.5rem;
}

.metric-container {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    padding: 1rem;
    border-radius: 15px;
    text-align: center;
}

[data-testid="stMetricValue"] {
    color: white !important;
}
"""

st.markdown(custom_css, unsafe_allow_html=True)

# ==================== FACEBOOK CHAT API WRAPPER ====================
class FacebookAutomation:
    def __init__(self, user_id: int, automation_state):
        self.user_id = user_id
        self.automation_state = automation_state
        self.api = None
        self.running = False
        
    def log(self, msg: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {msg}"
        self.automation_state.logs.append((formatted_msg, level))
        
    def setup_fca(self, appstate: str):
        """Setup Facebook Chat API with appstate"""
        try:
            import json
            import facebook_chat_api
            
            # Save appstate to file
            appstate_path = f"/tmp/appstate_{self.user_id}.json"
            with open(appstate_path, 'w') as f:
                json.dump(json.loads(appstate), f)
            
            # Initialize API
            self.api = facebook_chat_api.FacebookChatAPI(appstate_path)
            self.log("✅ FCA API initialized successfully", "success")
            return True
        except Exception as e:
            self.log(f"❌ FCA setup failed: {str(e)}", "error")
            return False
    
    def send_message_selenium(self, chat_id: str, message: str, cookies: str = None):
        """Send message using Selenium (works for E2EE)"""
        driver = None
        try:
            self.log("Setting up browser...", "info")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Try to find Chrome binary
            possible_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser"
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    chrome_options.binary_location = path
                    break
            
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager(path="/tmp/chromedriver").install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Navigate to Facebook
            driver.get('https://www.facebook.com/')
            time.sleep(5)
            
            # Add cookies if provided
            if cookies:
                cookie_pairs = cookies.split(';')
                for pair in cookie_pairs:
                    if '=' in pair:
                        name, value = pair.split('=', 1)
                        try:
                            driver.add_cookie({'name': name.strip(), 'value': value.strip(), 'domain': '.facebook.com'})
                        except:
                            pass
            
            # Navigate to chat
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
            time.sleep(8)
            
            # Find message input
            wait = WebDriverWait(driver, 30)
            message_input = None
            
            selectors = [
                'div[contenteditable="true"][role="textbox"]',
                'div[contenteditable="true"][data-lexical-editor="true"]',
                'div[aria-label*="message" i][contenteditable="true"]'
            ]
            
            for selector in selectors:
                try:
                    message_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                    if message_input:
                        break
                except:
                    continue
            
            if not message_input:
                self.log("❌ Could not find message input", "error")
                return False
            
            # Send message
            driver.execute_script("""
                arguments[0].scrollIntoView({block: 'center'});
                arguments[0].focus();
                arguments[0].click();
                arguments[0].textContent = arguments[1];
                arguments[0].innerHTML = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """, message_input, message)
            
            time.sleep(1)
            message_input.send_keys(Keys.RETURN)
            
            self.log(f"✅ Message sent via Selenium: {message[:50]}...", "success")
            return True
            
        except Exception as e:
            self.log(f"❌ Selenium error: {str(e)}", "error")
            return False
        finally:
            if driver:
                driver.quit()
    
    def send_message_fca(self, chat_id: str, message: str):
        """Send message using FCA (Facebook Chat API)"""
        try:
            if not self.api:
                self.log("❌ FCA not initialized", "error")
                return False
            
            # Send message using FCA
            result = self.api.sendMessage(message, chat_id)
            self.log(f"✅ Message sent via FCA: {message[:50]}...", "success")
            return True
        except Exception as e:
            self.log(f"❌ FCA error: {str(e)}", "error")
            return False
    
    def run_automation(self, config: Dict):
        """Main automation loop"""
        self.running = True
        total_sent = 0
        
        # Prepare messages
        messages_list = [m.strip() for m in config['messages'].split('\n') if m.strip()]
        if not messages_list:
            messages_list = ['Hello!']
        
        chat_id = config['chat_id']
        use_fca = config.get('use_fca', True)
        name_prefix = config.get('name_prefix', '')
        
        self.log(f"🚀 Starting automation to {chat_id}", "success")
        self.log(f"📝 Using {'FCA API' if use_fca else 'Selenium'} method", "info")
        self.log(f"💬 Loaded {len(messages_list)} messages", "info")
        
        message_index = 0
        
        while self.running and self.automation_state.running:
            try:
                # Get message
                base_msg = messages_list[message_index % len(messages_list)]
                full_msg = f"{name_prefix} {base_msg}".strip() if name_prefix else base_msg
                
                # Send message
                if use_fca and self.api:
                    success = self.send_message_fca(chat_id, full_msg)
                else:
                    success = self.send_message_selenium(chat_id, full_msg, config.get('cookies'))
                
                if success:
                    total_sent += 1
                    self.automation_state.message_count = total_sent
                    message_index += 1
                    
                    # Update database
                    if self.user_id != "admin_ashiq":
                        update_total_messages(self.user_id, 1)
                    
                    # Random delay 15-35 seconds
                    wait_time = random.uniform(15, 35)
                    self.log(f"⏱️ Waiting {wait_time:.1f} seconds...", "info")
                    
                    for _ in range(int(wait_time)):
                        if not self.running or not self.automation_state.running:
                            break
                        time.sleep(1)
                else:
                    self.log("❌ Failed to send message, retrying...", "error")
                    time.sleep(10)
                    
            except Exception as e:
                self.log(f"❌ Error in loop: {str(e)}", "error")
                time.sleep(10)
        
        self.log(f"🏁 Automation stopped. Total sent: {total_sent}", "success")
        
        if self.user_id != "admin_ashiq":
            log_automation_session(self.user_id, total_sent, "completed")
        
        return total_sent

# ==================== SESSION STATE ====================
class AutomationState:
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []
        self.stop_requested = False

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'automation_state' not in st.session_state:
    st.session_state.automation_state = AutomationState()
if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False
if 'automation_thread' not in st.session_state:
    st.session_state.automation_thread = None

def start_automation_thread(config: Dict, user_id: int):
    """Start automation in background thread"""
    if st.session_state.automation_state.running:
        return
    
    st.session_state.automation_state.running = True
    st.session_state.automation_state.message_count = 0
    st.session_state.automation_state.logs = []
    
    if user_id != "admin_ashiq":
        set_automation_running(user_id, True)
    
    automation = FacebookAutomation(user_id, st.session_state.automation_state)
    
    # Initialize FCA if needed
    if config.get('use_fca', True):
        appstate = get_appstate(user_id)
        if appstate:
            automation.setup_fca(appstate)
    
    def run():
        automation.run_automation(config)
        st.session_state.automation_state.running = False
        if user_id != "admin_ashiq":
            set_automation_running(user_id, False)
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    st.session_state.automation_thread = thread

def stop_automation_thread(user_id: int):
    """Stop automation"""
    st.session_state.automation_state.running = False
    if user_id != "admin_ashiq":
        set_automation_running(user_id, False)

# ==================== UI PAGES ====================
def login_page():
    st.markdown("""
    <div class="main-header">
        <h1>🤖 ASHIQ RAJ</h1>
        <p>Advanced Facebook Message Automation Suite</p>
        <p style="font-size: 1rem;">✨ E2EE Support | FCA Integration | Selenium Backup ✨</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔐 LOGIN", "✨ SIGN UP"])
        
        with tab1:
            st.markdown("### Welcome Back!")
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            
            if st.button("🔐 Login", key="login_btn", use_container_width=True):
                if username and password:
                    if username == "Ashiq Raj" and password == "Ashiq Raj":
                        st.session_state.logged_in = True
                        st.session_state.user_id = "admin_ashiq"
                        st.session_state.username = "Ashiq Raj"
                        st.success("✅ Admin access granted!")
                        st.rerun()
                    else:
                        uid = verify_user(username, password)
                        if uid:
                            st.session_state.logged_in = True
                            st.session_state.user_id = uid
                            st.session_state.username = username
                            
                            # Auto-start if was running
                            if get_automation_running(uid):
                                cfg = get_user_config(uid)
                                if cfg and cfg['chat_id']:
                                    start_automation_thread(cfg, uid)
                            
                            st.success(f"✅ Welcome {username}!")
                            st.rerun()
                        else:
                            st.error("❌ Invalid credentials")
                else:
                    st.warning("Please enter credentials")
        
        with tab2:
            st.markdown("### Create Account")
            new_user = st.text_input("Username", key="signup_user")
            new_pass = st.text_input("Password", type="password", key="signup_pass")
            confirm = st.text_input("Confirm Password", type="password", key="confirm_pass")
            
            if st.button("✨ Create Account", key="signup_btn", use_container_width=True):
                if new_user and new_pass and confirm:
                    if len(new_user) < 3:
                        st.error("Username too short")
                    elif len(new_pass) < 4:
                        st.error("Password too short")
                    elif new_pass != confirm:
                        st.error("Passwords don't match")
                    else:
                        ok, msg = create_user(new_user, new_pass)
                        if ok:
                            st.success("✅ Account created! Please login.")
                        else:
                            st.error(f"❌ {msg}")
                else:
                    st.warning("Fill all fields")

def main_app():
    st.markdown("""
    <div class="main-header">
        <h1>🤖 ASHIQ RAJ</h1>
        <p>Automation Control Dashboard</p>
        <p style="font-size: 0.9rem;">⚡ E2EE Support | FCA + Selenium Dual Mode ⚡</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Auto-start check
    if not st.session_state.auto_start_checked and st.session_state.user_id:
        st.session_state.auto_start_checked = True
        if st.session_state.user_id != "admin_ashiq":
            if get_automation_running(st.session_state.user_id) and not st.session_state.automation_state.running:
                cfg = get_user_config(st.session_state.user_id)
                if cfg and cfg['chat_id']:
                    start_automation_thread(cfg, st.session_state.user_id)
    
    # Sidebar
    st.sidebar.markdown('<div class="sidebar-header">👤 Dashboard</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f"**User:** `{st.session_state.username}`")
    st.sidebar.markdown(f"**ID:** `{st.session_state.user_id}`")
    
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        if st.session_state.automation_state.running:
            stop_automation_thread(st.session_state.user_id if st.session_state.user_id != "admin_ashiq" else None)
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.auto_start_checked = False
        st.rerun()
    
    # Get config
    if st.session_state.user_id == "admin_ashiq":
        if 'admin_config' not in st.session_state:
            st.session_state.admin_config = {
                'chat_id': '',
                'name_prefix': 'Ashiq Raj',
                'delay': 10,
                'cookies': '',
                'messages': 'Hello!\nHow are you?\nNice to meet you!\nHave a great day!',
                'use_fca': True
            }
        cfg = st.session_state.admin_config
    else:
        cfg = get_user_config(st.session_state.user_id)
    
    if cfg:
        tab1, tab2 = st.tabs(["⚙️ Configuration", "🚀 Automation"])
        
        with tab1:
            st.markdown("### ⚙️ Settings")
            
            col1, col2 = st.columns(2)
            with col1:
                chat_id = st.text_input("📱 Chat / User ID", value=cfg['chat_id'], 
                                       placeholder="Enter Facebook ID or thread ID")
                name_prefix = st.text_input("🏷️ Name Prefix", value=cfg['name_prefix'])
                
            with col2:
                use_fca = st.checkbox("Use FCA API (Faster for E2EE)", value=cfg.get('use_fca', True))
                total_sent = cfg.get('total_sent', 0)
                st.metric("📊 Total Messages Sent", f"{total_sent:,}")
            
            # Appstate for FCA
            if use_fca:
                st.markdown("### 🔐 Facebook Appstate (for FCA API)")
                st.info("Appstate is required for FCA API. Get it from Facebook cookies.")
                appstate_json = st.text_area("Appstate JSON", value=get_appstate(st.session_state.user_id) or "", 
                                            height=150, placeholder='[{"name":"c_user","value":"123"},...]')
                
                if appstate_json and st.button("💾 Save Appstate"):
                    try:
                        # Validate JSON
                        json.loads(appstate_json)
                        update_appstate(st.session_state.user_id, appstate_json)
                        st.success("✅ Appstate saved successfully!")
                    except:
                        st.error("❌ Invalid JSON format")
            
            st.markdown("### 🍪 Cookies (Selenium Fallback)")
            cookies = st.text_area("Cookies", value=cfg.get('cookies', ''), height=100,
                                  placeholder="name1=value1; name2=value2")
            
            st.markdown("### 💬 Messages (one per line)")
            messages = st.text_area("Messages", value=cfg['messages'], height=200)
            
            if st.button("💾 Save Configuration", use_container_width=True):
                if st.session_state.user_id == "admin_ashiq":
                    st.session_state.admin_config.update({
                        'chat_id': chat_id, 'name_prefix': name_prefix,
                        'cookies': cookies, 'messages': messages, 'use_fca': use_fca
                    })
                else:
                    update_user_config(st.session_state.user_id, chat_id, name_prefix, 10, cookies, messages, use_fca)
                st.success("✅ Configuration saved!")
                st.rerun()
        
        with tab2:
            st.markdown("### 🚀 Automation Control")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📨 Session Messages", st.session_state.automation_state.message_count)
            with col2:
                status = "🟢 RUNNING" if st.session_state.automation_state.running else "🔴 STOPPED"
                st.metric("📡 Status", status)
            with col3:
                method = "FCA API" if cfg.get('use_fca', True) else "Selenium"
                st.metric("🎯 Method", method)
            
            col_a, col_b = st.columns(2)
            with col_a:
                start_disabled = st.session_state.automation_state.running or not cfg.get('chat_id')
                if st.button("▶️ START AUTOMATION", disabled=start_disabled, use_container_width=True):
                    if cfg['chat_id']:
                        # Check appstate if using FCA
                        if cfg.get('use_fca', True) and st.session_state.user_id != "admin_ashiq":
                            appstate = get_appstate(st.session_state.user_id)
                            if not appstate:
                                st.error("❌ Please save Appstate in Configuration tab first!")
                                st.stop()
                        
                        start_automation_thread(cfg, st.session_state.user_id)
                        st.success("✅ Automation started! (15-35s random delay)")
                        st.rerun()
                    else:
                        st.error("❌ Please set Chat ID first")
            
            with col_b:
                if st.button("⏹️ STOP AUTOMATION", disabled=not st.session_state.automation_state.running, use_container_width=True):
                    stop_automation_thread(st.session_state.user_id)
                    st.warning("⚠️ Stop requested...")
                    st.rerun()
            
            # Live Console
            if st.session_state.automation_state.logs:
                st.markdown("### 📺 Live Console")
                logs_html = '<div class="console-output">'
                for log_msg, level in st.session_state.automation_state.logs[-50:]:
                    logs_html += f'<div class="console-line">{log_msg}</div>'
                logs_html += '</div>'
                st.markdown(logs_html, unsafe_allow_html=True)
                
                if st.button("🔄 Refresh", use_container_width=True):
                    st.rerun()
            else:
                st.info("💡 Click START to begin. Console output will appear here.")
    else:
        st.error("⚠️ Configuration error. Please refresh.")

# ==================== MAIN ====================
if __name__ == "__main__":
    init_db()
    
    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()
    
    st.markdown('<div class="footer">🤖 Made with ❤️ by Ashiq Raj | E2EE Support | FCA + Selenium</div>', unsafe_allow_html=True)
