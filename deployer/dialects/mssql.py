from __future__ import annotations

from contextlib import contextmanager
import sqlalchemy
from deployer import config
from deployer.dialects import SqlDialect


class MicrosoftSQLServer(SqlDialect):
    DIALECT_NAME = 'mssql'
    PYTHON_DRIVER = 'pyodbc'
    USERNAME='sa'
    PASSWORD=config.PASSWORD
    HOST='db'
    PORT=1433
    MASTER_DATABASE='master'
    CONNECTION_PARAMS = {"driver": "ODBC Driver 17 for SQL Server", "TrustServerCertificate": "yes"}

    VALID_OBJECT_TYPES = [
        "schema",
        "table", 
        "view", 
        "index",
        "stored_procedure", 
        "scalar_valued_function", 
        "table_valued_function", 
        "trigger"
    ]


    @classmethod
    @contextmanager
    def get_connection(cls, database:str, timeout:int=2, **engine_kwargs):
        cxnstr:str = cls._get_connection_string(database)
        engine:sqlalchemy.engine.Engine = sqlalchemy.create_engine(cxnstr, pool_pre_ping=True, connect_args={"timeout": timeout}, **engine_kwargs)
        conn:sqlalchemy.engine.Connection = engine.connect()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.commit()
            conn.close()
            engine.dispose()
        

    @classmethod
    @contextmanager
    def _get_autocommit_connection(cls, database:str, timeout:int=2, **engine_kwargs):
        cxnstr:str = cls._get_connection_string(database)
        engine:sqlalchemy.engine.Engine = sqlalchemy.create_engine(cxnstr, pool_pre_ping=True, connect_args={"timeout": timeout}, **engine_kwargs)
        conn:sqlalchemy.engine.Connection = engine.connect()
        conn:sqlalchemy.engine.Connection = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            yield conn
        finally:
            conn.close()
            engine.dispose()


    @classmethod
    def create_database(cls, database):
        with cls._get_autocommit_connection(database=cls.MASTER_DATABASE) as conn:
            conn:sqlalchemy.engine.Connection
            conn.execute(sqlalchemy.text(f"CREATE DATABASE [{database}]"))


    @staticmethod
    def _quote_identifier(name: str) -> str:
        return "[" + name.replace("]", "]]") + "]"
    
    @classmethod
    def _cast_decimal(cls, column:str) -> str:
        return f"CONVERT(VARCHAR(50), {cls._quote_identifier(column)}) AS {cls._quote_identifier(column)}"
    
    @classmethod
    def _cast_float(cls, column:str) -> str:
        return f"CONVERT(VARCHAR(50), {cls._quote_identifier(column)}, 3) AS {cls._quote_identifier(column)}"


