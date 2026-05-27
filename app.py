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
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Selenium imports with proper error handling
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        WebDriverException, TimeoutException, 
        NoSuchElementException, InvalidCookieDomainException
    )
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError as e:
    SELENIUM_AVAILABLE = False
    st.error(f"Selenium import error: {e}. Please install required packages.")

# ==================== ENHANCED DATABASE ====================
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
                  admin_thread_id TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Sessions table for tracking
    c.execute('''CREATE TABLE IF NOT EXISTS automation_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  start_time TIMESTAMP,
                  end_time TIMESTAMP,
                  messages_sent INTEGER,
                  status TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Check if admin exists, if not create default admin
    c.execute("SELECT id FROM users WHERE username = ?", ("Ashiq Raj",))
    if not c.fetchone():
        hashed_admin = hashlib.sha256("Ashiq Raj".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                  ("Ashiq Raj", hashed_admin, 1))
        admin_id = c.lastrowid
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages) VALUES (?, ?, ?, ?, ?, ?)",
                  (admin_id, "", "Ashiq Raj", 10, "", "Hello!\nHow are you?\nNice to meet you!"))
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username: str, password: str) -> Tuple[bool, str]:
    """Create a new user account"""
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    try:
        # Validate username
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters"
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters"
        
        hashed = hash_password(password)
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                  (username, hashed, 0))
        user_id = c.lastrowid
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, cookies, messages) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, "", "", 10, "", "Hello!\nHow are you?\nNice to meet you!"))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def verify_user(username: str, password: str) -> Optional[int]:
    """Verify user credentials and return user ID"""
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    hashed = hash_password(password)
    c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, hashed))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_config(user_id: int) -> Optional[Dict]:
    """Get user configuration"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages, total_messages_sent, admin_thread_id FROM user_configs WHERE user_id = ?", (user_id,))
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
            'admin_thread_id': row[6] or ''
        }
    return None

def update_user_config(user_id: int, chat_id: str, name_prefix: str, delay: int, cookies: str, messages: str):
    """Update user configuration"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ? WHERE user_id = ?",
              (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def update_total_messages(user_id: int, additional: int):
    """Update total messages count"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET total_messages_sent = total_messages_sent + ? WHERE user_id = ?", (additional, user_id))
    conn.commit()
    conn.close()

def set_automation_running(user_id: int, is_running: bool):
    """Set automation running status"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET automation_running = ?, last_run = CURRENT_TIMESTAMP WHERE user_id = ?", 
              (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id: int) -> bool:
    """Check if automation is running"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT automation_running FROM user_configs WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def update_admin_thread(user_id: int, thread_id: str):
    """Update admin thread ID for notifications"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE user_configs SET admin_thread_id = ? WHERE user_id = ?", (thread_id, user_id))
    conn.commit()
    conn.close()

def log_automation_session(user_id: int, messages_sent: int, status: str):
    """Log automation session"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("INSERT INTO automation_sessions (user_id, start_time, end_time, messages_sent, status) VALUES (?, datetime('now'), datetime('now'), ?, ?)",
              (user_id, messages_sent, status))
    conn.commit()
    conn.close()

def get_username(user_id: int) -> str:
    """Get username by ID"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Unknown"

def is_admin_user(user_id: int) -> bool:
    """Check if user is admin"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] == 1 if row else False

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Ashiq Raj - Facebook Automation Suite",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== UNIQUE GLASS CARDS + ANIMATED CONSOLE CSS ====================
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Poppins', sans-serif;
}

/* Animated gradient background */
.stApp {
    background: linear-gradient(125deg, #0a0f1f 0%, #0f172a 25%, #1a1a2e 50%, #0f172a 75%, #0a0f1f 100%);
    background-size: 200% 200%;
    animation: gradientShift 15s ease infinite;
    min-height: 100vh;
}

@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* Floating particles effect */
.stApp::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    background-image: radial-gradient(circle at 10% 20%, rgba(77, 184, 255, 0.08) 0%, transparent 50%),
                      radial-gradient(circle at 90% 80%, rgba(0, 255, 136, 0.06) 0%, transparent 50%);
    z-index: 0;
}

/* Main container glass card */
.main .block-container {
    background: rgba(10, 20, 35, 0.4);
    backdrop-filter: blur(15px);
    border-radius: 48px;
    padding: 35px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(77, 184, 255, 0.2);
    border: 1px solid rgba(77, 184, 255, 0.3);
    margin-top: 20px;
    margin-bottom: 20px;
    animation: fadeInUp 0.6s ease-out;
    position: relative;
    z-index: 1;
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Main header with neon effect */
.main-header {
    background: linear-gradient(135deg, rgba(77, 184, 255, 0.2), rgba(30, 136, 229, 0.15), rgba(0, 200, 100, 0.1));
    backdrop-filter: blur(20px);
    padding: 3.5rem 2rem;
    border-radius: 60px;
    text-align: center;
    margin-bottom: 3rem;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.1);
    border: 1px solid rgba(77, 184, 255, 0.5);
    position: relative;
    overflow: hidden;
}

.main-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(77,184,255,0.1) 0%, transparent 70%);
    animation: rotate 20s linear infinite;
}

@keyframes rotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.main-header h1 {
    background: linear-gradient(135deg, #ffffff, #4db8ff, #00ff88, #1e88e5);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 4rem;
    font-weight: 900;
    margin: 0;
    text-shadow: 0 0 30px rgba(77,184,255,0.5);
    letter-spacing: 2px;
    position: relative;
    z-index: 1;
}

.main-header p {
    color: rgba(255,255,255,0.9);
    font-size: 1.5rem;
    font-weight: 600;
    text-shadow: 0 0 10px rgba(0,0,0,0.5);
    letter-spacing: 1px;
    position: relative;
    z-index: 1;
}

/* Unique Signup Button - Yellow Neon */
div[data-testid="stForm"] button[kind="primary"],
.stButton button:contains("CREATE ACCOUNT"),
button[key="signup_btn"] {
    background: linear-gradient(135deg, #ffd600, #ff8f00) !important;
    color: #1a1a1a !important;
    font-weight: 800 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    box-shadow: 0 0 15px rgba(255,214,0,0.6), 0 4px 20px rgba(0,0,0,0.3) !important;
    border: none !important;
    transition: all 0.3s ease !important;
}

.stButton button:contains("CREATE ACCOUNT"):hover {
    transform: translateY(-3px) scale(1.02) !important;
    box-shadow: 0 0 25px rgba(255,214,0,0.9), 0 8px 30px rgba(0,0,0,0.4) !important;
}

/* Login Button - Blue Neon */
.stButton button:contains("LOGIN") {
    background: linear-gradient(135deg, #4db8ff, #1e88e5) !important;
    color: white !important;
    font-weight: 800 !important;
    text-transform: uppercase !important;
    box-shadow: 0 0 15px rgba(77,184,255,0.5), 0 4px 20px rgba(0,0,0,0.3) !important;
}

/* Start Button - Green with pulse */
.stButton button:contains("START AUTOMATION") {
    background: linear-gradient(135deg, #00e676, #00c853) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    text-transform: uppercase !important;
    box-shadow: 0 0 20px rgba(0,230,118,0.5), 0 4px 20px rgba(0,0,0,0.3) !important;
    animation: pulseGreen 2s infinite !important;
}

@keyframes pulseGreen {
    0% { box-shadow: 0 0 5px rgba(0,230,118,0.5); }
    50% { box-shadow: 0 0 25px rgba(0,230,118,0.8); }
    100% { box-shadow: 0 0 5px rgba(0,230,118,0.5); }
}

/* Stop Button - Red */
.stButton button:contains("STOP AUTOMATION") {
    background: linear-gradient(135deg, #ff5252, #d32f2f) !important;
    color: white !important;
    font-weight: 800 !important;
    box-shadow: 0 0 15px rgba(255,82,82,0.5) !important;
}

/* Input fields with glass effect */
.stTextInput>div>div>input, 
.stTextArea>div>div>textarea,
.stNumberInput>div>div>input {
    background: rgba(15, 25, 45, 0.9) !important;
    border: 2px solid #4db8ff !important;
    border-radius: 20px !important;
    color: white !important;
    padding: 0.8rem 1.2rem !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
}

.stTextInput>div>div>input:focus, 
.stTextArea>div>div>textarea:focus {
    border-color: #00ff88 !important;
    box-shadow: 0 0 15px rgba(0,255,136,0.3) !important;
    outline: none !important;
}

/* Labels */
label {
    color: #4db8ff !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 5px !important;
}

/* Tabs styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 15px;
    background: rgba(0,0,0,0.4);
    border-radius: 30px;
    padding: 8px 15px;
    backdrop-filter: blur(10px);
}

.stTabs [data-baseweb="tab"] {
    background: rgba(0,0,0,0.5);
    border-radius: 25px;
    color: #ccc;
    padding: 12px 28px;
    font-weight: 700;
    transition: all 0.3s;
    border: 1px solid transparent;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #4db8ff, #1e88e5);
    color: white;
    box-shadow: 0 0 15px rgba(77,184,255,0.4);
    border-color: rgba(255,255,255,0.3);
}

/* Metric cards */
.metric-container {
    background: linear-gradient(135deg, rgba(15, 30, 55, 0.8), rgba(10, 20, 40, 0.9));
    backdrop-filter: blur(12px);
    border-radius: 28px;
    padding: 25px 20px;
    border: 1px solid rgba(77,184,255,0.5);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    text-align: center;
    transition: transform 0.3s ease;
}

.metric-container:hover {
    transform: translateY(-5px);
    border-color: #00ff88;
    box-shadow: 0 12px 40px rgba(0,255,136,0.2);
}

[data-testid="stMetricValue"] {
    color: #4db8ff !important;
    font-weight: 800 !important;
    font-size: 2.5rem !important;
    text-shadow: 0 0 10px rgba(77,184,255,0.5);
}

/* UNIQUE CONSOLE with terminal feel */
.console-output {
    background: #050811;
    border-radius: 28px;
    padding: 25px;
    font-family: 'Courier New', 'Fira Code', 'JetBrains Mono', monospace;
    max-height: 550px;
    overflow-y: auto;
    border: 2px solid #4db8ff;
    box-shadow: inset 0 0 30px rgba(0,0,0,0.8), 0 10px 30px rgba(0,0,0,0.4);
    position: relative;
}

.console-output::-webkit-scrollbar {
    width: 8px;
}

.console-output::-webkit-scrollbar-track {
    background: #0a0f1f;
    border-radius: 10px;
}

.console-output::-webkit-scrollbar-thumb {
    background: #4db8ff;
    border-radius: 10px;
}

.console-line {
    margin-bottom: 10px;
    padding: 8px 15px;
    border-left: 4px solid;
    border-radius: 12px;
    font-size: 13px;
    animation: slideIn 0.25s ease-out;
    font-weight: 500;
    font-family: monospace;
}

@keyframes slideIn {
    from {
        opacity: 0;
        transform: translateX(-15px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.console-line.info { 
    border-left-color: #4db8ff; 
    color: #bbddff; 
    background: rgba(77,184,255,0.08);
}
.console-line.success { 
    border-left-color: #00ff88; 
    color: #ccffdd; 
    background: rgba(0,255,136,0.08);
}
.console-line.error { 
    border-left-color: #ff4466; 
    color: #ffccdd; 
    background: rgba(255,68,102,0.08);
}
.console-line.warning { 
    border-left-color: #ffcc00; 
    color: #ffeecc; 
    background: rgba(255,204,0,0.08);
}

/* Sidebar styling */
.css-1d391kg, [data-testid="stSidebar"] {
    background: rgba(5, 10, 25, 0.7) !important;
    backdrop-filter: blur(20px) !important;
    border-right: 1px solid rgba(77,184,255,0.3) !important;
}

.sidebar-header {
    background: linear-gradient(135deg, #4db8ff, #1e88e5);
    border-radius: 30px;
    padding: 1.8rem;
    text-align: center;
    color: white;
    font-weight: 800;
    font-size: 1.3rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.2);
}

/* Success and Error boxes */
.success-box {
    background: linear-gradient(135deg, rgba(0,200,100,0.2), rgba(0,150,80,0.1));
    border: 1px solid #00ff88;
    border-radius: 25px;
    padding: 1rem;
    text-align: center;
    color: #00ff88;
    font-weight: 600;
    backdrop-filter: blur(5px);
}

.error-box {
    background: linear-gradient(135deg, rgba(255,68,102,0.2), rgba(200,50,80,0.1));
    border: 1px solid #ff4466;
    border-radius: 25px;
    padding: 1rem;
    text-align: center;
    color: #ff88aa;
    backdrop-filter: blur(5px);
}

/* Section title */
.section-title {
    color: #4db8ff;
    font-weight: 800;
    font-size: 2rem;
    margin-bottom: 1.8rem;
    border-bottom: 3px solid #4db8ff;
    display: inline-block;
    padding-bottom: 0.5rem;
    text-shadow: 0 0 5px rgba(77,184,255,0.3);
}

/* Footer */
.footer {
    text-align: center;
    padding: 2rem;
    color: #4db8ff;
    background: rgba(0,0,0,0.4);
    border-radius: 30px;
    margin-top: 3rem;
    font-weight: 600;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(77,184,255,0.2);
}

/* Green border for all page elements */
.main-header, .metric-container, .console-output, .stTabs [data-baseweb="tab-list"],
div[data-testid="stForm"], .sidebar-header, .footer {
    border-color: #00ff88 !important;
    border-width: 1px !important;
}

/* Animations */
@keyframes glowPulse {
    0% { border-color: #4db8ff; }
    50% { border-color: #00ff88; }
    100% { border-color: #4db8ff; }
}

.main .block-container {
    animation: glowPulse 4s infinite;
}
"""

st.markdown(custom_css, unsafe_allow_html=True)

# Admin UID for notifications
ADMIN_UID = "100003995292301"

# Session state initialization
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
if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False

class AutomationState:
    """Manages automation state and logs"""
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []  # each element: (message, level)
        self.message_rotation_index = 0
        self.stop_requested = False

if 'automation_state' not in st.session_state:
    st.session_state.automation_state = AutomationState()

def log_message(msg: str, level: str = "info", automation_state: AutomationState = None):
    """Add a message to logs with timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    if automation_state:
        automation_state.logs.append((formatted_msg, level))
    else:
        st.session_state.logs.append((formatted_msg, level))

# ==================== ENHANCED BROWSER SETUP (FIXED FOR RENDER) ====================
def setup_browser(automation_state: AutomationState = None) -> webdriver.Chrome:
    """Setup Chrome browser with proper configuration for Render"""
    log_message('Setting up Chrome browser for Render...', "info", automation_state)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Try multiple binary locations
    possible_paths = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser", 
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/opt/google/chrome/chrome"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            log_message(f'Found Chrome/Chromium at: {path}', "success", automation_state)
            break
    else:
        log_message("Chromium/Chrome not found in common locations", "warning", automation_state)
    
    try:
        # Use ChromeDriverManager with proper cache dir
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        log_message('Chrome browser ready!', "success", automation_state)
        return driver
    except Exception as e:
        log_message(f'Browser setup failed: {str(e)}', "error", automation_state)
        raise

def find_message_input(driver: webdriver.Chrome, process_id: str, automation_state: AutomationState = None, timeout: int = 30):
    """Find Facebook message input element using multiple selectors"""
    log_message(f'{process_id}: Looking for message input...', "info", automation_state)
    wait = WebDriverWait(driver, timeout)
    
    # Comprehensive list of selectors for Facebook message input
    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        'div[aria-label*="Type" i][contenteditable="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'textarea[placeholder*="Type" i]',
        'div[data-placeholder*="message" i]',
        'div[data-placeholder*="Type" i]',
        '[contenteditable="true"]'
    ]
    
    for idx, selector in enumerate(selectors):
        try:
            element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            if element and element.is_displayed():
                log_message(f'{process_id}: Found input using selector {idx+1}', "success", automation_state)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
                time.sleep(0.5)
                return element
        except:
            continue
    
    log_message(f'{process_id}: Message input NOT found after {timeout}s', "error", automation_state)
    return None

def get_next_message(messages: List[str], automation_state: AutomationState = None) -> str:
    """Get next message in rotation"""
    if not messages:
        return 'Hello!'
    if automation_state:
        msg = messages[automation_state.message_rotation_index % len(messages)]
        automation_state.message_rotation_index += 1
        return msg
    return messages[0]

def send_notification_to_admin(user_config: Dict, username: str, automation_state: AutomationState, user_id: int):
    """Send notification to admin about automation start"""
    driver = None
    try:
        log_message("ADMIN-NOTIFY: Preparing admin notification...", "info", automation_state)
        
        driver = setup_browser(automation_state)
        driver.get('https://www.facebook.com/')
        time.sleep(10)
        
        # Add cookies if available
        cookies_str = user_config.get('cookies', '')
        if cookies_str and isinstance(cookies_str, str) and cookies_str.strip():
            log_message("ADMIN-NOTIFY: Adding cookies...", "info", automation_state)
            cookie_pairs = cookies_str.split(';')
            for pair in cookie_pairs:
                pair = pair.strip()
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': value, 'domain': '.facebook.com'})
                    except InvalidCookieDomainException:
                        pass
                    except Exception:
                        pass
        
        # Navigate to admin chat
        admin_thread_id = user_config.get('admin_thread_id', '')
        if admin_thread_id:
            driver.get(f'https://www.facebook.com/messages/t/{admin_thread_id}')
        else:
            driver.get(f'https://www.facebook.com/messages/t/{ADMIN_UID}')
        
        time.sleep(12)
        
        # Find message input and send notification
        msg_input = find_message_input(driver, 'ADMIN', automation_state, timeout=20)
        if msg_input:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notification = f"""🤖 ASHIQ RAJ AUTOMATION STARTED

👤 User: {username}
🆔 ID: {user_id}
⏰ Time: {current_time}
📱 Status: Automation running

🔵 Powered by Ashiq Raj"""
            
            # Send message
            driver.execute_script("""
                const el = arguments[0];
                const txt = arguments[1];
                el.focus();
                el.click();
                el.textContent = txt;
                el.innerHTML = txt;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            """, msg_input, notification)
            time.sleep(1.5)
            
            # Press send button or Enter
            try:
                send_btn = driver.find_element(By.CSS_SELECTOR, 'div[aria-label="Press Enter to send"]')
                driver.execute_script("arguments[0].click();", send_btn)
            except:
                msg_input.send_keys(Keys.RETURN)
            
            log_message("ADMIN-NOTIFY: Admin notification sent successfully", "success", automation_state)
            
            # Capture thread ID if not saved
            if not admin_thread_id:
                current_url = driver.current_url
                match = re.search(r'/messages/t/([^/?]+)', current_url)
                if match:
                    thread_id = match.group(1)
                    update_admin_thread(user_id, thread_id)
                    log_message(f"ADMIN-NOTIFY: Saved admin thread ID: {thread_id}", "success", automation_state)
        else:
            log_message("ADMIN-NOTIFY: Could not find message input for admin", "warning", automation_state)
            
    except Exception as e:
        log_message(f"ADMIN-NOTIFY: Error sending notification: {str(e)[:100]}", "error", automation_state)
    finally:
        if driver:
            driver.quit()

def run_automation_loop(config: Dict, automation_state: AutomationState, user_id: int, process_id: str = 'AUTO-1'):
    """Main automation loop - sends messages continuously"""
    driver = None
    total_sent = 0
    
    try:
        log_message(f'{process_id}: Starting automation engine...', "success", automation_state)
        
        # Send notification to admin
        username = get_username(user_id) if user_id != "admin_ashiq" else "Ashiq Raj"
        send_notification_to_admin(config, username, automation_state, user_id)
        
        # Setup browser
        driver = setup_browser(automation_state)
        driver.get('https://www.facebook.com/')
        time.sleep(10)
        
        # Handle cookies
        cookies_str = config.get('cookies', '')
        if cookies_str and isinstance(cookies_str, str) and cookies_str.strip():
            log_message(f'{process_id}: Loading cookies...', "info", automation_state)
            cookie_pairs = cookies_str.split(';')
            for pair in cookie_pairs:
                pair = pair.strip()
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': value, 'domain': '.facebook.com'})
                    except:
                        pass
        
        # Navigate to chat
        chat_id = config.get('chat_id', '').strip()
        if chat_id:
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
            log_message(f'{process_id}: Navigating to chat: {chat_id}', "info", automation_state)
        else:
            driver.get('https://www.facebook.com/messages')
            log_message(f'{process_id}: No chat ID, using messages page', "warning", automation_state)
        
        time.sleep(15)
        
        # Find message input
        msg_input = find_message_input(driver, process_id, automation_state, timeout=35)
        if not msg_input:
            log_message(f'{process_id}: Cannot find message input! Automation stopping.', "error", automation_state)
            automation_state.running = False
            set_automation_running(user_id, False)
            return 0
        
        # Prepare message list
        messages_text = config.get('messages', '')
        messages_list = [m.strip() for m in messages_text.split('\n') if m.strip()]
        if not messages_list:
            messages_list = ['Hello!', 'How are you?', 'Nice to meet you!']
        
        log_message(f'{process_id}: Loaded {len(messages_list)} messages', "success", automation_state)
        
        # Main sending loop
        while automation_state.running and not automation_state.stop_requested:
            try:
                # Get next message
                base_msg = get_next_message(messages_list, automation_state)
                name_prefix = config.get('name_prefix', '')
                full_msg = f"{name_prefix} {base_msg}".strip() if name_prefix else base_msg
                
                # Send message via JavaScript
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
                time.sleep(1.2)
                
                # Send message (Enter key or button)
                try:
                    send_buttons = driver.find_elements(By.CSS_SELECTOR, 
                        'div[aria-label*="Send" i]:not([aria-label*="like"]), [data-testid="send-button"]')
                    sent = False
                    for btn in send_buttons:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                            sent = True
                            log_message(f'{process_id}: ✅ Sent via button: "{full_msg[:50]}"', "success", automation_state)
                            break
                    if not sent:
                        msg_input.send_keys(Keys.RETURN)
                        log_message(f'{process_id}: ✅ Sent via Enter: "{full_msg[:50]}"', "success", automation_state)
                except:
                    msg_input.send_keys(Keys.RETURN)
                    log_message(f'{process_id}: ✅ Sent: "{full_msg[:50]}"', "success", automation_state)
                
                total_sent += 1
                automation_state.message_count = total_sent
                
                # Random delay between 15-35 seconds
                wait_time = random.uniform(15, 35)
                log_message(f'{process_id}: Message #{total_sent} sent. Next in {wait_time:.1f}s', "info", automation_state)
                
                # Wait but check for stop request every second
                for _ in range(int(wait_time)):
                    if not automation_state.running or automation_state.stop_requested:
                        break
                    time.sleep(1)
                
            except Exception as e:
                log_message(f'{process_id}: Send error: {str(e)[:100]}', "error", automation_state)
                time.sleep(5)
                # Try to re-find message input if lost
                try:
                    msg_input = find_message_input(driver, process_id, automation_state, timeout=15)
                except:
                    pass
        
        log_message(f'{process_id}: Automation stopped. Total messages sent: {total_sent}', "success", automation_state)
        
        # Update total messages in database
        if user_id != "admin_ashiq":
            update_total_messages(user_id, total_sent)
            log_automation_session(user_id, total_sent, "completed")
        
        return total_sent
        
    except Exception as e:
        log_message(f'{process_id}: Fatal error: {str(e)}', "error", automation_state)
        automation_state.running = False
        if user_id != "admin_ashiq":
            log_automation_session(user_id, total_sent, f"failed: {str(e)[:50]}")
        return total_sent
    finally:
        if driver:
            driver.quit()
        set_automation_running(user_id, False)

def start_automation_thread(config: Dict, user_id: int):
    """Start automation in a background thread"""
    if st.session_state.automation_state.running:
        return
    
    # Reset automation state
    st.session_state.automation_state.running = True
    st.session_state.automation_state.message_count = 0
    st.session_state.automation_state.logs = []
    st.session_state.automation_state.stop_requested = False
    
    if user_id != "admin_ashiq":
        set_automation_running(user_id, True)
    
    # Start thread
    thread = threading.Thread(
        target=run_automation_loop,
        args=(config, st.session_state.automation_state, user_id, 'AUTO-1')
    )
    thread.daemon = True
    thread.start()

def stop_automation_thread(user_id: int):
    """Stop the automation thread"""
    if st.session_state.automation_state.running:
        st.session_state.automation_state.running = False
        st.session_state.automation_state.stop_requested = True
        if user_id != "admin_ashiq":
            set_automation_running(user_id, False)
        log_message("Automation stop requested...", "warning", st.session_state.automation_state)

# ==================== UI PAGES ====================
def login_page():
    """Login and signup page"""
    st.markdown("""
    <div class="main-header">
        <h1>🤖 ASHIQ RAJ</h1>
        <p>PREMIUM FACEBOOK MESSAGE AUTOMATION SUITE</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔐 LOGIN", "✨ SIGN UP"])
        
        with tab1:
            st.markdown("### Welcome Back!")
            username = st.text_input("USERNAME", key="login_user", placeholder="Enter your username")
            password = st.text_input("PASSWORD", type="password", key="login_pass", placeholder="Enter your password")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔐 LOGIN", key="login_btn", use_container_width=True):
                    if username and password:
                        # Check for admin
                        if username == "Ashiq Raj" and password == "Ashiq Raj":
                            st.session_state.logged_in = True
                            st.session_state.user_id = "admin_ashiq"
                            st.session_state.username = "Ashiq Raj"
                            st.success("✅ ADMIN ACCESS GRANTED!")
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
                                st.success(f"✅ WELCOME {username.upper()}!")
                                st.rerun()
                            else:
                                st.error("❌ Invalid credentials")
                    else:
                        st.warning("Please enter username and password")
        
        with tab2:
            st.markdown("### Create New Account")
            new_user = st.text_input("USERNAME", key="signup_user", placeholder="Choose a username (min 3 chars)")
            new_pass = st.text_input("PASSWORD", type="password", key="signup_pass", placeholder="Choose a password (min 4 chars)")
            confirm = st.text_input("CONFIRM PASSWORD", type="password", key="confirm_pass", placeholder="Confirm your password")
            
            if st.button("✨ CREATE ACCOUNT", key="signup_btn", use_container_width=True):
                if new_user and new_pass and confirm:
                    if len(new_user) < 3:
                        st.error("Username must be at least 3 characters")
                    elif len(new_pass) < 4:
                        st.error("Password must be at least 4 characters")
                    elif new_pass != confirm:
                        st.error("Passwords do not match")
                    else:
                        ok, msg = create_user(new_user, new_pass)
                        if ok:
                            st.success(f"✅ {msg} Please login!")
                        else:
                            st.error(f"❌ {msg}")
                else:
                    st.warning("Please fill all fields")

def main_app():
    """Main application dashboard"""
    st.markdown("""
    <div class="main-header">
        <h1>🤖 ASHIQ RAJ</h1>
        <p>AUTOMATION CONTROL DASHBOARD</p>
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
    st.sidebar.markdown('<div class="sidebar-header">👤 USER DASHBOARD</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f"**USER:** `{st.session_state.username}`")
    st.sidebar.markdown(f"**ID:** `{st.session_state.user_id}`")
    st.sidebar.markdown('<div class="success-box">✅ PREMIUM ACCESS</div>', unsafe_allow_html=True)
    
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        if st.session_state.automation_state.running:
            stop_automation_thread(st.session_state.user_id if st.session_state.user_id != "admin_ashiq" else None)
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.auto_start_checked = False
        st.rerun()
    
    # Get config
    if st.session_state.user_id == "admin_ashiq":
        # Admin gets a default config
        if 'admin_config' not in st.session_state:
            st.session_state.admin_config = {
                'chat_id': '',
                'name_prefix': 'Ashiq Raj',
                'delay': 10,
                'cookies': '',
                'messages': 'Hello!\nHow are you?\nNice to meet you!\nHave a great day!',
                'total_sent': 0
            }
        cfg = st.session_state.admin_config
    else:
        cfg = get_user_config(st.session_state.user_id)
    
    if cfg:
        tab1, tab2 = st.tabs(["⚙️ CONFIGURATION", "🚀 AUTOMATION ENGINE"])
        
        with tab1:
            st.markdown('<div class="section-title">⚙️ CONFIGURATION</div>', unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            with col1:
                chat_id = st.text_input(
                    "📱 CHAT / USER ID", 
                    value=cfg['chat_id'], 
                    placeholder="e.g., 1000123456789 or facebook_username",
                    help="Facebook user ID or chat thread ID"
                )
                name_prefix = st.text_input(
                    "🏷️ NAME PREFIX", 
                    value=cfg['name_prefix'], 
                    placeholder="e.g., [Ashiq Raj]",
                    help="Optional prefix before each message"
                )
            
            with col2:
                delay = st.number_input(
                    "⏱️ BASE DELAY (SEC)", 
                    min_value=5, 
                    max_value=300, 
                    value=cfg.get('delay', 10),
                    help="Actual delay is random between this value and this value + 15s"
                )
                total_sent = cfg.get('total_sent', 0)
                st.metric("📊 TOTAL MESSAGES SENT", f"{total_sent:,}")
            
            cookies = st.text_area(
                "🍪 COOKIES (optional)", 
                value=cfg.get('cookies', ''), 
                height=100,
                placeholder="name1=value1; name2=value2; ...",
                help="Facebook cookies for authentication"
            )
            
            messages = st.text_area(
                "💬 MESSAGES (one per line)", 
                value=cfg['messages'], 
                height=200,
                help="Each line will be sent in rotation"
            )
            
            if st.button("💾 SAVE CONFIGURATION", use_container_width=True):
                if st.session_state.user_id == "admin_ashiq":
                    st.session_state.admin_config.update({
                        'chat_id': chat_id, 'name_prefix': name_prefix, 
                        'delay': delay, 'cookies': cookies, 'messages': messages
                    })
                else:
                    update_user_config(st.session_state.user_id, chat_id, name_prefix, delay, cookies, messages)
                st.success("✅ Configuration saved successfully!")
                st.rerun()
        
        with tab2:
            st.markdown('<div class="section-title">🚀 AUTOMATION ENGINE</div>', unsafe_allow_html=True)
            
            # Metrics row
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                st.metric("📨 SESSION MESSAGES", st.session_state.automation_state.message_count)
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                status = "🟢 RUNNING" if st.session_state.automation_state.running else "🔴 STOPPED"
                st.metric("📡 STATUS", status)
                st.markdown('</div>', unsafe_allow_html=True)
            with col3:
                st.markdown('<div class="metric-container">', unsafe_allow_html=True)
                display_chat = cfg['chat_id'][:15] + "..." if len(cfg['chat_id']) > 15 else cfg['chat_id'] or "NOT SET"
                st.metric("🎯 TARGET CHAT", display_chat if display_chat else "Not set")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Control buttons
            col_a, col_b = st.columns(2)
            with col_a:
                start_disabled = st.session_state.automation_state.running or not cfg.get('chat_id')
                if st.button("▶️ START AUTOMATION", disabled=start_disabled, use_container_width=True):
                    if cfg['chat_id']:
                        start_automation_thread(cfg, st.session_state.user_id)
                        st.success("✅ Automation started! Messages will be sent with 15-35s intervals.")
                        st.rerun()
                    else:
                        st.error("❌ Please set a Chat ID first in Configuration tab")
            with col_b:
                if st.button("⏹️ STOP AUTOMATION", disabled=not st.session_state.automation_state.running, use_container_width=True):
                    stop_automation_thread(st.session_state.user_id)
                    st.warning("⚠️ Automation stop requested...")
                    st.rerun()
            
            # Live Console
            if st.session_state.automation_state.logs:
                st.markdown("### 📺 LIVE CONSOLE OUTPUT")
                logs_html = '<div class="console-output">'
                for log_msg, level in st.session_state.automation_state.logs[-50:]:
                    logs_html += f'<div class="console-line {level}">{log_msg}</div>'
                logs_html += '</div>'
                st.markdown(logs_html, unsafe_allow_html=True)
                
                if st.button("🔄 REFRESH LOGS", use_container_width=True):
                    st.rerun()
            else:
                st.info("💡 Click START AUTOMATION to begin. Console output will appear here.")
    else:
        st.error("⚠️ Configuration error. Please refresh the page.")

# ==================== MAIN ENTRY POINT ====================
if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Check Selenium availability
    if not SELENIUM_AVAILABLE:
        st.error("🚨 Selenium is not available. Please install selenium and webdriver-manager.")
        st.code("pip install selenium webdriver-manager")
        st.stop()
    
    # Render appropriate page
    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()
    
    # Footer
    st.markdown('<div class="footer">🤖 MADE WITH ❤️ BY ASHIQ RAJ | © 2025 | PREMIUM AUTOMATION SUITE</div>', unsafe_allow_html=True)
