"""Hermes Print Automation - SQLite Database & State Management.

Provides robust, persistent multi-turn session tracking and message history
per WhatsApp phone number.
"""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.config import settings
from app.models import SessionData, SessionStatus


def get_db_connection() -> sqlite3.Connection:
    """Create a thread-safe connection to the SQLite database with row factory."""
    db_path = settings.database_file_path
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    """Initialize database tables and indexes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # User sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                phone_number TEXT PRIMARY KEY,
                customer_name TEXT DEFAULT '',
                current_file_path TEXT,
                original_filename TEXT,
                file_url TEXT,
                page_count INTEGER DEFAULT 0,
                color_pages_count INTEGER DEFAULT 0,
                bw_pages_count INTEGER DEFAULT 0,
                paper_size TEXT DEFAULT 'A4',
                orientation TEXT DEFAULT 'Potret',
                document_summary TEXT DEFAULT '',
                copies INTEGER DEFAULT 1,
                color_mode TEXT DEFAULT 'auto',
                page_range TEXT DEFAULT 'all',
                estimated_price INTEGER DEFAULT 0,
                session_status TEXT DEFAULT 'IDLE',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        
        # Message log table for multi-turn LLM context
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                action TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_phone ON conversation_history(phone_number);"
        )
        conn.commit()


def get_or_create_session(phone_number: str, customer_name: str = "") -> SessionData:
    """Retrieve existing session or create a new IDLE session for the phone number."""
    now_iso = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        
        if row:
            data = dict(row)
            # Update customer name if provided and not currently saved
            if customer_name and not data.get("customer_name"):
                cursor.execute(
                    "UPDATE sessions SET customer_name = ?, updated_at = ? WHERE phone_number = ?",
                    (customer_name, now_iso, phone_number)
                )
                conn.commit()
                data["customer_name"] = customer_name
            return SessionData(**data)
        
        # Create fresh session
        new_session = SessionData(
            phone_number=phone_number,
            customer_name=customer_name or "",
            session_status=SessionStatus.IDLE,
            created_at=now_iso,
            updated_at=now_iso
        )
        cursor.execute(
            """
            INSERT INTO sessions (
                phone_number, customer_name, page_count, color_pages_count,
                bw_pages_count, paper_size, orientation, copies, color_mode,
                page_range, estimated_price, session_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_session.phone_number,
                new_session.customer_name,
                new_session.page_count,
                new_session.color_pages_count,
                new_session.bw_pages_count,
                new_session.paper_size,
                new_session.orientation,
                new_session.copies,
                new_session.color_mode,
                new_session.page_range,
                new_session.estimated_price,
                new_session.session_status.value,
                new_session.created_at,
                new_session.updated_at
            )
        )
        conn.commit()
        return new_session


def update_session(phone_number: str, **kwargs: Any) -> SessionData:
    """Update specific session attributes by phone number and return updated state."""
    kwargs["updated_at"] = datetime.now().isoformat()
    if "session_status" in kwargs and isinstance(kwargs["session_status"], SessionStatus):
        kwargs["session_status"] = kwargs["session_status"].value

    fields = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [phone_number]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sessions SET {fields} WHERE phone_number = ?", values)
        conn.commit()
        
        cursor.execute("SELECT * FROM sessions WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Session for phone {phone_number} does not exist.")
        return SessionData(**dict(row))


def reset_session_file(phone_number: str) -> SessionData:
    """Reset active document and print configuration for a session."""
    return update_session(
        phone_number,
        current_file_path=None,
        original_filename=None,
        file_url=None,
        page_count=0,
        color_pages_count=0,
        bw_pages_count=0,
        paper_size="A4",
        orientation="Potret",
        document_summary="",
        copies=1,
        color_mode="auto",
        page_range="all",
        estimated_price=0,
        session_status=SessionStatus.IDLE
    )


def add_conversation_history(
    phone_number: str,
    role: str,
    message: str,
    action: str = ""
) -> None:
    """Append a dialogue turn into the persistent message history."""
    now_iso = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversation_history (phone_number, role, message, action, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (phone_number, role, message, action, now_iso)
        )
        conn.commit()


def get_recent_conversation(phone_number: str, limit: int = 8) -> List[Dict[str, str]]:
    """Retrieve recent conversation history formatted for LLM dialogue context."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, message, action, timestamp
            FROM conversation_history
            WHERE phone_number = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (phone_number, limit)
        )
        rows = cursor.fetchall()
        # Return in chronological order
        return [dict(r) for r in reversed(rows)]
