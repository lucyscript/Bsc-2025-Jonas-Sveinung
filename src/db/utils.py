"""Utilities for SQLite database connection."""

import logging
import sqlite3

from src.db.config import load_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def connect():
    """Connect to the SQLite database."""
    try:
        config = load_config()
        conn = sqlite3.connect(config["database"])
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        logging.info("Connected to the SQLite database.")
        return conn
    except (sqlite3.Error, Exception) as error:
        logging.error(f"Error connecting to the SQLite database: {error}")
        raise


def create_tables(conn):
    """Creates all database tables if they don't exist."""
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    platform TEXT
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) 
                        REFERENCES conversations(conversation_id)
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    rating INTEGER,
                    emoji TEXT,
                    FOREIGN KEY (message_id) 
                        REFERENCES messages(message_id)
                );
                """
            )

        logging.info("Database tables created successfully.")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")
        raise


def create_conversation(conn, user_id, platform=None):
    """Creates a new conversation and returns the conversation_id."""
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (user_id, platform)
                VALUES (?, ?);
                """,
                (user_id, platform),
            )
            conversation_id = cursor.lastrowid
        return conversation_id
    except Exception as e:
        logging.error(f"Error creating conversation: {e}")
        raise


def add_message(
    conn, message_id, conversation_id, sender, content, message_type="text"
):
    """Adds a message to a conversation and returns the message_id."""
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO messages 
                    (message_id, conversation_id, sender, content, message_type)
                VALUES (?, ?, ?, ?, ?);
                """,
                (message_id, conversation_id, sender, content, message_type),
            )
        return message_id
    except Exception as e:
        logging.error(f"Error adding message: {e}")
        raise


def add_feedback(message_id, rating=None, emoji=None):
    """Adds feedback for a specific message.

    Args:
        message_id: ID of the bot message being rated
        rating: Numeric rating (1-6)
        emoji: Reaction emoji
    """
    conn = None
    try:
        conn = connect()
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO feedback 
                (message_id, rating, emoji)
                VALUES (?, ?, ?);
                """,
                (message_id, rating, emoji),
            )
            feedback_id = cursor.lastrowid
        return feedback_id
    except Exception as e:
        logging.error(f"Error adding feedback: {e}")
        raise
    finally:
        if conn:
            conn.close()


def record_conversation_message(
    message_id,
    user_id,
    platform,
    message_text=None,
    is_user_message=True,
    message_type="text",
):
    """Records a message in a conversation.

    This helper function is designed to be used with the WhatsApp and Telegram
    routers, which share global dictionaries from processors.py.

    Args:
        message_id: ID of the message
        user_id: User identifier (phone number or chat ID)
        platform: "whatsapp" or "telegram"
        message_text: The text content of the message
        is_user_message: True if this is a message from the user, False if bot
        message_type: Type of message (e.g., 'text', 'image')

    Returns:
        Dictionary with conversation_id and message_id
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT conversation_id 
            FROM conversations
            WHERE user_id = ? AND platform = ?
            ORDER BY conversation_id DESC
            LIMIT 1;
            """,
            (user_id, platform),
        )
        row = cursor.fetchone()

        if row:
            conversation_id = row[0]
        else:
            conversation_id = create_conversation(conn, user_id, platform)

        sender = "user" if is_user_message else "bot"
        message_id = add_message(
            conn,
            message_id,
            conversation_id=conversation_id,
            sender=sender,
            content=message_text,
            message_type=message_type,
        )

        return {"conversation_id": conversation_id, "message_id": message_id}
    except Exception as e:
        logging.error(f"Error recording conversation message: {e}")
        raise
    finally:
        if conn:
            conn.close()
