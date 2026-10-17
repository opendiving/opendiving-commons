import sys
from pathlib import Path

# `scripts/` is build tooling, not a package: the scripts import each other by name, as they
# do when run as `python scripts/<name>.py`, and the tests import them the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
