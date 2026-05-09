from dataclasses import dataclass
from pathlib import Path

@dataclass
class DatabaseObject:
    database:str
    schema:str
    name:str
    type:str
    script_path:Path
    definition:str