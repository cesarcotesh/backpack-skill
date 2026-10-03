"""Entry point for the skill: python run.py <command> [options]. See SKILL.md."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backpack.__main__ import main  # noqa: E402

sys.exit(main())
