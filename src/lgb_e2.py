"""E2: own LightGBM on our folds. Feature groups (toggle in config `groups`):
  base    raw columns, the 4 categoricals as category dtype
  route   Flight Distance = route id: count + per-route mean of Age/ratings/delays + per-route share of each
          categorical level, over train+test feature rows (no labels)
  teacher logit of an LGBM trained only on the original dataset (no competition labels)
  te      smoothed target encoding of FD, Age, FD x Class, FD x Type of Travel: fit on outer-train rows only,
          inner 5-fold OOF for the outer-train rows themselves
Early stopping uses a 5% stratified split of the outer-train rows, never the scored fold.
"""
import json
import lightgbm as lgb
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from common import ART, DATA, T, folds, log_exp, save_preds

CATS = ["Gender", "Customer Type", "Type of Travel", "Class"]
FD = "Flight Distance"


def _load(cfg):
    tr, te = pd.read_csv(DATA / "comp/train.csv"), pd.read_csv(DATA / "comp/test.csv")
    if cfg.get("smoke_rows"):
        tr, te = tr.iloc[: cfg["smoke_rows"]].copy(), te.iloc[: cfg["smoke_rows"] // 2].copy()
    y = tr[T].astype(str).str.lower().isin(["true", "1", "satisfied"]).astype(np.int8).to_numpy()
    orig = pd.concat([pd.read_csv(DATA / f"orig/{f}.csv") for f in ("train", "test")], ignore_index=True)
    return tr.drop(columns=[T]), te, y, orig


def _cat(df, levels):
    for c in CATS:
        df[c] = pd.Categorical(df[c].astype(str), categories=levels[c])
    return df


def route_features(allx):
    num = [c for c in allx.columns if c not in CATS + ["id", FD]]
    g = allx.groupby(FD)
    out = pd.DataFrame({"route_count": g[FD].transform("size")}, index=allx.index)
    for c in num:
        out[f"route_mean_{c}"] = g[c].transform("mean")
    for c in CATS:
        for v in sorted(allx[c].astype(str).unique())[:-1]:     # last level is implied
            out[f"route_share_{c}_{v}"] = (allx[c].astype(str) == v).groupby(allx[FD]).transform("mean")
    return out


def teacher_feature(allx, orig, cfg):
    cols = [c for c in allx.columns if c != "id" and c in orig.columns]
    yo = (orig[T] == "satisfied").astype(int).to_numpy()
    levels = {c: sorted(orig[c].astype(str).unique()) for c in CATS}
    Xo, Xa = _cat(orig[cols].copy(), levels), _cat(allx[cols].copy(), levels)
    m = lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=50,
                       feature_fraction=0.8, verbose=-1, seed=42, num_threads=cfg.get("threads", -1)),
                  lgb.Dataset(Xo, yo), num_boost_round=cfg.get("teacher_rounds", 600))
    return pd.Series(m.predict(Xa, raw_score=True), index=allx.index, name="teacher_logit")


def _te_map(keys, y, m):
    prior = y.mean()
    g = pd.DataFrame({"k": keys, "y": y}).groupby("k")["y"].agg(["sum", "count"])
    return (g["sum"] + m * prior) / (g["count"] + m), prior


def te_block(K_tr, y_tr, K_apply, m, seed):
    """K_*: DataFrame of string keys. Returns (train-row OOF encodings, apply-row encodings)."""
    enc_tr = np.zeros((len(K_tr), K_tr.shape[1]), np.float32)
    enc_ap = np.zeros((len(K_apply), K_tr.shape[1]), np.float32)
    for j, c in enumerate(K_tr.columns):
        mp, prior = _te_map(K_tr[c].to_numpy(), y_tr, m)
        enc_ap[:, j] = K_apply[c].map(mp).fillna(prior).to_numpy()
        for itr, iva in StratifiedKFold(5, shuffle=True, random_state=seed).split(K_tr, y_tr):
            mp_i, pr_i = _te_map(K_tr[c].to_numpy()[itr], y_tr[itr], m)
            enc_tr[iva, j] = K_tr[c].iloc[iva].map(mp_i).fillna(pr_i).to_numpy()
    return enc_tr, enc_ap


