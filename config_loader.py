import tomllib
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent / "config"

def load_toml(name: str):
    """
    Loads a TOML config file from the config directory.
    """
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"TOML config not found: {path}")

    with open(path, "rb") as f:
        return tomllib.load(f)

SCHEMA_FILE = Path(__file__).resolve().parent / "config" / "input_table.toml"

def load_farm_schema():
    with open(SCHEMA_FILE, "rb") as f:
        data = tomllib.load(f)
    return data["columns"]
