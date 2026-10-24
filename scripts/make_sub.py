"""Build + validate one submission file. Never submits.
  python scripts/make_sub.py --pick-e1        # applies the E1a/E1b rule, then builds the honest stack's file
  python scripts/make_sub.py --exp e1b_stack
"""
import argparse, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import ART, DATA, read_log

ap = argparse.ArgumentParser()
ap.add_argument("--exp"); ap.add_argument("--pick-e1", action="store_true")
ap.add_argument("--es-margin", type=float, default=0.00005)
a = ap.parse_args()
log = read_log()

if a.pick_e1:
    ca, cb = log.at["e1a_stack", "cv_mean"], log.at["e1b_stack", "cv_mean"]
    a.exp = "e1b_stack" if ca - cb > a.es_margin else "e1a_stack"
    (ART / "e1_pick.txt").write_text(a.exp + "\n")             # read by cell 7 (run.py --base-from)
    print(f"[pick] E1a={ca:.6f} E1b={cb:.6f} diff={ca - cb:+.6f} margin={a.es_margin} -> honest={a.exp} (saved to e1_pick.txt)")

p = np.load(ART / "test" / f"{a.exp}.npy").astype(np.float64)
ss = pd.read_csv(DATA / "comp/sample_submission.csv")
te_ids = pd.read_csv(DATA / "comp/test.csv", usecols=["id"])["id"].to_numpy()
checks = {
    "rows": len(p) == len(ss) == 299_844,
    "ids": np.array_equal(ss["id"].to_numpy(), te_ids),
    "cols": list(ss.columns) == ["id", "satisfaction"],
    "finite": bool(np.isfinite(p).all()),
    "in_0_1": bool(p.min() >= 0 and p.max() <= 1),
    "non_constant": bool(p.std() > 1e-6 and len(np.unique(p)) > 1000),
}
bad = [k for k, v in checks.items() if not v]
cv = log.at[a.exp, "cv_mean"]
if bad:
    sys.exit(f"[sub] {a.exp} INVALID: {bad}")
out = ART / "submissions" / f"{a.exp}.csv"
out.parent.mkdir(parents=True, exist_ok=True)
pd.DataFrame({"id": ss["id"], "satisfaction": p}).to_csv(out, index=False, float_format="%.8f")
print(f"[sub] {a.exp} OK ({', '.join(checks)}) cv={cv:.6f} expected_public={cv - 0.0005:.5f}..{cv - 0.0003:.5f} "
      f"-> {out}  (NOT submitted)")
