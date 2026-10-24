"""Synthetic smoke test for src/stack.py: fake comp data + fake members in every library format."""
import os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd

root = Path(tempfile.mkdtemp(prefix="s6smoke_")); D, A = root / "data", root / "art"
rng = np.random.default_rng(1); n, nt = 30_000, 12_000
lat, latt = rng.normal(size=n), rng.normal(size=nt)
y = (lat + rng.normal(scale=0.9, size=n) > 0)
(D / "comp").mkdir(parents=True)
pd.DataFrame({"id": np.arange(n), "satisfaction": y}).to_csv(D / "comp/train.csv", index=False)
pd.DataFrame({"id": np.arange(n, n + nt)}).to_csv(D / "comp/test.csv", index=False)
sig = lambda z: 1 / (1 + np.exp(-z))
mem = lambda s: (sig(lat + rng.normal(scale=s, size=n)), sig(latt + rng.normal(scale=s, size=nt)))
P = D / "public_oof"
for i in range(6):                                            # npy pairs
    (P / "a").mkdir(parents=True, exist_ok=True); o, t = mem(0.5 + 0.1 * i)
    np.save(P / f"a/oof_m{i}.npy", o); np.save(P / f"a/test_m{i}.npy", t)
o, t = mem(0.6); np.save(P / "a/oof_stack9.npy", o); np.save(P / "a/test_stack9.npy", t)        # stack-level
np.save(P / "a/oof_leak.npy", y + rng.normal(scale=.01, size=n)); np.save(P / "a/test_leak.npy", t)  # auc_hi
o, t = mem(0.7); np.save(P / "a/oof_shift.npy", o); np.save(P / "a/test_shift.npy", t ** 3)    # ks
np.save(P / "a/oof_dup.npy", np.load(P / "a/oof_m0.npy") * 0.99); np.save(P / "a/test_dup.npy", np.load(P / "a/test_m0.npy"))
(P / "b").mkdir(); o, t = mem(0.8); np.savez(P / "b/z.npz", oof=o, test=t)                     # npz
(P / "c").mkdir(); o, t = mem(0.9)                                                             # csv by id (shuffled)
pd.DataFrame({"id": np.arange(n), "fold": 0, "pred": o}).sample(frac=1, random_state=0).to_csv(P / "c/x_oof.csv", index=False)
pd.DataFrame({"id": np.arange(n, n + nt), "pred": t}).to_csv(P / "c/x_test.csv", index=False)
(P / "d").mkdir(); o1, t1 = mem(1.0); o2, t2 = mem(1.1)                                        # wide parquet
pd.DataFrame({"id": np.arange(n), "fold": 0, "satisfaction": y, "p1": o1, "p2": np.log(o2 / (1 - o2))}).to_parquet(P / "d/oof_predictions.parquet")
pd.DataFrame({"id": np.arange(n, n + nt), "p1": t1, "p2": np.log(t2 / (1 - t2))}).to_parquet(P / "d/test_predictions.parquet")
cfg = (Path("configs/e1_stack.yaml").read_text().replace("[20, 40, 80]", "[3, 6]").replace("[5, 10, 20]", "[2, 4]")
       .replace("[0.0001, 0.0003, 0.001, 0.003, 0.01, 0.1]", "[0.001, 0.1]"))
Path("configs/e1_smoke.yaml").write_text(cfg)
env = dict(os.environ, S6_DATA=str(D), S6_ART=str(A))
for run in (1, 2):                                            # run 2 must resume from cache + fold checkpoints
    r = subprocess.run([sys.executable, "src/run.py", "--exp", "e1_smoke"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    print(f"run{run}: " + r.stdout.strip().replace("\n", " || "))
exp = pd.read_csv(A / "experiments.csv")
print(f"smoke OK: experiments.csv rows={len(exp)} oof={np.load(A / 'oof/e1_smoke.npy').shape} test={np.load(A / 'test/e1_smoke.npy').shape}")
Path("configs/e1_smoke.yaml").unlink()
