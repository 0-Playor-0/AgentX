"""Phase 0 checks on competition data: pandas groupbys only, no model training.
Writes folds.npy (SKF 5, shuffle, rs=42 = the scheme the public OOF libraries use) and prints one line per check."""
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

import os
D, A = os.environ.get("S6_DATA", "data"), os.environ.get("S6_ART", "artifacts"); os.makedirs(A, exist_ok=True)
T = "satisfaction"
tr = pd.read_csv(f"{D}/comp/train.csv"); te = pd.read_csv(f"{D}/comp/test.csv")
o = pd.concat([pd.read_csv(f"{D}/orig/{f}.csv") for f in ("train", "test")])
y = tr[T].astype(str).str.lower().isin(["true", "1", "satisfied"]).astype(int).values
folds = np.zeros(len(tr), int)
for k, (_, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(tr, y)):
    folds[va] = k
np.save(f"{A}/folds.npy", folds)

def oof_te(keys, a=20):
    """Fold-safe smoothed target mean; returns OOF AUC of the encoding alone."""
    key = tr[keys].astype(str).agg("|".join, axis=1) if isinstance(keys, list) else tr[keys].astype(str)
    p, prior = np.zeros(len(tr)), y.mean()
    for k in range(5):
        m = folds != k
        g = pd.DataFrame({"k": key[m], "y": y[m]}).groupby("k")["y"].agg(["sum", "count"])
        enc = (g["sum"] + a * prior) / (g["count"] + a)
        p[~m] = key[~m].map(enc).fillna(prior).values
    return roc_auc_score(y, p)

fd = tr["Flight Distance"]; vc = fd.value_counts()
rat = [c for c in tr.columns if pd.api.types.is_numeric_dtype(tr[c]) and c not in ("id", T, "Age", "Flight Distance")
       and "Delay" not in c]
print(f"shape train={tr.shape} test={te.shape} pos={y.mean():.4f} na={tr.isna().sum().sum()} cols_match_orig="
      f"{set(tr.columns) - {'id'} <= set(o.columns)}")
print(f"FD unique={fd.nunique()} median_count={vc.median():.0f} rows_on_FD_count>=20={vc[vc>=20].sum()/len(tr):.3f} "
      f"test_FD_seen={te['Flight Distance'].isin(set(fd)).mean():.4f} FD_in_orig={fd.isin(set(o['Flight Distance'])).mean():.4f} "
      f"FD_nonint={(fd % 1 != 0).mean():.4f}")
print(f"ratings nonint_share={max((tr[c] % 1 != 0).mean() for c in rat):.4f} max_levels={max(tr[c].nunique() for c in rat)} n={len(rat)}")
print("TE_AUC " + " ".join(f"{n}={oof_te(k):.5f}" for n, k in [
    ("FD", "Flight Distance"), ("Age", "Age"), ("FDxClass", ["Flight Distance", "Class"]),
    ("FDxToT", ["Flight Distance", "Type of Travel"]), ("Class", "Class"), ("wifi", "Inflight wifi service")]))
# route profile: how much route-level shares vary vs. what random grouping of the same sizes would give
cls = (tr["Class"] == "Business").astype(float)
r = cls.groupby(fd).transform("mean"); rs = cls.groupby(np.random.default_rng(0).permutation(fd.values)).transform("mean")
print(f"route_profile Business_share_std route={r.std():.4f} shuffled={rs.std():.4f} corr(route_share,y)={np.corrcoef(r, y)[0,1]:.4f}")
print(f"orig pos={(o[T]=='satisfied').mean():.4f} vs comp {y.mean():.4f}; exact-dup comp rows in orig="
      f"{tr.drop(columns=['id',T]).merge(o.drop(columns=[c for c in o.columns if c in ('id','Unnamed: 0',T)]).drop_duplicates(), how='inner').shape[0]}")
