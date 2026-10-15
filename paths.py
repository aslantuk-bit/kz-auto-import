"""Где лежат данные. В собранном приложении KZAI_HOME указывает на Application Support."""
import os
from pathlib import Path

HOME = Path(os.environ.get("KZAI_HOME") or Path(__file__).resolve().parent)
RAW = HOME / "sources" / "raw"
OUT = HOME / "out"
PORT = 8790
