"""Shared paths, labels, folds and experiment logging. Every model uses the same folds.npy."""
import csv, json, os
from pathlib import Path
import numpy as np
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("S6_DATA", ROOT / "data"))          # comp/, orig/, public_oof/
ART = Path(os.environ.get("S6_ART", ROOT / "artifacts"))        # oof/, test/, ckpt/, experiments.csv
T = "satisfaction"
N_TRAIN, N_TEST = 699_635, 299_844


def labels():
    import pandas as pd
    tr = pd.read_csv(DATA / "comp/train.csv", usecols=["id", T])
    te = pd.read_csv(DATA / "comp/test.csv", usecols=["id"])
    y = tr[T].astype(str).str.lower().isin(["true", "1", "satisfied"]).astype(np.int8).to_numpy()
    return tr["id"].to_numpy(), y, te["id"].to_numpy()


def folds(y, save=True):
    """SKF(5, shuffle, 42): the split used by the public OOF libraries. Cached in folds.npy."""
    p = ART / "folds.npy"
    if p.exists():
        f = np.load(p)
        if len(f) == len(y):
            return f
    f = np.zeros(len(y), np.int8)
    for k, (_, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(np.zeros(len(y)), y)):
        f[va] = k
    if save:
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(p, f)
    return f


def log_exp(exp, features, model, per_fold, notes):
    p = ART / "experiments.csv"
    new = not p.exists()
    with open(p, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["exp", "features", "model", "cv_mean", "cv_std", "per_fold", "notes"])
        w.writerow([exp, features, model, f"{np.mean(per_fold):.6f}", f"{np.std(per_fold):.6f}",
                    json.dumps([round(float(a), 6) for a in per_fold]), notes])


def save_preds(exp, oof, test):
    for d, a in (("oof", oof), ("test", test)):
        (ART / d).mkdir(parents=True, exist_ok=True)
        np.save(ART / d / f"{exp}.npy", a.astype(np.float32))
