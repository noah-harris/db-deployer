from ._sql_dialect import SQLDialect
from .mssql import MicrosoftSQLServer
from .postgres import Postgres


mapping = {
    "mssql": MicrosoftSQLServer,
    "postgresql": Postgres
}
