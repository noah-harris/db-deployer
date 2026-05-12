import signal
import sys
from config import *
from dialects import mapping, SqlDialect
dialect:SqlDialect = mapping.get(DIALECT.lower())


def teardown(signum, frame):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    dialect.create_restore_point()
    sys.exit(0)

signal.signal(signal.SIGTERM, teardown)
signal.signal(signal.SIGINT, teardown)

dialect.init_database()

while True:
    signal.pause()
