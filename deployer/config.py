import colorlog
import logging
import os
from pathlib import Path
import pandas as pd

def make_logger(name: str) -> logging.Logger:
    root = logging.getLogger()
    if not root.handlers:
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            fmt='%(log_color)s[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt="%H:%M:%S"
        ))
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
    return logging.getLogger(name)

# ==================== CREDENTIALS ====================
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
INTERNAL_PORT = os.getenv("INTERNAL_PORT")
EXTERNAL_PORT = os.getenv("EXTERNAL_PORT")
DIALECT = os.getenv("DIALECT")
HOST = os.getenv("HOST")

TIMESTAMP = pd.Timestamp.now().strftime("%Y-%m-%d %H.%M.%S")

RESTORE_POINTS_DIR = Path("/app/restore/")
RESTORE_POINTS_DIR.mkdir(exist_ok=True, parents=True)

SQL_SCRIPTS_DIR = Path("/app/sql-scripts/")
SQL_SCRIPTS_DIR.mkdir(exist_ok=True, parents=True)

SUPPORTED_DIALECTS = ["mssql", "postgres"]


ORDER_FILE = SQL_SCRIPTS_DIR / 'order.json'
STATUS_FILE = SQL_SCRIPTS_DIR / 'status.json'