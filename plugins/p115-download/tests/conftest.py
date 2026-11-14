from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
PLUGIN_ROOT = HERE.parents[1]        # plugins/p115-download
KIT_ROOT = HERE.parents[3]           # movieclaw-kit

sys.path.insert(0, str(PLUGIN_ROOT))
_MC = os.environ.get("MOVIECLAW_SRC") or str(KIT_ROOT.parent / "MovieClaw" / "src")
sys.path.insert(0, _MC)
sys.path.insert(0, str(HERE.parent))
