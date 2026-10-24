"""E1: honest stack over public OOF libraries (+ optional own members).

Filters (logged in one line): invalid, stack-level names, OOF AUC > auc_max, OOF−LB gap > lb_gap_max
(only where the member's public LB is known), test-vs-OOF distribution mismatch (KS), rank-corr dedupe.
Stacker: L2 logistic regression on logits. Inside each outer fold, members are ranked by AUC on the
outer-train rows and (top-k, C) are chosen by inner CV on those rows only; the outer 5 folds only report.
Sanity baseline: rank-average of top-k, k chosen on the outer-train rows.
"""
import hashlib, json, re
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import ks_2samp, rankdata
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from common import ART, DATA, folds, labels, log_exp, save_preds


def _logit_pair(o, t):
    o, t = np.asarray(o, np.float64).ravel(), np.asarray(t, np.float64).ravel()
    if not (o.min() < 0 or o.max() > 1 or t.min() < 0 or t.max() > 1):   # probabilities -> logits
        o, t = [np.log(np.clip(a, 1e-7, 1 - 1e-7) / (1 - np.clip(a, 1e-7, 1 - 1e-7))) for a in (o, t)]
    return np.clip(o, -30, 30).astype(np.float32), np.clip(t, -30, 30).astype(np.float32)


def _by_id(df, ids, col):
    return df.set_index("id")[col].reindex(ids).to_numpy()


def load_members(root, tr_ids, te_ids):
    """Walk root/<source>/ and collect (oof, test) pairs in any of the formats the libraries use."""
    out, skipped = {}, []
    meta_cols = {"id", "fold", "satisfaction", "target", "y"}
    for src in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        def add(name, o, t):
            out[f"{src.name}:{name}"] = (o, t)
        for f in sorted(src.rglob("oof_*.npy")):
            t = f.with_name("test_" + f.name[4:])
            if t.exists():
                add(f.stem[4:], np.load(f, allow_pickle=False), np.load(t, allow_pickle=False))
            else:
                skipped.append(f.name)
        for f in sorted(src.rglob("*.npz")):
            z = np.load(f, allow_pickle=False)
            if {"oof", "test"} <= set(z.files):
                add(f.stem, z["oof"], z["test"])
        for f in sorted(src.rglob("*_oof.csv")):
            t = f.with_name(f.name[:-8] + "_test.csv")
            if not t.exists():
                skipped.append(f.name); continue
            o, te = pd.read_csv(f), pd.read_csv(t)
            c = [x for x in o.columns if x.lower() not in meta_cols][-1]
            ct = [x for x in te.columns if x.lower() not in meta_cols][-1]
            add(f.name[:-8], _by_id(o, tr_ids, c), _by_id(te, te_ids, ct))
        for f in sorted(src.rglob("oof_*.parquet")):
            t = f.with_name("test_" + f.name[4:])
            if not t.exists():
                skipped.append(f.name); continue
            o, te = pd.read_parquet(f), pd.read_parquet(t)
            for c in o.columns:
                if c.lower() not in meta_cols and c in te.columns and np.issubdtype(o[c].dtype, np.number):
                    add(f"{f.stem[4:]}.{c}", _by_id(o, tr_ids, c), _by_id(te, te_ids, c))
    return out, skipped


