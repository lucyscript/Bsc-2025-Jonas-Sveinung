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
        # Load database configuration
        config = load_config()

        # Connecting to the PostgreSQL server
        logging.info("Connecting to the PostgreSQL server...")
        conn = psycopg2.connect(**config)
        logging.info("Connected to the PostgreSQL server.")
        return conn
    except (psycopg2.DatabaseError, Exception) as error:
        logging.error(f"Error connecting to the PostgreSQL server: {error}")
        raise


def create_feedback_table(conn):
    """Creates the feedback table if it doesn't exist."""
    logging.info("Creating feedback table...")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    emoji TEXT,
                    timestamp INTEGER
                );
                """
            )
            conn.commit()
        logging.info("Feedback table created successfully.")
    except Exception as e:
        logging.error(f"Error creating feedback table: {e}")
        raise


def insert_feedback(conn, emoji, timestamp):
    """Inserts feedback into the feedback table."""
    logging.info("Inserting feedback...")
    create_feedback_table(conn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (emoji, timestamp)
                VALUES (%s, %s);
                """,
                (emoji, timestamp),
            )
            conn.commit()
        logging.info("Feedback inserted successfully.")
    except Exception as e:
        logging.error(f"Error inserting feedback: {e}")
        raise


def get_all_feedback(conn):
    """Retrieves all feedback from the feedback table and returns."""
    logging.info("Retrieving all feedback...")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT emoji, timestamp FROM feedback")
            rows = cur.fetchall()
            feedback_list = []
            if rows:
                logging.info("Feedback data:")
                for row in rows:
                    logging.info(f"  Emoji: {row[0]}, Timestamp: {row[1]}")
                    feedback_list.append({"emoji": row[0], "timestamp": row[1]})
            else:
                logging.info("No feedback data found.")
            return feedback_list
    except Exception as e:
        logging.error(f"Error retrieving feedback: {e}")
        raise
