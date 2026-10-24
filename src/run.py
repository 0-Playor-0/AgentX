"""Entry point: python src/run.py --exp <name>  (reads configs/<name>.yaml; 'module' picks the runner)."""
import argparse, importlib, sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent))
ap = argparse.ArgumentParser()
ap.add_argument("--exp", required=True)
a = ap.parse_args()
cfg = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "configs" / f"{a.exp}.yaml"))
importlib.import_module(cfg["module"]).main(cfg, a.exp)
