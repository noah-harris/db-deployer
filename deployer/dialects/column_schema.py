from dataclasses import dataclass

@dataclass
class ColumnSchema:
    name: str
    db_type: str  # canonical type name from the DB (lowercased)
    nullable: bool
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    char_length: int | None = None
