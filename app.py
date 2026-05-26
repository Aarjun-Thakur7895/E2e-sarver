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
import sqlite3
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import requests

# ==================== DATABASE HANDLING (self-contained) ====================
DB_PATH = "ashiq_raj.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    # User configurations
    c.execute('''CREATE TABLE IF NOT EXISTS user_configs (
                    user_id INTEGER PRIMARY KEY,
                    chat_id TEXT,
                    name_prefix TEXT,
                    delay INTEGER DEFAULT 10,
                    cookies TEXT,
                    messages TEXT,
                    automation_running INTEGER DEFAULT 0,
                    admin_e2ee_thread_id TEXT,
                    admin_chat_type TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        hashed = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        user_id = c.lastrowid
        # Create default config
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, "", "", 10, "", "Hello!"))
        conn.commit()
        conn.close()
        return True, "Account created successfully."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists."
    except Exception as e:
        conn.close()
        return False, str(e)

def verify_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    hashed = hash_password(password)
    c.execute("SELECT id FROM users WHERE username=? AND password=?", (username, hashed))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_username(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_config(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_configs WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 10,
            'cookies': row[3] or '',
            'messages': row[4] or 'Hello!'
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE user_configs 
                 SET chat_id=?, name_prefix=?, delay=?, cookies=?, messages=?
                 WHERE user_id=?''',
              (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT automation_running FROM user_configs WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def set_automation_running(user_id, running):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET automation_running=? WHERE user_id=?", (1 if running else 0, user_id))
    conn.commit()
    conn.close()

def get_admin_e2ee_thread_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT admin_e2ee_thread_id, admin_chat_type FROM user_configs WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]  # thread id
    return None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies, chat_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET admin_e2ee_thread_id=?, admin_chat_type=?, cookies=? WHERE user_id=?",
              (thread_id, chat_type, cookies, user_id))
    conn.commit()
    conn.close()

