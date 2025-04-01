"""Config file for SQLite database connection."""

import os
import logging


def load_config():
    """Loads SQLite database configuration with a fixed database path."""
    cwd = os.getcwd()
    
    data_dir = os.path.join(cwd, "data")
    
    os.makedirs(data_dir, exist_ok=True)
    
    db_path = os.path.join(data_dir, "factibot.db")
    
    logging.info(f"Using SQLite database at: {db_path}")
    
    return {"database": db_path}


if __name__ == "__main__":
    config = load_config()
    print(config)
