import sqlite3
import hashlib
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

# ==================== RENDER PERSISTENCE ====================
IS_RENDER = bool(os.environ.get('RENDER'))
if IS_RENDER:
    DATA_DIR = Path('/opt/render/project/data')
else:
    DATA_DIR = Path(__file__).parent

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / 'users.db'
ENCRYPTION_KEY_FILE = DATA_DIR / '.encryption_key'

# ==================== ENCRYPTION SETUP ====================
def get_encryption_key():
    if ENCRYPTION_KEY_FILE.exists():
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, 'wb') as f:
        f.write(key)
    return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

# ==================== HELPER FUNCTIONS ====================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt_cookies(cookies: str) -> str | None:
    if not cookies:
        return None
    return cipher_suite.encrypt(cookies.encode()).decode()

def decrypt_cookies(encrypted_cookies: str) -> str:
    if not encrypted_cookies:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_cookies.encode()).decode()
    except Exception:
        return ""

# ==================== DATABASE INIT (with all columns) ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Complete user_configs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            chat_id TEXT,
            name_prefix TEXT,
            delay INTEGER DEFAULT 30,
            cookies_encrypted TEXT,
            messages TEXT,
            automation_running INTEGER DEFAULT 0,
            locked_group_name TEXT,
            locked_nicknames TEXT,
            lock_enabled INTEGER DEFAULT 0,
            admin_thread_id TEXT,
            admin_chat_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Add missing columns (safe for existing DBs)
    columns_to_add = [
        ('automation_running', 'INTEGER DEFAULT 0'),
        ('locked_group_name', 'TEXT'),
        ('locked_nicknames', 'TEXT'),
        ('lock_enabled', 'INTEGER DEFAULT 0'),
        ('admin_thread_id', 'TEXT'),
        ('admin_chat_type', 'TEXT'),
        ('name_prefix', 'TEXT'),
        ('delay', 'INTEGER DEFAULT 30'),
        ('messages', 'TEXT')
    ]
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE user_configs ADD COLUMN {col_name} {col_type}')
        except sqlite3.OperationalError:
            pass  # already exists

    conn.commit()
    conn.close()
    print(f"✓ Database ready at {DB_PATH}")

# ==================== USER MANAGEMENT ====================
def create_user(username: str, password: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        pwd_hash = hash_password(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pwd_hash))
        user_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, '', '', 30, ''))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def verify_user(username: str, password: str) -> int | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    if user and user[1] == hash_password(password):
        return user[0]
    return None

def get_username(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# ==================== CONFIGURATION (full) ====================
def get_user_config(user_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, name_prefix, delay, cookies_encrypted, messages, automation_running
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 30,
            'cookies': decrypt_cookies(row[3]),
            'messages': row[4] or '',
            'automation_running': bool(row[5])
        }
    return None

def update_user_config(user_id: int, chat_id: str, name_prefix: str, delay: int, cookies: str, messages: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    enc_cookies = encrypt_cookies(cookies)
    cursor.execute('''
        UPDATE user_configs
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies_encrypted = ?,
            messages = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, enc_cookies, messages, user_id))
    conn.commit()
    conn.close()

# ==================== AUTOMATION STATUS ====================
def set_automation_running(user_id: int, is_running: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_configs SET automation_running = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                   (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT automation_running FROM user_configs WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ==================== LOCK SYSTEM ====================
def get_lock_config(user_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, locked_group_name, locked_nicknames, lock_enabled, cookies_encrypted
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        nicknames = {}
        try:
            if row[2]:
                nicknames = json.loads(row[2])
        except:
            pass
        return {
            'chat_id': row[0] or '',
            'locked_group_name': row[1] or '',
            'locked_nicknames': nicknames,
            'lock_enabled': bool(row[3]),
            'cookies': decrypt_cookies(row[4])
        }
    return None

def update_lock_config(user_id: int, chat_id: str, locked_group_name: str, locked_nicknames: dict, cookies: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    nicknames_json = json.dumps(locked_nicknames)
    if cookies is not None:
        enc_cookies = encrypt_cookies(cookies)
        cursor.execute('''
            UPDATE user_configs
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?,
                cookies_encrypted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, enc_cookies, user_id))
    else:
        cursor.execute('''
            UPDATE user_configs
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, user_id))
    conn.commit()
    conn.close()

def set_lock_enabled(user_id: int, enabled: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_configs SET lock_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                   (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()

def get_lock_enabled(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT lock_enabled FROM user_configs WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ==================== ADMIN THREAD (E2EE) ====================
def get_admin_e2ee_thread_id(user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT admin_thread_id, admin_chat_type FROM user_configs WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'thread_id': row[0], 'chat_type': row[1]}
    return {'thread_id': None, 'chat_type': None}

def set_admin_e2ee_thread_id(user_id: int, thread_id: str, cookies: str, chat_type: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    enc_cookies = encrypt_cookies(cookies)
    cursor.execute('''
        UPDATE user_configs
        SET admin_thread_id = ?, admin_chat_type = ?, cookies_encrypted = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (thread_id, chat_type, enc_cookies, user_id))
    conn.commit()
    conn.close()

# ==================== DB HEALTH CHECK ====================
def check_database_status() -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        ok = cursor.fetchone() is not None
        conn.close()
        return ok
    except Exception:
        return False

# ==================== INITIALIZE ====================
init_db()
print("✓ db.py loaded – all features ready (automation, lock, admin thread, config)")
