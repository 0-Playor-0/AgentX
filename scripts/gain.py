"""One line: nested-CV gain of <exp> over the stack named in artifacts/e1_pick.txt, and the keep decision.
  python scripts/gain.py --exp e1c_stack_e2 [--min-gain 0.00003]"""
import argparse, ast, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import ART, read_log

ap = argparse.ArgumentParser()
ap.add_argument("--exp", required=True); ap.add_argument("--min-gain", type=float, default=0.00003)
a = ap.parse_args()
L, base = read_log(), (ART / "e1_pick.txt").read_text().strip()
fb, fe = [ast.literal_eval(L.at[x, "per_fold"]) for x in (base, a.exp)]
g = L.at[a.exp, "cv_mean"] - L.at[base, "cv_mean"]
up = sum(e > b for b, e in zip(fb, fe))
print(f"[gain] {a.exp} vs {base}: {L.at[base, 'cv_mean']:.6f} -> {L.at[a.exp, 'cv_mean']:.6f} gain={g:+.6f} "
      f"folds_up={up}/5 keep={g >= a.min_gain}")