# Initialize DB on first run
init_db()

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Ashiq Raj",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS ====================
custom_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap');
    * { font-family: 'Poppins', sans-serif; }
    .stApp {
        background: linear-gradient(135deg, #e6f7ff 0%, #b3e0ff 50%, #80ceff 100%);
        background-size: cover;
        background-attachment: fixed;
    }
    .main .block-container {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 8px 32px rgba(0, 100, 200, 0.2);
        margin-top: 20px;
        margin-bottom: 20px;
    }
    .main-header {
        background: linear-gradient(135deg, #4db8ff 0%, #1e88e5 50%, #0d47a1 100%);
        padding: 3rem 2rem;
        border-radius: 25px;
        text-align: center;
        margin-bottom: 3rem;
        box-shadow: 0 15px 40px rgba(30, 136, 229, 0.3);
        border: 3px solid rgba(255, 255, 255, 0.3);
        position: relative;
        overflow: hidden;
    }
    .main-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.1) 50%, transparent 70%);
        animation: shine 3s infinite;
    }
    @keyframes shine {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
    }
    .main-header h1 {
        color: white;
        font-size: 3.5rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 3px 3px 10px rgba(0, 0, 0, 0.3);
    }
    .main-header p {
        color: rgba(255, 255, 255, 0.95);
        font-size: 1.4rem;
        font-weight: 600;
        margin-top: 1rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #4db8ff 0%, #1e88e5 100%);
        color: white;
        border: none;
        border-radius: 15px;
        padding: 1rem 2.5rem;
        font-weight: 700;
        font-size: 1.1rem;
        transition: all 0.3s ease;
        box-shadow: 0 6px 20px rgba(30, 136, 229, 0.4);
        width: 100%;
        text-transform: uppercase;
    }
    .stButton>button:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(30, 136, 229, 0.6);
    }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background: rgba(255, 255, 255, 0.9);
        border: 2px solid #80ceff;
        border-radius: 12px;
        padding: 1rem;
        font-weight: 500;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background: rgba(128, 206, 255, 0.2);
        padding: 15px;
        border-radius: 15px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.8);
        border-radius: 12px;
        color: #1e88e5;
        padding: 12px 25px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #4db8ff 0%, #1e88e5 100%);
        color: white;
    }
    [data-testid="stMetricValue"] {
        color: #1e88e5;
        font-weight: 800;
        font-size: 2.2rem;
    }
    .console-output {
        background: #1a1a1a;
        border: 2px solid #1e88e5;
        border-radius: 12px;
        padding: 15px;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        color: #00ff88;
        line-height: 1.7;
        max-height: 500px;
        overflow-y: auto;
    }
    .console-line {
        margin-bottom: 5px;
        padding: 8px 12px;
        padding-left: 35px;
        border-left: 3px solid #1e88e5;
        position: relative;
        border-radius: 5px;
        background: rgba(30, 136, 229, 0.05);
    }
    .console-line::before {
        content: '▶';
        position: absolute;
        left: 12px;
        color: #1e88e5;
        font-weight: bold;
    }
    .success-box {
        background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-weight: 700;
    }
    .error-box {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-weight: 700;
    }
    .footer {
        text-align: center;
        padding: 2rem;
        color: #1e88e5;
        font-weight: 800;
        margin-top: 3rem;
        background: rgba(255, 255, 255, 0.9);
        border-radius: 20px;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==================== CONSTANTS ====================
ADMIN_UID = "100003995292301"

# ==================== SESSION STATE INIT ====================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'automation_state' not in st.session_state:
    class AutomationState:
        def __init__(self):
            self.running = False
            self.message_count = 0
            self.logs = []
            self.message_rotation_index = 0
    st.session_state.automation_state = AutomationState()
if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False

# ==================== HELPER FUNCTIONS ====================
def log_message(msg, automation_state=None):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    if automation_state:
        automation_state.logs.append(formatted)
    else:
        # fallback to session logs (not used much)
        pass

def setup_browser(automation_state=None):
    log_message("Setting up Chrome browser...", automation_state)
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    # For Render.com – adjust binary if needed
    chrome_options.binary_location = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_message("Browser started successfully.", automation_state)
        return driver
    except Exception as e:
        log_message(f"Browser setup failed: {e}", automation_state)
        raise

def find_message_input(driver, process_id, automation_state=None):
    log_message(f"{process_id}: Searching for message input...", automation_state)
    time.sleep(5)

    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'div[aria-placeholder*="message" i]',
        '[contenteditable="true"]',
        'textarea',
        'input[type="text"]'
    ]

    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    log_message(f"{process_id}: Found potential input with selector: {selector[:50]}", automation_state)
                    return el
        except:
            continue
    log_message(f"{process_id}: ❌ Message input not found!", automation_state)
    return None

def send_message_via_driver(driver, message_input, message_text, automation_state=None):
    try:
        driver.execute_script("""
            const el = arguments[0];
            const txt = arguments[1];
            el.scrollIntoView({behavior: 'smooth', block: 'center'});
            el.click();
            el.focus();
            if (el.tagName === 'DIV') {
                el.textContent = txt;
                el.innerHTML = txt;
            } else {
                el.value = txt;
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        """, message_input, message_text)
        time.sleep(1)

        # Try send button first
        sent = driver.execute_script("""
            const btns = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
            for (let btn of btns) {
                if (btn.offsetParent !== null) {
                    btn.click();
                    return true;
                }
            }
            return false;
        """)
        if sent:
            log_message(f"✅ Sent via button: \"{message_text[:50]}...\"", automation_state)
            return True
        else:
            # Fallback: Enter key
            driver.execute_script("""
                const el = arguments[0];
                el.focus();
                const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
                el.dispatchEvent(enterEvent);
            """, message_input)
            log_message(f"✅ Sent via Enter: \"{message_text[:50]}...\"", automation_state)
            return True
    except Exception as e:
        log_message(f"Send error: {str(e)[:100]}", automation_state)
        return False

def get_next_message(messages_list, automation_state):
    if not messages_list:
        return "Hello!"
    msg = messages_list[automation_state.message_rotation_index % len(messages_list)]
    automation_state.message_rotation_index += 1
    return msg

