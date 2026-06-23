import sqlite3
import os
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "config" / "INDRA_memory.db"

def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_all_memory() -> str:
    _init_db()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM memory ORDER BY timestamp DESC LIMIT 50')
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "[DATABASE MEMORY: Empty]"
        
        lines = ["[DATABASE MEMORY: Recent facts & context]"]
        for key, value in rows:
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines) + "\n\n"
    except Exception as e:
        return f"[DATABASE MEMORY ERROR: {e}]\n\n"

def memory_manager(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Stores or retrieves information from INDRA's long-term memory.
    """
    _init_db()
    action = parameters.get("action", "query").lower()
    key = parameters.get("key", "").strip().lower()
    value = parameters.get("value", "")

    if action == "store":
        if not key or not value:
            return "Must provide both a 'key' and a 'value' to store."
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO memory (key, value)
                VALUES (?, ?)
            ''', (key, value))
            conn.commit()
            conn.close()
            return f"Successfully committed to long-term memory. Key: '{key}'"
        except Exception as e:
            return f"Failed to store memory: {e}"
            
    elif action == "query":
        if not key:
            # Return all keys to let INDRA know what is stored
            try:
                conn = sqlite3.connect(str(DB_PATH))
                cursor = conn.cursor()
                cursor.execute('SELECT key FROM memory')
                keys = [row[0] for row in cursor.fetchall()]
                conn.close()
                if not keys:
                    return "Memory is currently empty."
                return "Stored memory keys:\n" + "\n".join(f"- {k}" for k in keys)
            except Exception as e:
                return f"Failed to list memories: {e}"
                
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM memory WHERE key = ?', (key,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return f"Memory for '{key}':\n{row[0]}"
            else:
                return f"No memory found for key: '{key}'"
        except Exception as e:
            return f"Failed to query memory: {e}"
            
    elif action == "forget":
        if not key:
            return "Must provide a 'key' to forget."
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute('DELETE FROM memory WHERE key = ?', (key,))
            changes = conn.total_changes
            conn.commit()
            conn.close()
            if changes > 0:
                return f"Successfully erased '{key}' from memory."
            else:
                return f"No memory found to erase for key: '{key}'"
        except Exception as e:
            return f"Failed to erase memory: {e}"
            
    else:
        return f"Unknown memory action: {action}"
