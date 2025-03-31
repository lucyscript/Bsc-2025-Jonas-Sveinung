"""Utilities for PostgreSQL database connection."""

import logging

import psycopg2

from src.db.config import load_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def connect():
    """Connect to the PostgreSQL database server."""
    try:
        config = load_config()

        conn = psycopg2.connect(**config)
        logging.info("Connected to the PostgreSQL server.")
        return conn
    except (psycopg2.DatabaseError, Exception) as error:
        logging.error(f"Error connecting to the PostgreSQL server: {error}")
        raise


def create_tables(conn):
    """Creates all database tables if they don't exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    platform VARCHAR(50)
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id VARCHAR(255) PRIMARY KEY,
                    conversation_id INT NOT NULL 
                        REFERENCES conversations(conversation_id),
                    sender VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    message_type VARCHAR(50) DEFAULT 'text',
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id SERIAL PRIMARY KEY,
                    message_id VARCHAR(255) NOT NULL 
                        REFERENCES messages(message_id),
                    rating INT,
                    emoji VARCHAR(10)
                );
                """
            )

            conn.commit()
        logging.info("Database tables created successfully.")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")
        conn.rollback()
        raise


def create_conversation(conn, user_id, platform=None):
    """Creates a new conversation and returns the conversation_id."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (user_id, platform)
                VALUES (%s, %s)
                RETURNING conversation_id;
                """,
                (user_id, platform),
            )
            conversation_id = cur.fetchone()[0]
            conn.commit()
        return conversation_id
    except Exception as e:
        logging.error(f"Error creating conversation: {e}")
        conn.rollback()
        raise


def add_message(
    conn, message_id, conversation_id, sender, content, message_type="text"
):
    """Adds a message to a conversation and returns the message_id."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages 
                    (message_id, conversation_id, sender, content, message_type)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING message_id;
                """,
                (message_id, conversation_id, sender, content, message_type),
            )
            message_id = cur.fetchone()[0]
            conn.commit()
        return message_id
    except Exception as e:
        logging.error(f"Error adding message: {e}")
        conn.rollback()
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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback 
                (message_id, rating, emoji)
                VALUES (%s, %s, %s)
                RETURNING feedback_id;
                """,
                (message_id, rating, emoji),
            )
            feedback_id = cur.fetchone()[0]
            conn.commit()
        return feedback_id
    except Exception as e:
        logging.error(f"Error adding feedback: {e}")
        conn.rollback()
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
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id 
                FROM conversations
                WHERE user_id = %s AND platform = %s
                ORDER BY conversation_id DESC
                LIMIT 1;
                """,
                (user_id, platform),
            )
            row = cur.fetchone()

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