def send_admin_notification(user_config, username, automation_state, user_id):
    driver = None
    try:
        log_message("ADMIN-NOTIFY: Starting admin notification...", automation_state)
        driver = setup_browser(automation_state)
        driver.get("https://www.facebook.com/")
        time.sleep(8)

        # Add cookies if provided
        if user_config.get('cookies'):
            for cookie in user_config['cookies'].split(';'):
                cookie = cookie.strip()
                if '=' in cookie:
                    name, val = cookie.split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': val, 'domain': '.facebook.com', 'path': '/'})
                    except:
                        pass

        # Try to open existing admin thread
        admin_thread = get_admin_e2ee_thread_id(user_id)
        if admin_thread:
            driver.get(f"https://www.facebook.com/messages/t/{admin_thread}")
            time.sleep(8)
        else:
            # Open new message to admin
            driver.get("https://www.facebook.com/messages/new")
            time.sleep(5)
            # Find recipient input
            recipient_input = None
            for sel in ['input[aria-label*="To:" i]', 'input[placeholder*="Type a name" i]', 'input[type="text"]']:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for e in els:
                        if e.is_displayed():
                            recipient_input = e
                            break
                    if recipient_input:
                        break
                except:
                    continue
            if recipient_input:
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input'));", recipient_input, ADMIN_UID)
                time.sleep(3)
                # Click first result
                try:
                    result = driver.find_element(By.CSS_SELECTOR, 'div[role="option"], li[role="option"]')
                    result.click()
                    time.sleep(5)
                except:
                    pass

        # Find message input and send notification
        msg_input = find_message_input(driver, "ADMIN-NOTIFY", automation_state)
        if msg_input:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notification = f"🔵 Ashiq Raj - User Started Automation\n\n👤 Username: {username}\n⏰ Time: {current_time}\n🆔 User ID: {user_id}"
            send_message_via_driver(driver, msg_input, notification, automation_state)
            log_message("ADMIN-NOTIFY: Notification sent successfully.", automation_state)

            # Save admin thread id if we got a new one
            current_url = driver.current_url
            if '/messages/t/' in current_url:
                tid = current_url.split('/messages/t/')[-1].split('?')[0].split('/')[0]
                if tid:
                    set_admin_e2ee_thread_id(user_id, tid, user_config.get('cookies', ''), 'REGULAR')
            elif '/e2ee/t/' in current_url:
                tid = current_url.split('/e2ee/t/')[-1].split('?')[0].split('/')[0]
                if tid:
                    set_admin_e2ee_thread_id(user_id, tid, user_config.get('cookies', ''), 'E2EE')
        else:
            log_message("ADMIN-NOTIFY: Could not find message input to send notification.", automation_state)
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: Error: {str(e)}", automation_state)
    finally:
        if driver:
            driver.quit()

def send_messages_loop(user_config, automation_state, user_id):
    driver = None
    try:
        log_message("AUTO: Starting message sending loop...", automation_state)
        driver = setup_browser(automation_state)
        driver.get("https://www.facebook.com/")
        time.sleep(8)

        # Add cookies
        if user_config.get('cookies'):
            for cookie in user_config['cookies'].split(';'):
                cookie = cookie.strip()
                if '=' in cookie:
                    name, val = cookie.split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': val, 'domain': '.facebook.com', 'path': '/'})
                    except:
                        pass

        # Open target chat
        if user_config['chat_id']:
            driver.get(f"https://www.facebook.com/messages/t/{user_config['chat_id']}")
        else:
            driver.get("https://www.facebook.com/messages")
        time.sleep(10)

        message_input = find_message_input(driver, "AUTO", automation_state)
        if not message_input:
            log_message("AUTO: ❌ Could not find message input. Stopping.", automation_state)
            automation_state.running = False
            set_automation_running(user_id, False)
            return

        messages_list = [m.strip() for m in user_config['messages'].split('\n') if m.strip()]
        if not messages_list:
            messages_list = ["Hello!"]

        delay = max(1, int(user_config.get('delay', 10)))

        while automation_state.running:
            try:
                # Refresh driver if stale (re-find input)
                if not driver.window_handles:
                    raise Exception("Browser closed")
                # Re-find input each loop to avoid stale element
                message_input = find_message_input(driver, "AUTO", automation_state)
                if not message_input:
                    log_message("AUTO: Message input disappeared, re-finding...", automation_state)
                    time.sleep(5)
                    continue

                base_msg = get_next_message(messages_list, automation_state)
                if user_config.get('name_prefix'):
                    full_msg = f"{user_config['name_prefix']} {base_msg}"
                else:
                    full_msg = base_msg

                success = send_message_via_driver(driver, message_input, full_msg, automation_state)
                if success:
                    automation_state.message_count += 1
                    log_message(f"AUTO: Message #{automation_state.message_count} sent. Waiting {delay}s...", automation_state)
                else:
                    log_message("AUTO: Failed to send message, retrying in 10s...", automation_state)
                    time.sleep(10)
                    continue

                time.sleep(delay)
            except Exception as e:
                log_message(f"AUTO: Loop error: {str(e)[:100]}. Re-initializing browser...", automation_state)
                # Recreate driver
                try:
                    driver.quit()
                except:
                    pass
                driver = setup_browser(automation_state)
                driver.get("https://www.facebook.com/")
                time.sleep(8)
                # Re-apply cookies
                if user_config.get('cookies'):
                    for cookie in user_config['cookies'].split(';'):
                        cookie = cookie.strip()
                        if '=' in cookie:
                            name, val = cookie.split('=', 1)
                            try:
                                driver.add_cookie({'name': name, 'value': val, 'domain': '.facebook.com', 'path': '/'})
                            except:
                                pass
                driver.get(f"https://www.facebook.com/messages/t/{user_config['chat_id']}")
                time.sleep(10)

    except Exception as e:
        log_message(f"AUTO: Fatal error: {str(e)}", automation_state)
    finally:
        if driver:
            driver.quit()
        automation_state.running = False
        set_automation_running(user_id, False)
        log_message("AUTO: Automation stopped.", automation_state)

