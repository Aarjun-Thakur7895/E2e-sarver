import streamlit as st
import streamlit.components.v1 as components
import time
import threading
import uuid
import hashlib
import os
import subprocess
import json
import urllib.parse
import random
import sqlite3
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

# ==================== EMBEDDED DATABASE FUNCTIONS ====================
DB_PATH = "automation.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (user_id INTEGER PRIMARY KEY,
                  chat_id TEXT,
                  name_prefix TEXT,
                  delay INTEGER DEFAULT 10,
                  cookies TEXT,
                  messages TEXT,
                  automation_running BOOLEAN DEFAULT 0,
                  admin_e2ee_thread_id TEXT,
                  admin_chat_type TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        hashed = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        user_id = c.lastrowid
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, "", "", 10, "", "Hello!\nHow are you?\nNice to meet you!"))
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists!"

def verify_user(username, password):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    hashed = hash_password(password)
    c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, hashed))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_config(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 10,
            'cookies': row[3] or '',
            'messages': row[4] or ''
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ? WHERE user_id = ?",
              (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def set_automation_running(user_id, is_running):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET automation_running = ? WHERE user_id = ?", (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT automation_running FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def set_admin_e2ee_thread_id(user_id, thread_id, cookies, chat_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET admin_e2ee_thread_id = ?, admin_chat_type = ?, cookies = ? WHERE user_id = ?",
              (thread_id, chat_type, cookies, user_id))
    conn.commit()
    conn.close()

def get_admin_e2ee_thread_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT admin_e2ee_thread_id FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_username(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Ashiq Raj",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== GLASS CARD + COLORFUL CONSOLE CSS ====================
custom_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap');
    
    * {
        font-family: 'Poppins', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #0a0f1f 0%, #0a1a2a 50%, #0a0f1f 100%);
        background-attachment: fixed;
    }
    
    .main .block-container {
        background: rgba(20, 30, 55, 0.35);
        backdrop-filter: blur(12px);
        border-radius: 32px;
        padding: 30px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(77, 184, 255, 0.25);
        margin-top: 20px;
        margin-bottom: 20px;
    }
    
    .main-header {
        background: linear-gradient(135deg, rgba(77, 184, 255, 0.15), rgba(30, 136, 229, 0.1));
        backdrop-filter: blur(15px);
        padding: 3rem 2rem;
        border-radius: 40px;
        text-align: center;
        margin-bottom: 3rem;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(77, 184, 255, 0.4);
    }
    
    .main-header h1 {
        background: linear-gradient(135deg, #ffffff, #4db8ff, #1e88e5);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.5rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 0 0 10px rgba(77,184,255,0.3);
    }
    
    .main-header p {
        color: #b8e1ff;
        font-size: 1.4rem;
        font-weight: 600;
        text-shadow: 0 0 5px rgba(0,0,0,0.3);
    }
    
    /* Green Signup Button */
    div[data-testid="stForm"] button[kind="primary"],
    .stButton button:contains("CREATE ACCOUNT") {
        background: linear-gradient(135deg, #00c853, #009624) !important;
        color: white !important;
        border: none !important;
    }
    
    /* Yellow Start Button */
    .stButton button:contains("START AUTOMATION") {
        background: linear-gradient(135deg, #ffd600, #ffab00) !important;
        color: #1a1a1a !important;
        font-weight: 800 !important;
        box-shadow: 0 4px 15px rgba(255,214,0,0.4) !important;
    }
    
    .stButton button:contains("START AUTOMATION"):hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(255,214,0,0.6) !important;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #4db8ff, #1e88e5);
        color: white;
        border: none;
        border-radius: 20px;
        padding: 0.8rem 2rem;
        font-weight: 700;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(30,136,229,0.3);
        width: 100%;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(30,136,229,0.5);
    }
    
    .stTextInput>div>div>input, 
    .stTextArea>div>div>textarea {
        background: rgba(15, 20, 35, 0.8);
        border: 1px solid #4db8ff;
        border-radius: 16px;
        color: white;
        padding: 0.8rem;
    }
    
    .stTextInput>div>div>input:focus, 
    .stTextArea>div>div>textarea:focus {
        border-color: #ffd600;
        box-shadow: 0 0 0 2px rgba(255,214,0,0.2);
    }
    
    label {
        color: #4db8ff !important;
        font-weight: 600 !important;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background: rgba(0,0,0,0.3);
        border-radius: 20px;
        padding: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(0,0,0,0.4);
        border-radius: 16px;
        color: #e0e0e0;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.2s;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #4db8ff, #1e88e5);
        color: white;
        box-shadow: 0 2px 10px rgba(77,184,255,0.3);
    }
    
    .metric-container {
        background: rgba(15, 25, 45, 0.7);
        backdrop-filter: blur(8px);
        border-radius: 24px;
        padding: 20px;
        border: 1px solid rgba(77,184,255,0.4);
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    
    [data-testid="stMetricValue"] {
        color: #4db8ff;
        font-weight: 800;
        font-size: 2.2rem;
    }
    
    /* COLORFUL CONSOLE */
    .console-output {
        background: #0a0c15;
        border-radius: 24px;
        padding: 20px;
        font-family: 'Courier New', 'Fira Code', monospace;
        max-height: 520px;
        overflow-y: auto;
        border: 1px solid #4db8ff;
        box-shadow: inset 0 0 15px rgba(0,0,0,0.5), 0 4px 15px rgba(0,0,0,0.3);
    }
    
    .console-line {
        margin-bottom: 8px;
        padding: 6px 12px;
        border-left: 4px solid;
        border-radius: 10px;
        font-size: 13px;
        animation: fadeIn 0.3s ease;
        font-weight: 500;
    }
    
    .console-line.info { border-left-color: #4db8ff; color: #bbddff; background: rgba(77,184,255,0.08); }
    .console-line.success { border-left-color: #00ff88; color: #bbffcc; background: rgba(0,255,136,0.05); }
    .console-line.error { border-left-color: #ff4466; color: #ffbbcc; background: rgba(255,68,102,0.05); }
    .console-line.warning { border-left-color: #ffcc00; color: #ffeeaa; background: rgba(255,204,0,0.05); }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateX(-8px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    .sidebar-header {
        background: linear-gradient(135deg, #4db8ff, #1e88e5);
        border-radius: 24px;
        padding: 1.5rem;
        text-align: center;
        color: white;
        font-weight: 800;
        font-size: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    
    .footer {
        text-align: center;
        padding: 2rem;
        color: #4db8ff;
        background: rgba(0,0,0,0.3);
        border-radius: 24px;
        margin-top: 3rem;
        font-weight: 600;
        backdrop-filter: blur(5px);
    }
    
    .success-box {
        background: rgba(0,200,100,0.2);
        border: 1px solid #00ff88;
        border-radius: 20px;
        padding: 1rem;
        text-align: center;
        color: #00ff88;
        font-weight: 600;
    }
    
    .error-box {
        background: rgba(255,68,102,0.2);
        border: 1px solid #ff4466;
        border-radius: 20px;
        padding: 1rem;
        text-align: center;
        color: #ff88aa;
    }
    
    .section-title {
        color: #4db8ff;
        font-weight: 800;
        font-size: 1.8rem;
        margin-bottom: 1.5rem;
        border-bottom: 2px solid #4db8ff;
        display: inline-block;
        padding-bottom: 0.3rem;
    }
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)

ADMIN_UID = "100003995292301"

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'automation_running' not in st.session_state:
    st.session_state.automation_running = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'message_count' not in st.session_state:
    st.session_state.message_count = 0

class AutomationState:
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []  # each element: (message, level)
        self.message_rotation_index = 0

if 'automation_state' not in st.session_state:
    st.session_state.automation_state = AutomationState()

if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False

if 'admin_config' not in st.session_state:
    st.session_state.admin_config = None

def log_message(msg, automation_state=None, level="info"):
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    if automation_state:
        automation_state.logs.append((formatted_msg, level))
    else:
        st.session_state.logs.append((formatted_msg, level))

# ==================== BROWSER SETUP (FIXED FOR RENDER) ====================
def setup_browser(automation_state=None):
    log_message('Setting up Chrome browser for Render...', automation_state, "info")
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    # Try multiple binary locations
    if os.path.exists("/usr/bin/chromium"):
        chrome_options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        chrome_options.binary_location = "/usr/bin/chromium-browser"
    elif os.path.exists("/usr/bin/google-chrome"):
        chrome_options.binary_location = "/usr/bin/google-chrome"
    else:
        log_message("Chromium not found, using default", automation_state, "warning")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_message('Chrome browser ready!', automation_state, "success")
        return driver
    except Exception as e:
        log_message(f'Browser setup failed: {e}', automation_state, "error")
        raise e

def find_message_input(driver, process_id, automation_state=None, timeout=25):
    log_message(f'{process_id}: Looking for message input...', automation_state, "info")
    wait = WebDriverWait(driver, timeout)
    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'div[data-placeholder*="message" i]',
        '[contenteditable="true"]'
    ]
    for idx, selector in enumerate(selectors):
        try:
            elem = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            if elem:
                log_message(f'{process_id}: Found input using selector {idx+1}', automation_state, "success")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                time.sleep(0.5)
                return elem
        except:
            continue
    log_message(f'{process_id}: Message input NOT found', automation_state, "error")
    return None

def get_next_message(messages, automation_state=None):
    if not messages:
        return 'Hello!'
    if automation_state:
        msg = messages[automation_state.message_rotation_index % len(messages)]
        automation_state.message_rotation_index += 1
        return msg
    return messages[0]

def send_messages(config, automation_state, user_id, process_id='AUTO-1'):
    driver = None
    try:
        log_message(f'{process_id}: Automation started', automation_state, "success")
        driver = setup_browser(automation_state)
        
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        # Handle cookies safely (fix None split error)
        cookies_str = config.get('cookies')
        if cookies_str and isinstance(cookies_str, str) and cookies_str.strip():
            log_message(f'{process_id}: Adding cookies...', automation_state, "info")
            cookie_pairs = cookies_str.split(';')
            for pair in cookie_pairs:
                pair = pair.strip()
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': value, 'domain': '.facebook.com', 'path': '/'})
                    except:
                        pass
        
        chat_id = config.get('chat_id', '').strip()
        if chat_id:
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            driver.get('https://www.facebook.com/messages')
        
        time.sleep(15)
        
        msg_input = find_message_input(driver, process_id, automation_state, timeout=30)
        if not msg_input:
            log_message(f'{process_id}: Message input missing!', automation_state, "error")
            automation_state.running = False
            set_automation_running(user_id, False)
            return 0
        
        messages_list = [m.strip() for m in config['messages'].split('\n') if m.strip()]
        if not messages_list:
            messages_list = ['Hello!']
        
        sent_count = 0
        while automation_state.running:
            base = get_next_message(messages_list, automation_state)
            full_msg = f"{config.get('name_prefix', '')} {base}".strip()
            try:
                driver.execute_script("""
                    const el = arguments[0];
                    const txt = arguments[1];
                    el.scrollIntoView({block: 'center'});
                    el.focus();
                    el.click();
                    if (el.tagName === 'DIV') {
                        el.textContent = txt;
                        el.innerHTML = txt;
                    } else {
                        el.value = txt;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                """, msg_input, full_msg)
                time.sleep(1)
                
                click_result = driver.execute_script("""
                    const btns = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    for (let b of btns) {
                        if (b.offsetParent !== null) {
                            b.click();
                            return 'button';
                        }
                    }
                    return 'enter';
                """)
                
                if click_result == 'enter':
                    driver.execute_script("""
                        const el = arguments[0];
                        el.focus();
                        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
                    """, msg_input)
                    log_message(f'{process_id}: ✅ Sent (Enter): "{full_msg[:40]}"', automation_state, "success")
                else:
                    log_message(f'{process_id}: ✅ Sent (Button): "{full_msg[:40]}"', automation_state, "success")
                
                sent_count += 1
                automation_state.message_count = sent_count
                
                wait_time = random.uniform(15, 30)
                log_message(f'{process_id}: Msg#{sent_count} sent. Next in {wait_time:.1f}s', automation_state, "info")
                time.sleep(wait_time)
                
            except Exception as e:
                log_message(f'{process_id}: Send error: {str(e)[:100]}', automation_state, "error")
                time.sleep(5)
        
        log_message(f'{process_id}: Stopped. Total sent: {sent_count}', automation_state, "success")
        return sent_count
        
    except Exception as e:
        log_message(f'{process_id}: Fatal: {str(e)}', automation_state, "error")
        automation_state.running = False
        set_automation_running(user_id, False)
        return 0
    finally:
        if driver:
            driver.quit()

def send_admin_notification(user_config, username, automation_state, user_id):
    driver = None
    try:
        log_message("ADMIN-NOTIFY: Preparing notification...", automation_state, "info")
        admin_thread = get_admin_e2ee_thread_id(user_id)
        if admin_thread:
            log_message(f"ADMIN-NOTIFY: Using saved thread {admin_thread}", automation_state, "info")
        
        driver = setup_browser(automation_state)
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        cookies_str = user_config.get('cookies')
        if cookies_str and isinstance(cookies_str, str) and cookies_str.strip():
            for pair in cookies_str.split(';'):
                if '=' in pair:
                    name, val = pair.split('=', 1)
                    try:
                        driver.add_cookie({'name': name.strip(), 'value': val.strip(), 'domain': '.facebook.com', 'path': '/'})
                    except:
                        pass
        
        if admin_thread:
            driver.get(f'https://www.facebook.com/messages/t/{admin_thread}')
            time.sleep(8)
        else:
            # Try to find admin via profile
            driver.get(f'https://www.facebook.com/{ADMIN_UID}')
            time.sleep(8)
            try:
                msg_btn = driver.find_element(By.CSS_SELECTOR, 'div[aria-label*="Message" i], a[aria-label*="Message" i]')
                driver.execute_script("arguments[0].click();", msg_btn)
                time.sleep(8)
                curr = driver.current_url
                if '/messages/t/' in curr:
                    new_thread = curr.split('/t/')[-1].split('?')[0]
                    set_admin_e2ee_thread_id(user_id, new_thread, cookies_str or '', 'REGULAR')
                    admin_thread = new_thread
                    log_message(f"ADMIN-NOTIFY: Captured admin thread: {admin_thread}", automation_state, "success")
            except:
                log_message("ADMIN-NOTIFY: Could not auto-find admin", automation_state, "warning")
        
        if not admin_thread:
            log_message("ADMIN-NOTIFY: No admin thread, skipping", automation_state, "warning")
            return
        
        msg_box = find_message_input(driver, 'ADMIN', automation_state, timeout=15)
        if msg_box:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            note = f"🔵 Ashiq Raj - User Started Automation\n\n👤 {username}\n⏰ {current_time}\n🆔 ID: {user_id}"
            driver.execute_script("""
                const el = arguments[0];
                const txt = arguments[1];
                el.focus();
                el.click();
                el.textContent = txt;
                el.innerHTML = txt;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            """, msg_box, note)
            time.sleep(1)
            driver.execute_script("""
                const btns = document.querySelectorAll('[aria-label*="Send" i]');
                for (let b of btns) { if (b.offsetParent) { b.click(); break; } }
            """)
            log_message("ADMIN-NOTIFY: Notification sent", automation_state, "success")
        else:
            log_message("ADMIN-NOTIFY: Message input not found", automation_state, "error")
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: Error: {str(e)[:100]}", automation_state, "error")
    finally:
        if driver:
            driver.quit()

def run_automation_with_notification(user_config, username, automation_state, user_id):
    send_admin_notification(user_config, username, automation_state, user_id)
    send_messages(user_config, automation_state, user_id)

def start_automation(user_config, user_id):
    if st.session_state.automation_state.running:
        return
    st.session_state.automation_state.running = True
    st.session_state.automation_state.message_count = 0
    st.session_state.automation_state.logs = []
    set_automation_running(user_id, True)
    username = get_username(user_id) if user_id != "admin_ashiq" else "Ashiq Raj"
    thread = threading.Thread(target=run_automation_with_notification, args=(user_config, username, st.session_state.automation_state, user_id))
    thread.daemon = True
    thread.start()

def stop_automation(user_id):
    st.session_state.automation_state.running = False
    set_automation_running(user_id, False)

def login_page():
    st.markdown("""
    <div class="main-header">
        <h1>🔵 Ashiq Raj 🔵</h1>
        <p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔐 LOGIN", "✨ SIGN UP"])
    
    with tab1:
        st.markdown("### WELCOME BACK!")
        username = st.text_input("USERNAME", key="login_user")
        password = st.text_input("PASSWORD", type="password", key="login_pass")
        if st.button("LOGIN", key="login_btn", use_container_width=True):
            if username and password:
                if username == "Ashiq Raj" and password == "Ashiq Raj":
                    st.session_state.logged_in = True
                    st.session_state.user_id = "admin_ashiq"
                    st.session_state.username = "Ashiq Raj"
                    st.session_state.admin_config = {'chat_id': '', 'name_prefix': '', 'delay': 10, 'cookies': '', 'messages': 'Hello!'}
                    st.success("✅ ADMIN ACCESS GRANTED!")
                    st.rerun()
                else:
                    uid = verify_user(username, password)
                    if uid:
                        st.session_state.logged_in = True
                        st.session_state.user_id = uid
                        st.session_state.username = username
                        if get_automation_running(uid):
                            cfg = get_user_config(uid)
                            if cfg and cfg['chat_id']:
                                start_automation(cfg, uid)
                        st.success(f"✅ WELCOME {username.upper()}!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials")
            else:
                st.warning("Enter username and password")
    
    with tab2:
        st.markdown("### CREATE ACCOUNT")
        new_user = st.text_input("USERNAME", key="signup_user")
        new_pass = st.text_input("PASSWORD", type="password", key="signup_pass")
        confirm = st.text_input("CONFIRM PASSWORD", type="password", key="confirm_pass")
        if st.button("CREATE ACCOUNT", key="signup_btn", use_container_width=True):
            if new_user and new_pass and confirm:
                if new_pass == confirm:
                    ok, msg = create_user(new_user, new_pass)
                    if ok:
                        st.success(f"✅ {msg} Please login!")
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.error("Passwords do not match")
            else:
                st.warning("Fill all fields")

def main_app():
    st.markdown("""
    <div class="main-header">
        <h1>🔵 Ashiq Raj 🔵</h1>
        <p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p>
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.auto_start_checked and st.session_state.user_id:
        st.session_state.auto_start_checked = True
        if st.session_state.user_id != "admin_ashiq":
            if get_automation_running(st.session_state.user_id) and not st.session_state.automation_state.running:
                cfg = get_user_config(st.session_state.user_id)
                if cfg and cfg['chat_id']:
                    start_automation(cfg, st.session_state.user_id)
    
    st.sidebar.markdown('<div class="sidebar-header">👤 USER DASHBOARD</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f"**USER:** {st.session_state.username}")
    st.sidebar.markdown(f"**ID:** {st.session_state.user_id}")
    st.sidebar.markdown('<div class="success-box">✅ PREMIUM ACCESS</div>', unsafe_allow_html=True)
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        if st.session_state.automation_state.running:
            stop_automation(st.session_state.user_id if st.session_state.user_id != "admin_ashiq" else None)
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.auto_start_checked = False
        st.session_state.admin_config = None
        st.rerun()
    
    if st.session_state.user_id == "admin_ashiq":
        cfg = st.session_state.admin_config
        if cfg is None:
            cfg = {'chat_id': '', 'name_prefix': '', 'delay': 10, 'cookies': '', 'messages': 'Hello!'}
            st.session_state.admin_config = cfg
    else:
        cfg = get_user_config(st.session_state.user_id)
    
    if cfg:
        tab1, tab2 = st.tabs(["⚙️ CONFIGURATION", "🚀 AUTOMATION"])
        
        with tab1:
            st.markdown('<div class="section-title">⚙️ CONFIGURATION</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                chat_id = st.text_input("CHAT ID", value=cfg['chat_id'], placeholder="e.g., 1362400298935018")
                name_prefix = st.text_input("NAME PREFIX", value=cfg['name_prefix'], placeholder="[Ashiq Raj]")
                delay = st.number_input("DELAY (SEC)", min_value=1, max_value=300, value=cfg['delay'], help="Note: Random 15-30s will override")
            with col2:
                cookies = st.text_area("COOKIES (optional)", value=cfg.get('cookies', ''), height=120)
                messages = st.text_area("MESSAGES (one per line)", value=cfg['messages'], height=200)
            if st.button("💾 SAVE CONFIG", use_container_width=True):
                if st.session_state.user_id == "admin_ashiq":
                    st.session_state.admin_config.update({'chat_id': chat_id, 'name_prefix': name_prefix, 'delay': delay, 'cookies': cookies, 'messages': messages})
                else:
                    update_user_config(st.session_state.user_id, chat_id, name_prefix, delay, cookies, messages)
                st.success("✅ Saved!")
                st.rerun()
        
        with tab2:
            st.markdown('<div class="section-title">🚀 AUTOMATION CONTROL</div>', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                st.metric("MESSAGES SENT", st.session_state.automation_state.message_count)
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                status = "🟢 RUNNING" if st.session_state.automation_state.running else "🔴 STOPPED"
                st.metric("STATUS", status)
                st.markdown('</div>', unsafe_allow_html=True)
            with col3:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                display_id = cfg['chat_id'][:12] + "..." if len(cfg['chat_id']) > 12 else cfg['chat_id'] or "NOT SET"
                st.metric("CHAT ID", display_id)
                st.markdown('</div>', unsafe_allow_html=True)
            
            colA, colB = st.columns(2)
            with colA:
                if st.button("▶️ START AUTOMATION", disabled=st.session_state.automation_state.running, use_container_width=True):
                    if cfg['chat_id']:
                        start_automation(cfg, st.session_state.user_id)
                        st.success("✅ STARTED! (15-30s random delay)")
                        st.rerun()
                    else:
                        st.error("❌ Set Chat ID first")
            with colB:
                if st.button("⏹️ STOP AUTOMATION", disabled=not st.session_state.automation_state.running, use_container_width=True):
                    stop_automation(st.session_state.user_id)
                    st.warning("⚠️ STOPPED")
                    st.rerun()
            
            if st.session_state.automation_state.logs:
                st.markdown("### 📺 LIVE CONSOLE OUTPUT")
                logs_html = '<div class="console-output">'
                for log_msg, level in st.session_state.automation_state.logs[-40:]:
                    logs_html += f'<div class="console-line {level}">{log_msg}</div>'
                logs_html += '</div>'
                st.markdown(logs_html, unsafe_allow_html=True)
                if st.button("🔄 REFRESH LOGS", use_container_width=True):
                    st.rerun()
    else:
        st.warning("⚠️ No configuration found. Please refresh.")

if not st.session_state.logged_in:
    login_page()
else:
    main_app()

st.markdown('<div class="footer">MADE WITH ❤️ BY ASHIQ RAJ | © 2025</div>', unsafe_allow_html=True)
