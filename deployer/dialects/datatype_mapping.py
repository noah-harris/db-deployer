INTEGER_TYPES = {
    # Postgres
    "smallint", "integer", "bigint", "int2", "int4", "int8",
    # MSSQL
    "tinyint", "int",
}
DECIMAL_TYPES = {"numeric", "decimal", "money", "smallmoney"}
FLOAT_TYPES = {"real", "double precision", "float", "float4", "float8"}
BOOL_TYPES = {"boolean", "bool", "bit"}
DATE_TYPES = {"date"}
TIMESTAMP_TYPES = {"timestamp", "timestamp without time zone", "datetime", "datetime2", "smalldatetime"}
TIMESTAMPTZ_TYPES = {"timestamp with time zone", "timestamptz", "datetimeoffset"}
TIME_TYPES = {"time", "time without time zone", "time with time zone"}
BINARY_TYPES = {"bytea", "varbinary", "binary", "image"}


def pandas_dtype_for(db_type:str) -> str:
    """
    Return the pandas dtype to coerce this column to AFTER reading from SQL.
    We use nullable extension dtypes so NULL is preserved without float upcast.

    Decimals/floats stay as 'object' because we cast them to text in the query;
    we'll convert them to Decimal/float in Python explicitly.
    """
    if db_type in INTEGER_TYPES:
        return "Int64"  # nullable integer
    if db_type in DECIMAL_TYPES:
        return "object"  # will hold Decimal
    if db_type in FLOAT_TYPES:
        return "object"  # will hold float, parsed from text
    if db_type in BOOL_TYPES:
        return "boolean"  # nullable boolean
    if db_type in BINARY_TYPES:
        return "object"  # bytes
    # Dates and strings: leave as object for now; we handle conversion explicitly.
    return "object"
