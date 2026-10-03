# The package lives inside the skill folder so the skill installs self-contained.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit"))