def filter_members(raw, y, cfg, rng):
    drop = {k: 0 for k in ("invalid", "stack_level", "auc_hi", "lb_gap", "ks", "dup")}
    lb_known, keep, all_ks = 0, [], []
    excl = re.compile(cfg["exclude_regex"], re.I)
    lb_map = [(re.compile(k, re.I), v) for k, v in (cfg.get("lb") or {}).items()]
    sub = rng.choice(len(y), min(len(y), 200_000), replace=False)
    for name, (o, t) in raw.items():
        o, t = np.asarray(o, np.float64).ravel(), np.asarray(t, np.float64).ravel()
        if excl.search(name.split(":", 1)[1]):
            drop["stack_level"] += 1; continue
        if len(o) != len(y) or not np.isfinite(o).all() or not np.isfinite(t).all() or len(np.unique(o[sub[:5000]])) < 50:
            drop["invalid"] += 1; continue
        o, t = _logit_pair(o, t)
        auc = roc_auc_score(y, o)
        if auc > cfg["auc_max"]:
            drop["auc_hi"] += 1; continue
        lb = next((v for r, v in lb_map if r.search(name)), None)
        if lb is not None:
            lb_known += 1
            if auc - lb > cfg["lb_gap_max"]:
                drop["lb_gap"] += 1; continue
        # KS is invariant to monotone maps, so this equals KS on joint ranks of OOF vs test
        ks = ks_2samp(o[sub], t[rng.choice(len(t), min(len(t), 200_000), replace=False)]).statistic
        all_ks.append(ks)
        if ks > cfg["ks_max"]:
            drop["ks"] += 1; continue
        keep.append((auc, name, o, t, ks))
    keep.sort(key=lambda r: -r[0])
    ranks, kept = [], []                       # greedy dedupe on Spearman (pearson of ranks on a row sample)
    for r in keep:
        z = rankdata(r[2][sub]).astype(np.float32); z = (z - z.mean()) / z.std()
        if ranks and max(float(z @ q) / len(z) for q in ranks) > cfg["dedupe_corr"]:
            drop["dup"] += 1; continue
        ranks.append(z); kept.append(r)
    return kept, drop, lb_known, np.percentile(all_ks, [50, 95]) if all_ks else [0, 0]


def _pct(a):
    return (rankdata(a) - 0.5) / len(a)


def _lr(C):
    return LogisticRegression(C=C, max_iter=1000, tol=1e-6, warm_start=True)


def nested_stack(X, XT, y, f, forced, cfg, ckdir):
    """X/XT: logits (n, m) with columns pre-sorted by full-data AUC only for storage; selection redone per fold."""
    n_in, Cs, Ks, RKs = cfg["inner_folds"], sorted(cfg["C_grid"]), cfg["k_grid"], cfg["rank_k_grid"]
    oof, oof_r = np.zeros(len(y)), np.zeros(len(y))
    tst, tst_r, info = np.zeros(len(XT)), np.zeros(len(XT)), []
    m = X.shape[1]
    for k in range(5):
        ck = ckdir / f"fold{k}.npz"
        if ck.exists():                                         # resume: skip finished folds
            z = np.load(ck, allow_pickle=False)
            oof[f == k], oof_r[f == k] = z["va"], z["va_r"]
            tst += z["te"] / 5; tst_r += z["te_r"] / 5; info.append(json.loads(str(z["info"]))); continue
        tr, va = np.where(f != k)[0], np.where(f == k)[0]
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        Z = lambda rows, cols: (X[np.ix_(rows, cols)] - mu[cols]) / sd[cols]
        free = [j for j in range(m) if j not in forced]
        order = forced + sorted(free, key=lambda j: -roc_auc_score(y[tr], X[tr, j]))
        best = (-1, None, None)
        inner = list(StratifiedKFold(n_in, shuffle=True, random_state=7).split(tr, y[tr]))
        for kk in sorted({min(x, m) for x in Ks} | ({m} if cfg.get("k_all", True) else set())):
            cols = order[:kk]
            sc = np.zeros(len(Cs))
            for itr, iva in inner:
                a, b = tr[itr], tr[iva]
                lr = _lr(Cs[0]); Za, Zb = Z(a, cols), Z(b, cols)
                for ci, C in enumerate(Cs):                     # warm-started C path
                    lr.set_params(C=C); lr.fit(Za, y[a])
                    sc[ci] += roc_auc_score(y[b], lr.decision_function(Zb)) / n_in
            ci = int(np.argmax(sc))
            if sc[ci] > best[0]:
                best = (sc[ci], kk, Cs[ci])
        _, kk, C = best
        cols = order[:kk]
        lr = LogisticRegression(C=C, max_iter=2000, tol=1e-7).fit(Z(tr, cols), y[tr])
        va_p = lr.predict_proba(Z(va, cols))[:, 1]
        te_p = lr.predict_proba((XT[:, cols] - mu[cols]) / sd[cols])[:, 1]
        # rank-average sanity baseline, k picked on outer-train rows
        rk = max((min(x, m) for x in RKs), key=lambda x: roc_auc_score(
            y[tr], np.mean([_pct(X[tr, j]) for j in order[:x]], 0)))
        va_r = np.mean([_pct(X[va, j]) for j in order[:rk]], 0)
        te_r = np.mean([_pct(XT[:, j]) for j in order[:rk]], 0)
        inf = dict(fold=k, k=kk, C=C, inner=round(best[0], 6), rank_k=rk,
                   auc=roc_auc_score(y[va], va_p), auc_r=roc_auc_score(y[va], va_r))
        ckdir.mkdir(parents=True, exist_ok=True)
        np.savez(ck, va=va_p, va_r=va_r, te=te_p, te_r=te_r, info=json.dumps(inf))
        oof[va], oof_r[va] = va_p, va_r; tst += te_p / 5; tst_r += te_r / 5; info.append(inf)
    return oof, tst, oof_r, tst_r, info


