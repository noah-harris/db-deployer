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
