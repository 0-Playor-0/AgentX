"""Entry point: python src/run.py --exp <name>  (reads configs/<name>.yaml; 'module' picks the runner).
A config may set `base: <other>` to inherit that config and override keys."""
import argparse, importlib, sys
from pathlib import Path
import yaml

CONF = Path(__file__).resolve().parents[1] / "configs"
sys.path.insert(0, str(Path(__file__).parent))


def load(name):
    cfg = yaml.safe_load(open(CONF / f"{name}.yaml"))
    return {**load(cfg.pop("base")), **cfg} if "base" in cfg else cfg


ap = argparse.ArgumentParser()
ap.add_argument("--exp", required=True)
a = ap.parse_args()
cfg = load(a.exp)
importlib.import_module(cfg["module"]).main(cfg, a.exp)
