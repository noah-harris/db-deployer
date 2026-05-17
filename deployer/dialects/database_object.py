from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from config import SQL_SCRIPTS_DIR
# Z:\Repositories\ledgr\database\db\type\schema.name.sql


@dataclass
class DatabaseObject:
    script_path:Path
    dependents:set["DatabaseObject"]=field(default_factory=set)
    dependencies:set["DatabaseObject"]=field(default_factory=set)

    # The script path format is the following
    # project/database/type/schema.name.sql for all types except schema, which is project/database/schema/name.sql
    # Thus we work backwards from the filename to get the name, schema, type, and database. We also read the file contents to get the definition which we will use for dependency parsing later.

    @cached_property
    def database(self) -> str:
        self.script_path.relative_to(SQL_SCRIPTS_DIR)
        return self.script_path.parts[-3]
    
    @cached_property
    def schema(self) -> str | None:
        if self.type == 'schema':
            return None
        return self.script_path.stem.split('.', 1)[0]

    @property
    def name(self) -> str:
        if self.type == 'schema':
            return self.script_path.stem
        return self.script_path.stem.split('.', 1)[1]

    @cached_property
    def type(self) -> str:
        return self.script_path.parts[-2]

    @cached_property
    def definition(self) -> str:

        def __strip_comments(sql:str) -> str:
            """Remove SQL comments from a string.
            This function removes both single-line comments (starting with --) and multi-line comments (enclosed in /* */).
            Args:
                sql (str): The input SQL string.
            Returns:
                str: The SQL string with comments removed.
            """
            import re
            sql_no_single_comments = re.sub(r'--.*', '', sql)
            sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_single_comments, flags=re.DOTALL)
            return sql_no_comments

        raw = self.script_path.read_bytes()
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            enc = "utf-16"
        elif raw[:3] == b"\xef\xbb\xbf":
            enc = "utf-8-sig"
        else:
            enc = "utf-8"
        with open(self.script_path, "r", encoding=enc) as f:
            obj_definition = f.read()
        return __strip_comments(obj_definition)
    
    def __repr__(self):
        if self.type == 'schema':
            return f"{self.database}.{self.name} ({self.type})"
        return f"{self.database}.{self.schema}.{self.name} ({self.type})"
    
    def __eq__(self, value):
        if not isinstance(value, DatabaseObject):
            return False
        return (
            self.database == value.database and
            self.schema == value.schema and
            self.name == value.name and
            self.type == value.type
        )
    
    def __hash__(self):
        return hash((self.database, self.schema, self.name, self.type))
    
    def add_dependent(self, dependent:"DatabaseObject"):
        self.dependents.add(dependent)

    def add_dependency(self, dependency:"DatabaseObject"):
        self.dependencies.add(dependency)