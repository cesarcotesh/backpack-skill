# Fixture trap: if anything ever executes this file, it leaves a marker next to it.
from pathlib import Path

(Path(__file__).parent / "EXECUTED.marker").write_text("this script must never run")
