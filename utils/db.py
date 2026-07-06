"""
MongoDB helper with local SQLite fallback — ESGRC Intelligence Platform
Handles: user auth, report CRUD, chat history persistence.
"""

import hashlib
import hmac
import os
import secrets
import sqlite3
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import streamlit as st
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from bson.errors import InvalidId

# ─────────────────────────────────────────────────────────────────────────────
# SQLITE BACKUP SETUP
# ─────────────────────────────────────────────────────────────────────────────

DB_FILE = "esgrc_local.db"

def init_sqlite_db():
    """Ensure that the local SQLite database and tables exist."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                csv_filename TEXT,
                json_filename TEXT,
                report_content TEXT,
                module_name TEXT,
                overall_score REAL,
                context_data TEXT,
                chat_history TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error initializing SQLite DB: {e}")

# Call immediately on import to ensure DB is initialized
init_sqlite_db()


# ─────────────────────────────────────────────────────────────────────────────
# MONGODB CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _get_mongo_client():
    """Return a cached MongoClient with SSL fault tolerance."""
    uri = st.secrets.get("MONGODB_URI")
    if not uri:
        return None
    try:
        # First try with standard TLS and certifi
        try:
            import certifi
            tls_ca = certifi.where()
        except ImportError:
            tls_ca = None

        client_kwargs = {
            "serverSelectionTimeoutMS": 2000,
            "connectTimeoutMS": 2000,
            "socketTimeoutMS": 5000,
            "tls": True,
            "tlsAllowInvalidCertificates": True,
        }
        if tls_ca:
            client_kwargs["tlsCAFile"] = tls_ca

        client = MongoClient(uri, **client_kwargs)
        return client
    except Exception:
        try:
            client = MongoClient(
                uri,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000,
                socketTimeoutMS=5000,
            )
            return client
        except Exception:
            return None


@st.cache_resource(show_spinner=False)
def is_mongo_reachable() -> bool:
    """Check if the MongoDB cluster is reachable."""
    client = _get_mongo_client()
    if client is None:
        return False
    try:
        # Quick ping test
        client.admin.command('ping')
        return True
    except Exception:
        return False


def should_use_sqlite() -> bool:
    """Determine whether to use SQLite instead of MongoDB."""
    # Forced to False by user request to ONLY use MongoDB Atlas
    return False


def mark_sqlite_mode():
    """Explicitly switch to SQLite mode in session state."""
    pass


def get_db():
    """Return a MongoDB database handle, creating indexes if possible."""
    client = _get_mongo_client()
    if client is None:
        raise ConnectionError("MongoDB client could not be initialized.")
        
    db_name = st.secrets.get("MONGODB_DB", "esgrc_db")
    db = client[db_name]

    # Best-effort index creation (silently skipped if cluster has no primary)
    try:
        db.users.create_index("username", unique=True)
        db.users.create_index("email", unique=True)
        db.reports.create_index([("user_id", 1), ("created_at", DESCENDING)])
    except Exception:
        pass

    return db


def is_valid_object_id(id_str: str) -> bool:
    """Check if the ID is a valid MongoDB ObjectId hex string."""
    try:
        ObjectId(id_str)
        return True
    except InvalidId:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD HASHING
# ─────────────────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = st.secrets.get("APP_SECRET_KEY", "default-salt-change-me")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _verify_password(password: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password), stored_hash)


# ─────────────────────────────────────────────────────────────────────────────
# SQLITE BACKEND IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────────────────────────

def sqlite_register_user(username: str, email: str, password_hash: str, role: str = "ESGRC") -> Dict[str, Any]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Check username
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return {"ok": False, "error": "Username already taken (Local Mode)."}
    # Check email
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    if c.fetchone():
        conn.close()
        return {"ok": False, "error": "Email already registered (Local Mode)."}
    
    user_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    try:
        # Check if role column exists, add if not
        try:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'ESGRC'")
        except Exception:
            pass # Column already exists
            
        c.execute(
            "INSERT INTO users (id, username, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, email, password_hash, created_at, role)
        )
        conn.commit()
        user_doc = {
            "_id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "created_at": created_at,
            "role": role
        }
        conn.close()
        return {"ok": True, "user": user_doc}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": f"Local database error: {str(e)}"}


def sqlite_login_user(username: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        doc = {
            "_id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }
        # Safely get role for backward compatibility
        try:
            doc["role"] = row["role"] if row["role"] else "ESGRC"
        except IndexError:
            doc["role"] = "ESGRC"
        return doc
    return None


def sqlite_save_report(
    user_id: str,
    csv_filename: str,
    json_filename: str,
    report_content: str,
    context: dict,
) -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    report_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    c.execute(
        """INSERT INTO reports 
           (id, user_id, csv_filename, json_filename, report_content, module_name, overall_score, context_data, chat_history, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report_id,
            user_id,
            csv_filename,
            json_filename,
            report_content,
            context.get("module_name", ""),
            context.get("overall_score", 0.0),
            json.dumps(context),
            json.dumps([]),
            now,
            now
        )
    )
    conn.commit()
    conn.close()
    return report_id


