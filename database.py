import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'users.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  created_at TIMESTAMP)''')
    
    # User configs table
    c.execute('''CREATE TABLE IF NOT EXISTS user_configs
                 (user_id INTEGER PRIMARY KEY,
                  chat_id TEXT,
                  name_prefix TEXT,
                  delay INTEGER DEFAULT 5,
                  cookies TEXT,
                  messages TEXT,
                  automation_running INTEGER DEFAULT 0,
                  admin_e2ee_thread_id TEXT,
                  admin_thread_type TEXT,
                  updated_at TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
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
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                 (username, hashed, datetime.now()))
        user_id = c.lastrowid
        
        # Create default config
        c.execute("INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages, automation_running, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (user_id, "", "", 5, "Hello!\nHow are you?\nNice to meet you!", 0, datetime.now()))
        
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    finally:
        conn.close()

def verify_user(username, password):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    hashed = hash_password(password)
    c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, hashed))
    result = c.fetchone()
    
    conn.close()
    return result[0] if result else None

def get_username(user_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()
    
    conn.close()
    return result[0] if result else None

def get_user_config(user_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_configs WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    conn.close()
    
    if result:
        return {
            'chat_id': result[0] or '',
            'name_prefix': result[1] or '',
            'delay': result[2] or 5,
            'cookies': result[3] or '',
            'messages': result[4] or "Hello!\nHow are you?\nNice to meet you!"
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""UPDATE user_configs 
                 SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?, updated_at = ?
                 WHERE user_id = ?""",
              (chat_id, name_prefix, delay, cookies, messages, datetime.now(), user_id))
    
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT automation_running FROM user_configs WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    conn.close()
    return result[0] == 1 if result else False

def set_automation_running(user_id, running):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("UPDATE user_configs SET automation_running = ? WHERE user_id = ?", (1 if running else 0, user_id))
    
    conn.commit()
    conn.close()

def get_admin_e2ee_thread_id(user_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT admin_e2ee_thread_id FROM user_configs WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    conn.close()
    return result[0] if result and result[0] else None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies=None, thread_type='REGULAR'):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if cookies:
        c.execute("UPDATE user_configs SET admin_e2ee_thread_id = ?, admin_thread_type = ?, cookies = ?, updated_at = ? WHERE user_id = ?",
                 (thread_id, thread_type, cookies, datetime.now(), user_id))
    else:
        c.execute("UPDATE user_configs SET admin_e2ee_thread_id = ?, admin_thread_type = ?, updated_at = ? WHERE user_id = ?",
                 (thread_id, thread_type, datetime.now(), user_id))
    
    conn.commit()
    conn.close()

# Initialize database
init_db()
