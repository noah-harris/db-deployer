from __future__ import annotations

from contextlib import contextmanager
import sqlalchemy
from ._sql_dialect import SQLDialect
from .database_object import DatabaseObject
from .column_schema import ColumnSchema

class MicrosoftSQLServer(SQLDialect):
    PYTHON_DRIVER = 'pyodbc'
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


    @classmethod
    def _disable_triggers(cls, table: DatabaseObject):
        with cls._get_autocommit_connection(database=table.database) as conn:
            conn.execute(sqlalchemy.text(f"ALTER TABLE {cls._get_object_identifier(table)} DISABLE TRIGGER ALL"))


    @classmethod
    def _enable_triggers(cls, table: DatabaseObject):
        with cls._get_autocommit_connection(database=table.database) as conn:
            conn.execute(sqlalchemy.text(f"ALTER TABLE {cls._get_object_identifier(table)} ENABLE TRIGGER ALL"))


    @classmethod
    def _get_table_schema(cls, obj:DatabaseObject) -> list[ColumnSchema]:
        if obj.type != "table":
            raise ValueError(f"Object {obj.database}.{obj.schema}.{obj.name} is not a table.")

        # Not that this query is actually an ANSI Standard
        sql = """
            SELECT
                isc.column_name,
                isc.data_type,
                isc.is_nullable,
                isc.numeric_precision,
                isc.numeric_scale,
                isc.character_maximum_length
            FROM information_schema.columns AS isc
            JOIN sys.columns c ON c.object_id = OBJECT_ID(QUOTENAME(isc.table_schema) + '.' + QUOTENAME(isc.table_name)) AND c.name = isc.column_name
            WHERE 1=1 
                AND isc.table_schema = :schema AND isc.table_name = :table
                AND c.is_computed = 0
            ORDER BY isc.ordinal_position
        """
        with cls.get_connection(obj.database) as conn:
            conn:sqlalchemy.engine.Connection
            rows = conn.execute(sqlalchemy.text(sql), {"schema": obj.schema, "table": obj.name}).fetchall()
        return [
            ColumnSchema(
                name=r.column_name,
                db_type=r.data_type.lower(),
                nullable=(r.is_nullable == "YES"),
                numeric_precision=r.numeric_precision,
                numeric_scale=r.numeric_scale,
                char_length=r.character_maximum_length,
            )
            for r in rows
        ]