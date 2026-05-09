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
PASSWORD = os.getenv("PASSWORD")
EXTERNAL_PORT = os.getenv("EXTERNAL_PORT")
HOSTNAME = os.getenv("HOST_MACHINE_NAME") or "localhost"
TIMESTAMP = pd.Timestamp.now().strftime("%Y-%m-%d %H.%M.%S")

RESTORE_POINTS_DIR = Path("/app/restore/")
RESTORE_POINTS_DIR.mkdir(exist_ok=True, parents=True)

SQL_SCRIPTS_DIR = Path("/app/sql-scripts/")
SQL_SCRIPTS_DIR.mkdir(exist_ok=True, parents=True)

SUPPORTED_DIALECTS = ["mssql", "postgres"]
DIALECT = os.getenv("DIALECT")

ORDER_FILE = SQL_SCRIPTS_DIR / 'order.json'
STATUS_FILE = SQL_SCRIPTS_DIR / 'status.json'