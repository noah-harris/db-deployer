import signal
import sys
import threading
from config import *
from dialects import mapping, SqlDialect

logger = make_logger("deployer.entrypoint")
dialect: SqlDialect = mapping.get(DIALECT.lower())

stop_event = threading.Event()


def teardown(signum, frame):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logger.info(f"Received signal {signum} — starting teardown")
    stop_event.set()
    logger.info("Teardown complete — exiting")
    sys.exit(0)


def backup_loop():
    interval = RESTORE_POINT_INTERVAL_MINUTES * 60
    while not stop_event.wait(interval):
        dialect.create_restore_point()


signal.signal(signal.SIGTERM, teardown)
signal.signal(signal.SIGINT, teardown)

dialect.init_database()

if RESTORE_POINT_INTERVAL_MINUTES > 0:
    threading.Thread(target=backup_loop, daemon=True).start()
    logger.info(f"Scheduled restore points every {RESTORE_POINT_INTERVAL_MINUTES} minute(s), retention={RESTORE_POINT_RETENTION or 'unlimited'}")

while True:
    signal.pause()