def start_automation(user_config, user_id):
    if st.session_state.automation_state.running:
        return
    st.session_state.automation_state.running = True
    st.session_state.automation_state.message_count = 0
    st.session_state.automation_state.logs = []
    set_automation_running(user_id, True)

    # Send admin notification in background
    def notify_and_run():
        username = get_username(user_id) or "User"
        send_admin_notification(user_config, username, st.session_state.automation_state, user_id)
        # Wait a few seconds then start the main loop
        time.sleep(5)
        send_messages_loop(user_config, st.session_state.automation_state, user_id)

    thread = threading.Thread(target=notify_and_run, daemon=True)
    thread.start()

def stop_automation(user_id):
    st.session_state.automation_state.running = False
    set_automation_running(user_id, False)

# ==================== UI PAGES ====================
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
        if st.button("LOGIN", use_container_width=True):
            if username == "Ashiq Raj" and password == "Ashiq Raj":
                st.session_state.logged_in = True
                st.session_state.user_id = "admin_ashiq"
                st.session_state.username = "Ashiq Raj"
                st.success("Welcome Admin!")
                st.rerun()
            else:
                uid = verify_user(username, password)
                if uid:
                    st.session_state.logged_in = True
                    st.session_state.user_id = uid
                    st.session_state.username = username
                    # Auto-start if previously running
                    if get_automation_running(uid):
                        cfg = get_user_config(uid)
                        if cfg and cfg['chat_id']:
                            start_automation(cfg, uid)
                    st.success(f"Welcome {username}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials!")
    with tab2:
        st.markdown("### CREATE NEW ACCOUNT")
        new_user = st.text_input("USERNAME", key="new_user")
        new_pass = st.text_input("PASSWORD", type="password", key="new_pass")
        confirm = st.text_input("CONFIRM PASSWORD", type="password", key="confirm")
        if st.button("SIGN UP", use_container_width=True):
            if new_user and new_pass and new_pass == confirm:
                ok, msg = create_user(new_user, new_pass)
                if ok:
                    st.success(msg + " Please login.")
                else:
                    st.error(msg)
            else:
                st.warning("Fill all fields correctly.")

