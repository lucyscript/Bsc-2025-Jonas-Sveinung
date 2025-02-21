"""Config file for database connection."""

import os
from urllib.parse import urlparse


def load_config():
    """Loads database configuration from environment variables."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set.")

    result = urlparse(database_url)
    config = {
        "host": result.hostname,
        "database": result.path[1:],
        "user": result.username,
        "password": result.password,
        "port": result.port,
    }
    return config


if __name__ == "__main__":
    config = load_config()
    print(config)