def main(cfg, exp, smoke=False):
    rng = np.random.default_rng(0)
    tr_ids, y, te_ids = labels()
    f = folds(y)
    key = hashlib.md5(json.dumps({k: cfg[k] for k in ("exclude_regex", "auc_max", "lb_gap_max", "ks_max",
                      "dedupe_corr", "lb")}, sort_keys=True, default=str).encode()).hexdigest()[:8]
    cache = ART / "cache" / f"{exp}_{key}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        X, XT, names, log = z["X"], z["XT"], list(z["names"]), str(z["log"])
    else:
        raw, skipped = load_members(DATA / cfg["oof_dir"], tr_ids, te_ids)
        kept, drop, lb_known, ksq = filter_members(raw, y, cfg, rng)
        names = [r[1] for r in kept]
        X, XT = np.stack([r[2] for r in kept], 1), np.stack([r[3] for r in kept], 1)
        log = (f"loaded={len(raw)} kept={len(kept)} dropped " + " ".join(f"{k}={v}" for k, v in drop.items())
               + f" | lb_known={lb_known}/{len(raw)} no_test_file={len(skipped)} ks_p50/p95={ksq[0]:.4f}/{ksq[1]:.4f} best_single={kept[0][0]:.5f}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, X=X, XT=XT, names=np.array(names), log=log)
        pd.DataFrame([dict(name=r[1], auc=r[0], ks=r[4]) for r in kept]).to_csv(ART / f"{exp}_members.csv", index=False)
    print(f"[{exp}] filter: {log}", flush=True)
    forced = []
    for e in cfg.get("extra") or []:                            # own models, always offered to the stacker first
        o, t = _logit_pair(np.load(ART / "oof" / f"{e}.npy"), np.load(ART / "test" / f"{e}.npy"))
        X, XT = np.column_stack([X, o]), np.column_stack([XT, t]); names.append(f"own:{e}"); forced.append(X.shape[1] - 1)
    oof, tst, oof_r, tst_r, info = nested_stack(X, XT, y, f, forced, cfg, ART / "ckpt" / exp)
    pf, pfr = [i["auc"] for i in info], [i["auc_r"] for i in info]
    save_preds(exp, oof, tst); save_preds(exp + "_rankavg", oof_r, tst_r)
    sel = " ".join(f"k{i['k']}/C{i['C']:g}" for i in info)
    log_exp(exp, f"{X.shape[1]} members ({len(forced)} own)", "LR-L2 nested", pf,
            f"oof_auc={roc_auc_score(y, oof):.6f}; sel={sel}; {log}")
    log_exp(exp + "_rankavg", f"top-k of {X.shape[1]}", "rank-avg", pfr, f"k={[i['rank_k'] for i in info]}")
    print(f"[{exp}] stack cv={np.mean(pf):.6f}±{np.std(pf):.6f} folds={[round(a, 5) for a in pf]} sel={sel} | "
          f"rankavg cv={np.mean(pfr):.6f} k={[i['rank_k'] for i in info]} | members={X.shape[1]}", flush=True)
