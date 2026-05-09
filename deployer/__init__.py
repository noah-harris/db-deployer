from .config import *
from .dialects import mapping, SqlDialect
dialect:SqlDialect = mapping.get(DIALECT.lower())


