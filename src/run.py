"""Entry point: python src/run.py --exp <name>  (reads configs/<name>.yaml; 'module' picks the runner).
A config may set `base: <other>` to inherit that config and override keys; `--base-from <file>` replaces
that base with the config name stored in the file (e.g. artifacts/e1_pick.txt)."""
import argparse, importlib, sys
from pathlib import Path
import yaml

CONF = Path(__file__).resolve().parents[1] / "configs"
sys.path.insert(0, str(Path(__file__).parent))


def load(name, base=None):
    cfg = yaml.safe_load(open(CONF / f"{name}.yaml"))
    if base:
        cfg["base"] = base
    return {**load(cfg.pop("base")), **cfg} if "base" in cfg else cfg


ap = argparse.ArgumentParser()
ap.add_argument("--exp", required=True)
ap.add_argument("--base-from")
a = ap.parse_args()
base = Path(a.base_from).read_text().strip() if a.base_from else None
if base:
    print(f"[{a.exp}] base={base} (from {a.base_from})", flush=True)
cfg = load(a.exp, base)
importlib.import_module(cfg["module"]).main(cfg, a.exp)
