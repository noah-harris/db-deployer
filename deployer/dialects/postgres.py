from contextlib import contextmanager
import sqlalchemy
from . import SqlDialect
from .database_object import DatabaseObject

class Postgres(SqlDialect):
    PYTHON_DRIVER = 'psycopg2'
    MASTER_DATABASE='postgres'
    CONNECTION_PARAMS = {}

    VALID_OBJECT_TYPES = [
        "schema",
        "table", 
        "view", 
        "index",
        "stored_procedure", 
        "scalar_value_function", 
        "table_valued_function", 
        "trigger"
    ]

    @classmethod
    def _get_connection_string(cls, database: str) -> str:
        base = f"{cls.DIALECT_NAME}+{cls.PYTHON_DRIVER}://{cls.USERNAME}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{database}"
        if cls.CONNECTION_PARAMS:
            param_str = "&".join(f"{k}={v}" for k, v in cls.CONNECTION_PARAMS.items())
            return f"{base}?{param_str}"
        return base

    @classmethod
    @contextmanager
    def get_connection(cls, database):
        cxnstr:str = cls._get_connection_string(database)
        engine:sqlalchemy.engine.Engine = sqlalchemy.create_engine(cxnstr, pool_pre_ping=True, connect_args={"connect_timeout": 2}, **cls.CONNECTION_PARAMS)
        conn:sqlalchemy.engine.Connection = engine.connect()
        conn.execute(sqlalchemy.text("SET extra_float_digits = 3"))
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.commit()
            conn.close()
            engine.dispose()
        return

    @classmethod
    @contextmanager
    def _get_autocommit_connection(cls, database: str):
        cxnstr: str = cls._get_connection_string(database)
        engine: sqlalchemy.engine.Engine = sqlalchemy.create_engine(cxnstr, pool_pre_ping=True)
        conn: sqlalchemy.engine.Connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            yield conn
        finally:
            conn.close()
            engine.dispose() 


    @classmethod
    def create_database(cls, database: str):
        with cls._get_autocommit_connection(database=cls.MASTER_DATABASE) as conn:
            conn.execute(sqlalchemy.text(f"CREATE DATABASE {cls._quote_identifier(database)}"))


    @classmethod
    def _quote_identifier(cls,  name: str) -> str:
        return '"' + name.replace('"', '""') + '"'
    

    @classmethod
    def _cast_decimal(cls, column: str) -> str:
        return f"CAST({cls._quote_identifier(column)} AS VARCHAR(50)) AS {cls._quote_identifier(column)}"

    @classmethod
    def _cast_float(cls, column: str) -> str:
        return f"CAST({cls._quote_identifier(column)} AS VARCHAR) AS {cls._quote_identifier(column)}"

    @classmethod
    def _disable_triggers(cls, table: DatabaseObject):
        with cls._get_autocommit_connection(database=table.database) as conn:
            conn.execute(sqlalchemy.text(f"ALTER TABLE {cls._get_object_identifier(table)} DISABLE TRIGGER ALL"))

    @classmethod
    def _enable_triggers(cls, table: DatabaseObject):
        with cls._get_autocommit_connection(database=table.database) as conn:
            conn.execute(sqlalchemy.text(f"ALTER TABLE {cls._get_object_identifier(table)} ENABLE TRIGGER ALL"))