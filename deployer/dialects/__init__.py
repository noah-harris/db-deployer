from __future__ import annotations

from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
import sqlalchemy
import json
import pandas as pd
import csv
import os
import hashlib
import shutil
import subprocess
import sys

from decimal import Decimal
from typing import Any

from .column_schema import ColumnSchema
from .datatype_mapping import *
from .database_object import DatabaseObject
import config

logger = config.make_logger("deployer.dialects")

class SqlDialect:
    DIALECT_NAME:str=config.DIALECT
    PYTHON_DRIVER:str=''
    USERNAME:str=config.DB_USERNAME
    PASSWORD:str=config.DB_PASSWORD
    HOST:str=config.HOST
    PORT:int=config.INTERNAL_PORT
    MASTER_DATABASE:str=''
    CONNECTION_PARAMS:dict = {}

    VALID_OBJECT_TYPES:list[str] = []
    
    DATABASE_OBJECTS = {}

    @classmethod
    def _latest_restore_point(cls) -> Path | None:
        dirs = sorted(
            (d for d in config.RESTORE_POINTS_DIR.iterdir() if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )
        if len(dirs) > 0:
            return dirs[0]
        
        if not dirs:
            return
        
        
    @classmethod
    def _get_connection_string(cls, database:str) -> str:
        base = f"{cls.DIALECT_NAME}+{cls.PYTHON_DRIVER}://{cls.USERNAME}:{cls.PASSWORD}@{cls.HOST},{cls.PORT}/{database}"
        if cls.PASSWORD is None:
            redacted_password = None
        else:
            redacted_password = "*" * len(cls.PASSWORD)
        base_redacted = f"{cls.DIALECT_NAME}+{cls.PYTHON_DRIVER}://{cls.USERNAME}:{redacted_password}@{cls.HOST},{cls.PORT}/{database}"
        logger.debug(f"CONNECTION_STRING={base_redacted} with params")
        if cls.CONNECTION_PARAMS != {}:
            param_str = "&".join([f"{k}={v}" for k, v in cls.CONNECTION_PARAMS.items()])
            return f"{base}?{param_str}"
        return base
    

    @classmethod
    @contextmanager
    def get_connection(cls, database) -> sqlalchemy.engine.Connection:
        raise NotImplementedError("Subclasses must implement this method")
    

    ########## Database ##########
    @classmethod
    def _get_databases_to_create(cls) -> list[str]:
        database_names = []
        DATABASES:list[Path] = list(config.SQL_SCRIPTS_DIR.iterdir())
        for database in DATABASES:
            if database.is_dir():
                database_names.append(database.name)
        return database_names


    @classmethod
    def create_database(cls, database):
        raise NotImplementedError("Subclasses must implement this method")
    

    @classmethod
    def create_object(cls, obj:DatabaseObject):
        logger.info(f"Creating {obj.type} {obj.database}.{obj.schema}.{obj.name} from {obj.script_path}")
        try:
            with cls.get_connection(database=obj.database) as conn:
                conn:sqlalchemy.engine.Connection
                conn.execute(sqlalchemy.text(obj.definition))
                conn.commit()
        except Exception as e:
            raise RuntimeError(f"Failed to create {obj.type} {obj.database}.{obj.schema}.{obj.name} from {obj.script_path}") from e


    @classmethod
    def _get_tables(cls, database:str) -> list[DatabaseObject]:
        tables = []
        for obj in cls._get_project_load_order():
            if obj.database == database and obj.type == "table":
                tables.append(obj)
        return tables
    

    @classmethod
    def _get_table_schema(cls, obj:DatabaseObject) -> list[ColumnSchema]:
        if obj.type != "table":
            raise ValueError(f"Object {obj.database}.{obj.schema}.{obj.name} is not a table.")

        # Not that this query is actually an ANSI Standard
        sql = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                numeric_precision,
                numeric_scale,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
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
    

    @staticmethod
    def _pandas_dtype_for(col: ColumnSchema) -> Any:
        """
        Return the pandas dtype to coerce this column to AFTER reading from SQL.
        We use nullable extension dtypes so NULL is preserved without float upcast.

        Decimals/floats stay as 'object' because we cast them to text in the query;
        we'll convert them to Decimal/float in Python explicitly.
        """
        t = col.db_type
        if t in INTEGER_TYPES:
            return "Int64"  # nullable integer
        if t in DECIMAL_TYPES:
            return "object"  # will hold Decimal
        if t in FLOAT_TYPES:
            return "object"  # will hold float, parsed from text
        if t in BOOL_TYPES:
            return "boolean"  # nullable boolean
        if t in BINARY_TYPES:
            return "object"  # bytes
        # Dates and strings: leave as object for now; we handle conversion explicitly.
        return "object"


    @staticmethod
    def _quote_field(s: str) -> str:
        """Always-quoted text field with proper escaping."""
        return '"' + s.replace('"', '""') + '"'
    

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        raise NotImplementedError("Subclasses must implement this method")
    

    @classmethod
    def _get_object_identifier(cls, obj:DatabaseObject) -> str:
        return f"{cls._quote_identifier(obj.schema)}.{cls._quote_identifier(obj.name)}"


    @classmethod
    def _disable_triggers(cls, table: DatabaseObject):
        pass


    @classmethod
    def _enable_triggers(cls, table: DatabaseObject):
        pass


    @classmethod
    def _cast_decimal(cls, column:str) -> str:
        raise NotImplementedError("Subclasses must implement this method")
    

    @classmethod
    def _cast_float(cls, column:str) -> str:
        raise NotImplementedError("Subclasses must implement this method")


    @classmethod
    def _build_select(cls, obj:DatabaseObject) -> str:
        """
        Build a SELECT that casts decimal/float columns to text in the DB so
        pandas never sees them as Python floats. Other columns come through normally.
        """
        select_parts = []
        for col in cls._get_table_schema(obj):
            if col.db_type in DECIMAL_TYPES:
                select_parts.append(cls._cast_decimal(col.name))
            elif col.db_type in FLOAT_TYPES:
                select_parts.append(cls._cast_float(col.name))
            else:
                select_parts.append(cls._quote_identifier(col.name))
        order_by = ', '.join(str(i) for i in range(1, len(select_parts) + 1))
        return f"SELECT {', '.join(select_parts)} FROM {cls._get_object_identifier(obj)} ORDER BY {order_by}"


    @classmethod
    def _emit_field(cls, value: Any) -> str:
        """
        Emit a single CSV field per our convention:
        - None              -> ''           (unquoted empty = NULL)
        - numbers (int/Decimal) -> str(value) unquoted
        - everything else (already a str) -> quoted with "" escaping
        """
        if value is None:
            return ""
        # Decimal and int are written unquoted (they're numeric literals).
        if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
            return str(value)
        # Everything else is text and gets quoted.
        return cls._quote_field(str(value))


    @staticmethod
    def _serialize_cell(value: Any, col: ColumnSchema) -> Any:
        """
        Convert a pandas/Python value into something the csv writer will emit
        in the form we want.

        - NULL (None / pd.NA / NaN) -> None, which csv writer emits as empty unquoted.
        - Decimal -> Decimal (number; QUOTE_NONNUMERIC leaves it unquoted).
        - int (Int64 scalar) -> int.
        - bool -> "true"/"false" string (quoted).
        - bytes -> hex string (quoted).
        - datetime/date/time -> ISO 8601 string (quoted).
        - str -> str (quoted, including empty string as "").
        """
        # NULL detection: None, pd.NA, NaN, NaT all collapse to NULL.
        # We check pd.isna last and guard it because it raises on bytes/Decimal.
        if value is None or value is pd.NA:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass  # non-scalar or unhashable — definitely not NULL

        t = col.db_type

        if t in INTEGER_TYPES:
            return int(value)

        if t in DECIMAL_TYPES:
            # Already a Decimal object. QUOTE_NONNUMERIC leaves numbers unquoted.
            return value

        if t in FLOAT_TYPES:
            # Came back as text from the DB cast — keep as text to preserve exact repr.
            # It will be quoted by QUOTE_NONNUMERIC, which is fine; we re-parse on import.
            return str(value)

        if t in BOOL_TYPES:
            return "true" if bool(value) else "false"

        if t in BINARY_TYPES:
            if isinstance(value, memoryview):
                value = bytes(value)
            return value.hex()

        if t in DATE_TYPES:
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        if t in TIMESTAMP_TYPES or t in TIMESTAMPTZ_TYPES or t in TIME_TYPES:
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        # Default: string
        return str(value)


    @staticmethod
    def _deserialize_cell(text_val: str, was_quoted: bool, col: ColumnSchema) -> Any:
        """
        Convert a (text, was_quoted) pair back into the right Python value
        given the column's DB type.

        Key rule: an *unquoted* empty string is NULL. A *quoted* empty string is "".
        """
        if not was_quoted and text_val == "":
            return None  # NULL

        t = col.db_type

        if t in INTEGER_TYPES:
            # Numbers come through unquoted, but we accept either.
            return int(text_val)

        if t in DECIMAL_TYPES:
            return Decimal(text_val)

        if t in FLOAT_TYPES:
            return float(text_val)

        if t in BOOL_TYPES:
            return text_val.lower() == "true"

        if t in BINARY_TYPES:
            return bytes.fromhex(text_val)

        if t in DATE_TYPES:
            return pd.Timestamp(text_val).date()

        if t in TIMESTAMP_TYPES or t in TIMESTAMPTZ_TYPES:
            return pd.Timestamp(text_val)

        if t in TIME_TYPES:
            return pd.Timestamp(text_val).time()

        # Plain string — including the quoted empty string case.
        return text_val


    @staticmethod
    def _parse_body_with_quote_info(body: str) -> list[list[tuple[str, bool]]]:
        """
        Parse the entire CSV body (everything after the header) as a stream of
        fields, tracking which fields were quoted. Handles embedded newlines
        inside quoted fields and "" escapes.

        Dialect: delimiter=','  quote='"'  doublequote escape  CRLF or LF row terminator.
        Embedded \\r and \\n inside quoted fields are preserved as-is.
        """
        rows: list[list[tuple[str, bool]]] = []
        cur_row: list[tuple[str, bool]] = []
        n = len(body)
        i = 0
        while i < n:
            # Start of a field.
            if body[i] == '"':
                # Quoted field — anything goes until a closing quote.
                i += 1
                buf = []
                while i < n:
                    ch = body[i]
                    if ch == '"':
                        if i + 1 < n and body[i + 1] == '"':
                            buf.append('"')
                            i += 2
                        else:
                            i += 1  # closing quote
                            break
                    else:
                        buf.append(ch)
                        i += 1
                cur_row.append(("".join(buf), True))
            else:
                # Unquoted field — read until comma or row terminator.
                start = i
                while i < n and body[i] not in (",", "\n", "\r"):
                    i += 1
                cur_row.append((body[start:i], False))

            # Now expect comma, row terminator, or EOF.
            if i < n and body[i] == ",":
                i += 1
                if i == n:
                    cur_row.append(("", False))
                    rows.append(cur_row)
                    cur_row = []
            elif i < n and body[i] in ("\n", "\r"):
                # Consume \r\n or \n or \r (any of the three).
                if body[i] == "\r" and i + 1 < n and body[i + 1] == "\n":
                    i += 2
                else:
                    i += 1
                rows.append(cur_row)
                cur_row = []
            # else: EOF — handled below
        if cur_row:
            rows.append(cur_row)
        return rows


    @classmethod
    def export_table_to_csv(cls, table: DatabaseObject, restore_point_path: Path):
        """
        Read a table from the DB and write it to a CSV file.

        The destination table's schema is the source of truth — no sidecar is
        written. On import, the schema is re-introspected from the live database.

        Output:
        - <table.script_path>  the CSV (UTF-16 LE with BOM, CRLF terminators,
                                all non-null text/temporal/binary fields quoted,
                                NULL = unquoted empty, '' = quoted empty)
        """
        with cls.get_connection(database=table.database) as conn:
            cols = cls._get_table_schema(table)  # validate table exists before we do all the work

        with cls.get_connection(database=table.database) as conn:
            df = pd.read_sql_query(
                sqlalchemy.text(cls._build_select(table)),
                conn,
                dtype={c.name: cls._pandas_dtype_for(c) for c in cols},
            )

        # Convert decimal columns from text to Decimal so they survive untouched.
        # (We cast in SQL to text, so df[col] is currently strings or pd.NA.)
        for c in cols:
            if c.db_type in DECIMAL_TYPES:
                df[c.name] = df[c.name].map(lambda v: Decimal(v) if v is not None and not pd.isna(v) else None)

        # We write manually because csv.QUOTE_NONNUMERIC quotes None as "",
        # which would collide with our convention (empty string is "", NULL is unquoted empty).
        # Encoding is UTF-16 LE with BOM ("utf-16") for Windows/SQL Server compatibility.
        csv_path = restore_point_path / table.database / f"{table.schema}.{table.name}.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-16", newline="") as f:
            f.write(",".join(cls._quote_field(c.name) for c in cols) + "\r\n")
            for row in df.itertuples(index=False, name=None):
                cells = [cls._serialize_cell(v, col) for v, col in zip(row, cols)]
                f.write(",".join(cls._emit_field(cell) for cell in cells) + "\r\n")


    @classmethod
    def read_csv_to_sql(cls, table: DatabaseObject) -> pd.DataFrame:
        """
        Read a CSV produced by export_table_to_csv back into a DataFrame whose
        column dtypes match the destination table, with NULL vs '' preserved.

        The destination table must already exist with the correct schema — its
        columns are introspected from the live database and used to type the
        DataFrame. The CSV header is validated against this schema and a
        ValueError is raised on any mismatch (column count, names, or order).
        """
        cols = cls._get_table_schema(table)
        expected_names = [c.name for c in cols]
        raw_rows: list[list[tuple[str, bool]]] = []

        restore_point = cls._latest_restore_point()

        if not restore_point:
            logger.warning(f"No restore point found; skipping CSV import for {table.database}.{table.schema}.{table.name}.")
            return

        csv_path: Path = restore_point / table.database / f"{table.schema}.{table.name}.csv"

        if not csv_path.exists():
            logger.warning(f"Warning: CSV for table {table.database}.{table.schema}.{table.name} not found at {csv_path}. Skipping import.")
            return
    
        raw = csv_path.read_bytes()
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            encoding = "utf-16"
        elif raw[:3] == b"\xef\xbb\xbf":
            encoding = "utf-8-sig"
        else:
            encoding = "utf-8"
        with open(csv_path, "r", encoding=encoding, newline="") as f:
            # Read header first.
            header_line = f.readline()
            if not header_line:
                raise ValueError(f"CSV {csv_path} is empty (no header).")
            header = next(csv.reader([header_line]))

            # Validate header against the live table schema. Fail loudly on any mismatch.
            if header != expected_names:
                extra_in_csv = [c for c in header if c not in expected_names]
                missing_from_csv = [c for c in expected_names if c not in header]
                details = []
                if len(header) != len(expected_names):
                    details.append(f"column count differs: CSV has {len(header)}, table has {len(expected_names)}")
                if extra_in_csv:
                    details.append(f"columns in CSV but not in table: {extra_in_csv}")
                if missing_from_csv:
                    details.append(f"columns in table but not in CSV: {missing_from_csv}")
                if not details:
                    # Same set of names, different order.
                    details.append("column order differs between CSV and table")
                raise ValueError(
                    f"CSV header does not match destination table "
                    f"{table.database}.{table.schema}.{table.name}.\n"
                    f"  CSV:    {header}\n"
                    f"  Table:  {expected_names}\n"
                    f"  Issue:  {'; '.join(details)}"
                )

            # Parse the rest as one stream so embedded newlines inside quoted
            # fields don't terminate a row.
            body = f.read()
            raw_rows = cls._parse_body_with_quote_info(body)

        # Build column-wise data.
        data: dict[str, list[Any]] = {c.name: [] for c in cols}
        for row_idx, row in enumerate(raw_rows, start=1):
            if len(row) != len(cols):
                raise ValueError(
                    f"CSV row {row_idx} has {len(row)} fields, expected {len(cols)} "
                    f"(table {table.database}.{table.schema}.{table.name})"
                )
            for (txt, was_quoted), col in zip(row, cols):
                data[col.name].append(cls._deserialize_cell(txt, was_quoted, col))

        # Build DataFrame with the same nullable dtypes we used on read.
        df = pd.DataFrame(data)
        for col in cols:
            target = cls._pandas_dtype_for(col)
            if target == "Int64":
                # Replace None with pd.NA so Int64 construction stays in the integer domain
                # (going through float64 would lose precision for big ints).
                vals = [pd.NA if v is None else v for v in data[col.name]]
                df[col.name] = pd.array(vals, dtype="Int64")
            elif target == "boolean":
                vals = [pd.NA if v is None else v for v in data[col.name]]
                df[col.name] = pd.array(vals, dtype="boolean")
            # object stays object — Decimals, bytes, datetimes, strings live here.

        # Chunk size respects SQL Server's 2100-parameter limit per statement.
        chunksize = max(1, 2000 // len(cols)) if cols else 1000

        cls._disable_triggers(table)
        try:
            with cls.get_connection(database=table.database) as conn:
                conn:sqlalchemy.engine.Connection
                df.to_sql(name=table.name, con=conn, schema=table.schema, if_exists="append", index=False, method='multi', chunksize=chunksize)
                conn.commit()
        finally:
            cls._enable_triggers(table)

        logger.info(f"Imported data for {table.database}.{table.schema}.{table.name} with {len(df)} rows.")
    

    @classmethod
    def _run_post_init_scripts(cls):

        with open(config.ORDER_FILE) as f:
            order_data = json.load(f)

        post_init_order = order_data['post-init']
        dbs = cls._get_databases_to_create()
        for db in dbs:
            post_init_dir = config.SQL_SCRIPTS_DIR / db / "post-init"
            for entry in post_init_order:
                file_name:str = entry["file"]
                file_path:Path = post_init_dir / file_name
                if file_name.endswith(".sql"):
                    logger.info(f"Running post-init SQL script: {file_path}")
                    query = file_path.read_text(encoding="utf-8")   
                    with cls.get_connection(database=entry["database"]) as conn:
                        conn.execute(sqlalchemy.text(query))
                        conn.commit()
                elif file_name.endswith(".py"):
                    logger.info(f"Running post-init Python script: {file_path}")
                    subprocess.run(
                        [sys.executable, str(file_path)],
                        cwd=post_init_dir,
                        check=True,
                        env={**os.environ, "PYTHONPATH": str(post_init_dir)},
                    )


    @classmethod
    def init_database(cls):
        """
            Deploys database objects
        """
        config.STATUS_FILE.write_text(json.dumps({"status": "not ready"}, indent=2))
        failures: list[str] = []

        dbs = cls._get_databases_to_create()
        for db in dbs:
            try:
                cls.create_database(db)
            except Exception as e:
                logger.error(f"Failed to create database {db}: {e}")
                failures.append(f"create_database({db})")

        objs = cls._get_project_load_order()
        for obj in objs:
            try:
                cls.create_object(obj)
            except Exception as e:
                logger.error(f"Failed to create {obj.type} {obj.database}.{obj.schema}.{obj.name}: {e}")
                failures.append(f"create_object({obj.database}.{obj.schema}.{obj.name})")

        if cls._latest_restore_point():
            for db in dbs:
                tables = cls._get_tables(db)
                for table in tables:
                    try:
                        cls.read_csv_to_sql(table)
                    except Exception as e:
                        logger.error(f"Failed to import {table.database}.{table.schema}.{table.name}: {e}")
                        failures.append(f"read_csv_to_sql({table.database}.{table.schema}.{table.name})")
        else:
            logger.warning("No restore point found; skipping CSV import for all tables.")

        try:
            cls._run_post_init_scripts()
        except Exception as e:
            logger.error(f"Post-init scripts failed: {e}")
            failures.append("post_init_scripts")

        if failures:
            logger.warning(f"Database initialization completed with {len(failures)} failure(s): {failures}")
        else:
            config.STATUS_FILE.write_text(json.dumps({"status": "ready"}, indent=2))
            logger.info("Database initialization complete")


    @classmethod
    def _prune_restore_points(cls):
        if config.RESTORE_POINT_RETENTION == 0:
            return
        dirs = sorted(
            (d for d in config.RESTORE_POINTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: d.name,
            reverse=True,
        )
        for old_dir in dirs[config.RESTORE_POINT_RETENTION:]:
            shutil.rmtree(old_dir)
            logger.info(f"Pruned old backup: {old_dir.name}")


    @classmethod
    def _data_changed(cls, temp_path: Path) -> bool:
        committed = sorted(
            (d for d in config.RESTORE_POINTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: d.name,
            reverse=True,
        )
        if not committed:
            return True
        latest = committed[0]

        def file_hash(path: Path) -> str:
            h = hashlib.md5()
            h.update(path.read_bytes())
            return h.hexdigest()

        temp_files = {f.relative_to(temp_path) for f in temp_path.rglob("*") if f.is_file()}
        latest_files = {f.relative_to(latest) for f in latest.rglob("*") if f.is_file()}
        if temp_files != latest_files:
            return True
        return any(file_hash(temp_path / rel) != file_hash(latest / rel) for rel in temp_files)


    @classmethod
    def create_restore_point(cls):
        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H.%M.%S")
        temp_path = config.RESTORE_POINTS_DIR / f".tmp_{timestamp}"
        logger.info(f"Starting backup: {timestamp}")
        try:
            dbs = cls._get_databases_to_create()
        except Exception as e:
            logger.error(f"Failed to retrieve database list for backup: {e}")
            return
        failures: list[str] = []
        for db in dbs:
            try:
                tables = cls._get_tables(db)
            except Exception as e:
                logger.error(f"Failed to retrieve tables for database {db}: {e}")
                failures.append(db)
                continue
            for table in tables:
                logger.info(f"Exporting {table.database}.{table.schema}.{table.name}...")
                try:
                    cls.export_table_to_csv(table, temp_path)
                    logger.info(f"Exported {table.database}.{table.schema}.{table.name}")
                except Exception as e:
                    logger.error(f"Failed to export {table.database}.{table.schema}.{table.name}: {e}")
                    failures.append(f"{table.database}.{table.schema}.{table.name}")
        if not cls._data_changed(temp_path):
            shutil.rmtree(temp_path)
            logger.info("No data changes detected — skipping restore point")
            return
        final_path = config.RESTORE_POINTS_DIR / timestamp
        temp_path.rename(final_path)
        if failures:
            logger.warning(f"Backup created with {len(failures)} failure(s): {failures}")
        else:
            logger.info("Backup complete.")
        cls._prune_restore_points()


    @classmethod
    def resolve_load_order(cls):
        cls._load_object_dependencies()
        return cls._get_project_load_order()
    
    
    @classmethod
    def _load_object_mapping(cls) -> dict[str, type[DatabaseObject]]:
        object_mapping:dict = {}
        
        for db in config.SQL_SCRIPTS_DIR.iterdir():
            if not db.is_dir():
                continue

            for obj_type in db.iterdir():
                if not obj_type.is_dir() or obj_type.name == 'post-init':
                    continue

                for obj in obj_type.iterdir():
                    if not obj.is_file() or obj.suffix != '.sql':
                        continue

                    object_mapping[obj.stem] = DatabaseObject(script_path=obj)
        cls._object_mapping = object_mapping
        return cls._object_mapping
    

    _REF_TERMINATORS = (' ', '\n', '\t', '\r', ',', '(', ')', ';')

    @classmethod
    def _pattern_in(cls, pattern: str, definition: str) -> bool:
        """Check if pattern appears in definition.
        For patterns ending with a space (unbracketed names), also check other valid
        SQL terminators so references at end-of-line or before punctuation are detected.
        """
        if not pattern.endswith(' '):
            return pattern in definition
        base = pattern[:-1]
        return definition.endswith(base) or any(f"{base}{t}" in definition for t in cls._REF_TERMINATORS)

    @classmethod
    def _load_object_dependencies(cls):
        """ Dependents are the objects that depend on the current object.  """
        cls._load_object_mapping()

        objects:list[DatabaseObject] = list(cls._object_mapping.values())

        for obj in objects:

            for other_obj in objects:

                if other_obj == obj:
                    continue

                match obj.schema:
                    case 'dbo':
                        patterns = [f"{obj.schema}.{obj.name} ", f"{obj.name} ", f"[{obj.schema}].[{obj.name}]", f"[{obj.name}]"]
                    case None:
                        patterns = [f"{obj.name} ", f"[{obj.name}]"]
                    case _:
                        patterns = [f"{obj.schema}.{obj.name} ", f"[{obj.schema}].[{obj.name}]"]

                for pattern in patterns:
                    if cls._pattern_in(pattern, other_obj.definition):
                        obj.add_dependent(other_obj)
                        break

                match other_obj.schema:
                    case 'dbo':
                        other_patterns = [f"{other_obj.schema}.{other_obj.name} ", f"{other_obj.name} ", f"[{other_obj.schema}].[{other_obj.name}]", f"[{other_obj.name}]"]
                    case None:
                        other_patterns = [f"{other_obj.name} ", f"[{other_obj.name}]"]
                    case _:
                        other_patterns = [f"{other_obj.schema}.{other_obj.name} ", f"[{other_obj.schema}].[{other_obj.name}]"]

                for other_pattern in other_patterns:
                    if cls._pattern_in(other_pattern, obj.definition):
                        obj.add_dependency(other_obj)
                        break

        for obj in objects:
            if obj.schema is not None:
                schema_obj = cls._object_mapping.get(obj.schema)
                if schema_obj is not None and schema_obj.type == 'schema':
                    obj.add_dependency(schema_obj)


    @classmethod
    def _get_project_load_order(cls) -> list[DatabaseObject]:
        # Algorithm is:
        # For every node, starting at any arbitrary node in the global list of nodes:,
        # if their dependencies are not in the order, push them to the end of the list
        # ALLOWABLE INSERT LIST: THe list of all nodes that can be travelled too given the current start
        # Given start of load order, which nodes are completed and insertable

        cls._load_object_dependencies()
        objects:list[DatabaseObject] = list(cls._object_mapping.values())
        load_order:list[DatabaseObject] = []

        def _get_insertable_nodes() -> list[DatabaseObject]:
            insertable = []
            for obj in objects:
                if obj in load_order:
                    continue
                if all(dep in load_order for dep in obj.dependencies):
                    insertable.append(obj)

            return insertable
        
        
        while len(load_order) < len(objects):
            insertable = _get_insertable_nodes()
            if not insertable:
                stuck = [obj for obj in objects if obj not in load_order]
                raise ValueError(f"Circular dependency detected — cannot determine load order for: {stuck}")
            load_order.extend(insertable)

        return load_order


    def __init__(self):
        pass


from .mssql import MicrosoftSQLServer
from .postgres import Postgres

mapping = {
    "mssql": MicrosoftSQLServer,
    "postgresql": Postgres
}