def sqlite_get_user_reports(user_id: str, limit: int = 20) -> List[Dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, csv_filename, json_filename, module_name, overall_score, created_at FROM reports WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    reports = []
    for row in rows:
        reports.append({
            "_id": row["id"],
            "user_id": row["user_id"],
            "csv_filename": row["csv_filename"],
            "json_filename": row["json_filename"],
            "module_name": row["module_name"],
            "overall_score": row["overall_score"],
            "created_at": datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow()
        })
    return reports


def sqlite_get_report(report_id: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "_id": row["id"],
            "user_id": row["user_id"],
            "csv_filename": row["csv_filename"],
            "json_filename": row["json_filename"],
            "report_content": row["report_content"],
            "module_name": row["module_name"],
            "overall_score": row["overall_score"],
            "context_data": json.loads(row["context_data"]) if row["context_data"] else {},
            "chat_history": json.loads(row["chat_history"]) if row["chat_history"] else [],
            "created_at": datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            "updated_at": datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow()
        }
    return None


def sqlite_delete_report(report_id: str, user_id: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM reports WHERE id = ? AND user_id = ?", (report_id, user_id))
    count = c.rowcount
    conn.commit()
    conn.close()
    return count > 0


def sqlite_append_chat_message(report_id: str, role: str, content: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT chat_history FROM reports WHERE id = ?", (report_id,))
    row = c.fetchone()
    if row:
        chat_history = json.loads(row["chat_history"]) if row["chat_history"] else []
        chat_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        c.execute(
            "UPDATE reports SET chat_history = ?, updated_at = ? WHERE id = ?",
            (json.dumps(chat_history), datetime.utcnow().isoformat(), report_id)
        )
        conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC DATABASE INTERFACE (WITH AUTO-FALLBACK)
# ─────────────────────────────────────────────────────────────────────────────

def register_user(username: str, email: str, password: str, role: str = "ESGRC") -> Dict[str, Any]:
    """Create a new user. Returns {'ok': True, 'user': {...}} or {'ok': False, 'error': str}."""
    hashed = _hash_password(password)
    if should_use_sqlite():
        return sqlite_register_user(username, email, hashed, role)
        
    try:
        db = get_db()
        if db.users.find_one({"username": username}):
            return {"ok": False, "error": "Username already taken."}
        if db.users.find_one({"email": email}):
            return {"ok": False, "error": "Email already registered."}

        doc = {
            "username": username,
            "email": email,
            "password_hash": hashed,
            "created_at": datetime.utcnow(),
            "role": role
        }
        result = db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        return {"ok": True, "user": doc}
    except Exception as e:
        mark_sqlite_mode()
        return sqlite_register_user(username, email, hashed, role)


def login_user(username: str, password: str) -> Dict[str, Any]:
    """Verify credentials. Returns {'ok': True, 'user': {...}} or {'ok': False, 'error': str}."""
    if should_use_sqlite():
        user = sqlite_login_user(username)
        if not user:
            return {"ok": False, "error": "User not found (Local Mode)."}
        if not _verify_password(password, user["password_hash"]):
            return {"ok": False, "error": "Incorrect password (Local Mode)."}
        return {"ok": True, "user": user}
        
    try:
        db = get_db()
        user = db.users.find_one({"username": username})
        if not user:
            return {"ok": False, "error": "User not found."}
        if not _verify_password(password, user["password_hash"]):
            return {"ok": False, "error": "Incorrect password."}
        user["role"] = user.get("role", "ESGRC")
        return {"ok": True, "user": user}
    except Exception as e:
        mark_sqlite_mode()
        user = sqlite_login_user(username)
        if not user:
            return {"ok": False, "error": f"User not found (Offline Mode). MongoDB error: {e}"}
        if not _verify_password(password, user["password_hash"]):
            return {"ok": False, "error": "Incorrect password (Offline Mode)."}
        return {"ok": True, "user": user}


def save_report(
    user_id: str,
    csv_filename: str,
    json_filename: str,
    report_content: str,
    context: dict,
) -> str:
    """Persist a generated report. Returns the new report's string ID."""
    if should_use_sqlite():
        return sqlite_save_report(user_id, csv_filename, json_filename, report_content, context)
        
    try:
        db = get_db()
        doc = {
            "user_id": user_id,
            "csv_filename": csv_filename,
            "json_filename": json_filename,
            "report_content": report_content,
            "module_name": context.get("module_name", ""),
            "overall_score": context.get("overall_score", 0.0),
            "context_data": context,
            "chat_history": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = db.reports.insert_one(doc)
        return str(result.inserted_id)
    except Exception:
        mark_sqlite_mode()
        return sqlite_save_report(user_id, csv_filename, json_filename, report_content, context)


def get_user_reports(user_id: str, limit: int = 20) -> List[Dict]:
    """Return the most recent reports for a user. Returns [] on any DB error."""
    if should_use_sqlite():
        return sqlite_get_user_reports(user_id, limit)
        
    try:
        db = get_db()
        cursor = db.reports.find(
            {"user_id": user_id},
            {"report_content": 0, "context_data": 0},
        ).sort("created_at", DESCENDING).limit(limit)
        return list(cursor)
    except Exception:
        mark_sqlite_mode()
        return sqlite_get_user_reports(user_id, limit)


def get_report(report_id: str) -> Optional[Dict]:
    """Fetch a full report document by ID."""
    if should_use_sqlite() or not is_valid_object_id(report_id):
        return sqlite_get_report(report_id)
        
    try:
        db = get_db()
        return db.reports.find_one({"_id": ObjectId(report_id)})
    except Exception:
        mark_sqlite_mode()
        return sqlite_get_report(report_id)


def delete_report(report_id: str, user_id: str) -> bool:
    """Delete a report (only if it belongs to the requesting user)."""
    if should_use_sqlite() or not is_valid_object_id(report_id):
        return sqlite_delete_report(report_id, user_id)
        
    try:
        db = get_db()
        result = db.reports.delete_one(
            {"_id": ObjectId(report_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        mark_sqlite_mode()
        return sqlite_delete_report(report_id, user_id)


def append_chat_message(report_id: str, role: str, content: str) -> None:
    """Push a single chat message to a report's chat_history array."""
    if should_use_sqlite() or not is_valid_object_id(report_id):
        sqlite_append_chat_message(report_id, role, content)
        return
        
    try:
        db = get_db()
        db.reports.update_one(
            {"_id": ObjectId(report_id)},
            {
                "$push": {
                    "chat_history": {
                        "role": role,
                        "content": content,
                        "timestamp": datetime.utcnow(),
                    }
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
    except Exception:
        mark_sqlite_mode()
        sqlite_append_chat_message(report_id, role, content)


def get_chat_history(report_id: str) -> List[Dict]:
    """Return the chat_history array for a given report."""
    if should_use_sqlite() or not is_valid_object_id(report_id):
        doc = sqlite_get_report(report_id)
        if doc:
            return doc.get("chat_history", [])
        return []
        
    try:
        doc = get_report(report_id)
        if doc:
            return doc.get("chat_history", [])
        return []
    except Exception:
        mark_sqlite_mode()
        doc = sqlite_get_report(report_id)
        if doc:
            return doc.get("chat_history", [])
        return []