def main_app():
    st.markdown("""
    <div class="main-header">
        <h1>🔵 Ashiq Raj 🔵</h1>
        <p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p>
    </div>
    """, unsafe_allow_html=True)

    # Auto-start check for normal users
    if not st.session_state.auto_start_checked and st.session_state.user_id != "admin_ashiq":
        st.session_state.auto_start_checked = True
        if get_automation_running(st.session_state.user_id) and not st.session_state.automation_state.running:
            cfg = get_user_config(st.session_state.user_id)
            if cfg and cfg['chat_id']:
                start_automation(cfg, st.session_state.user_id)

    # Sidebar
    st.sidebar.markdown('<div class="sidebar-header">👤 USER DASHBOARD</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f"**USER:** {st.session_state.username}")
    st.sidebar.markdown(f"**ID:** {st.session_state.user_id}")
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        if st.session_state.automation_state.running:
            stop_automation(st.session_state.user_id)
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.auto_start_checked = False
        st.session_state.automation_state = AutomationState()
        st.rerun()

    # Load config
    if st.session_state.user_id == "admin_ashiq":
        # Admin in-memory config (or you could store in DB as well)
        if 'admin_config' not in st.session_state:
            st.session_state.admin_config = {
                'chat_id': '',
                'name_prefix': '',
                'delay': 10,
                'cookies': '',
                'messages': 'Hello!\nHi there!\nHow are you?'
            }
        user_config = st.session_state.admin_config
    else:
        user_config = get_user_config(st.session_state.user_id)
        if user_config is None:
            st.warning("No configuration found. Please refresh.")
            return

    tab1, tab2 = st.tabs(["⚙️ CONFIGURATION", "🚀 AUTOMATION"])

    with tab1:
        st.markdown("### CONFIGURATION SETTINGS")
        col1, col2 = st.columns(2)
        with col1:
            chat_id = st.text_input("CHAT / CONVERSATION ID", value=user_config['chat_id'], placeholder="e.g., 1362400298935018")
            name_prefix = st.text_input("NAME PREFIX (optional)", value=user_config['name_prefix'], placeholder="e.g., [Ashiq Raj]")
            delay = st.number_input("DELAY (seconds)", min_value=1, max_value=300, value=int(user_config['delay']))
        with col2:
            cookies = st.text_area("FACEBOOK COOKIES (optional)", value=user_config.get('cookies', ''), height=100,
                                   help="Cookies will be encrypted in DB. Leave empty if not needed.")
            messages = st.text_area("MESSAGES (one per line)", value=user_config['messages'], height=200,
                                    help="Each message on a new line. They will rotate.")
        if st.button("💾 SAVE CONFIGURATION", use_container_width=True):
            if st.session_state.user_id == "admin_ashiq":
                st.session_state.admin_config.update({
                    'chat_id': chat_id,
                    'name_prefix': name_prefix,
                    'delay': delay,
                    'cookies': cookies,
                    'messages': messages
                })
            else:
                update_user_config(st.session_state.user_id, chat_id, name_prefix, delay, cookies, messages)
            st.success("Configuration saved successfully!")
            st.rerun()

    with tab2:
        st.markdown("### AUTOMATION CONTROL")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("MESSAGES SENT", st.session_state.automation_state.message_count)
        with col2:
            status = "🟢 RUNNING" if st.session_state.automation_state.running else "🔴 STOPPED"
            st.metric("STATUS", status)
        with col3:
            cid = user_config['chat_id']
            display_cid = cid[:8] + "..." if len(cid) > 8 else cid or "NOT SET"
            st.metric("CHAT ID", display_cid)

        colA, colB = st.columns(2)
        with colA:
            if st.button("▶️ START AUTOMATION", disabled=st.session_state.automation_state.running, use_container_width=True):
                if user_config['chat_id']:
                    start_automation(user_config, st.session_state.user_id)
                    st.success("Automation started!")
                    st.rerun()
                else:
                    st.error("Please set a Chat ID in Configuration first!")
        with colB:
            if st.button("⏹️ STOP AUTOMATION", disabled=not st.session_state.automation_state.running, use_container_width=True):
                stop_automation(st.session_state.user_id)
                st.warning("Automation stopped.")
                st.rerun()

        if st.session_state.automation_state.logs:
            st.markdown("### LIVE CONSOLE OUTPUT")
            logs_html = '<div class="console-output">'
            for log in st.session_state.automation_state.logs[-50:]:
                logs_html += f'<div class="console-line">{log}</div>'
            logs_html += '</div>'
            st.markdown(logs_html, unsafe_allow_html=True)
            if st.button("🔄 REFRESH LOGS", use_container_width=True):
                st.rerun()

# ==================== MAIN ====================
if not st.session_state.logged_in:
    login_page()
else:
    main_app()

st.markdown('<div class="footer">MADE WITH ❤️ BY ASHIQ RAJ | © 2025</div>', unsafe_allow_html=True)
