"""Config file for SQLite database connection."""

import os


def load_config():
    """Loads SQLite database configuration with a fixed database path."""
    db_path = os.path.join("data", "factibot.db")

    os.makedirs("data", exist_ok=True)

    return {"database": db_path}


if __name__ == "__main__":
    config = load_config()
    print(config)
