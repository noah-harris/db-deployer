from contextlib import contextmanager
import sqlalchemy
from deployer import config
from deployer.dialects import SqlDialect

class Postgres(SqlDialect):
    DIALECT_NAME = 'postgresql'
    PYTHON_DRIVER = 'psycopg2'
    USERNAME='postgres'
    PASSWORD=config.DB_PASSWORD
    HOST='db'
    PORT=5432
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


    def create_database(self, database:str):
        pass


    @classmethod
    def _quote_identifier(cls,  name: str) -> str:
        return '"' + name.replace('"', '""') + '"'
    

    @classmethod
    def _cast_decimal(cls, column:str):
        return f"CONVERT(varchar(50), {cls._quote_identifier(column)}) AS {cls._quote_identifier(column)}"
    

    @classmethod
    def _cast_float(cls, column:str):
        return f"CONVERT(varchar(50), {cls._quote_identifier(column)}, 3) AS {cls._quote_identifier(column)}"