def main(cfg, exp):
    tr, te, y, orig = _load(cfg)
    f = folds(y, save=not cfg.get("smoke_rows"))
    groups = cfg["groups"]
    allx = pd.concat([tr, te], ignore_index=True)
    levels = {c: sorted(allx[c].astype(str).unique()) for c in CATS}
    parts = [_cat(allx.drop(columns=["id"]).copy(), levels)]
    if "route" in groups:
        parts.append(route_features(allx))
    if "teacher" in groups:
        parts.append(teacher_feature(allx, orig, cfg).to_frame())
    X = pd.concat(parts, axis=1)
    n = len(tr)
    Xtr, Xte = X.iloc[:n].reset_index(drop=True), X.iloc[n:].reset_index(drop=True)
    te_keys = pd.DataFrame({"te_FD": allx[FD].astype(str), "te_Age": allx["Age"].astype(str),
                            "te_FDxClass": allx[FD].astype(str) + "|" + allx["Class"].astype(str),
                            "te_FDxToT": allx[FD].astype(str) + "|" + allx["Type of Travel"].astype(str)})
    Ktr, Kte = te_keys.iloc[:n].reset_index(drop=True), te_keys.iloc[n:].reset_index(drop=True)
    params = dict(objective="binary", metric="auc", verbose=-1, seed=42, num_threads=cfg.get("threads", -1),
                  **cfg["params"])
    oof, tst, info = np.zeros(n), np.zeros(len(Xte)), []
    ck = ART / "ckpt" / exp
    ck.mkdir(parents=True, exist_ok=True)
    for k in range(cfg.get("n_folds_run", 5)):
        p = ck / f"fold{k}.npz"
        if p.exists():                                          # resume: skip finished folds
            z = np.load(p, allow_pickle=False)
            oof[f == k] = z["va"]; tst += z["te"] / cfg.get("n_folds_run", 5); info.append(json.loads(str(z["info"]))); continue
        tri, vai = np.where(f != k)[0], np.where(f == k)[0]
        A, V, E = Xtr.iloc[tri].copy(), Xtr.iloc[vai].copy(), Xte.copy()
        if "te" in groups:
            e_tr, e_ap = te_block(Ktr.iloc[tri], y[tri], pd.concat([Ktr.iloc[vai], Kte]), cfg["te_smooth"], 42 + k)
            for j, c in enumerate(Ktr.columns):
                A[c], V[c], E[c] = e_tr[:, j], e_ap[: len(vai), j], e_ap[len(vai):, j]
        fit, es = train_test_split(np.arange(len(tri)), test_size=0.05, stratify=y[tri], random_state=42 + k)
        m = lgb.train(params, lgb.Dataset(A.iloc[fit], y[tri][fit]), num_boost_round=cfg["rounds"],
                      valid_sets=[lgb.Dataset(A.iloc[es], y[tri][es])],
                      callbacks=[lgb.early_stopping(cfg["es_rounds"], verbose=False)])
        va_p, te_p = m.predict(V, num_iteration=m.best_iteration), m.predict(E, num_iteration=m.best_iteration)
        inf = dict(fold=k, auc=roc_auc_score(y[vai], va_p), iters=m.best_iteration)
        np.savez(p, va=va_p, te=te_p, info=json.dumps(inf))
        oof[vai] = va_p; tst += te_p / cfg.get("n_folds_run", 5); info.append(inf)
        print(f"[{exp}] fold {k} auc={inf['auc']:.6f} iters={inf['iters']}", flush=True)
    pf = [i["auc"] for i in info]
    nfeat = Xtr.shape[1] + (4 if "te" in groups else 0)
    if not cfg.get("smoke_rows"):
        save_preds(exp, oof, tst)
    log_exp(exp, "+".join(groups) + f" ({nfeat} feats)", "lgbm cpu", pf, f"iters={[i['iters'] for i in info]}")
    print(f"[{exp}] cv={np.mean(pf):.6f}±{np.std(pf):.6f} folds={[round(a, 5) for a in pf]} "
          f"iters={[i['iters'] for i in info]} feats={nfeat} groups={'+'.join(groups)}", flush=True)
