import pandas as pd, sys
o = pd.concat([pd.read_csv(f"data/orig/{f}.csv") for f in ("train", "test")])
fd = o["Flight Distance"]; vc = fd.value_counts()
print(f"orig rows={len(o)} cols={o.shape[1]} FD_unique={fd.nunique()} FD_median_count={vc.median():.0f} "
      f"FD_top_share={(vc[vc>=20].sum()/len(o)):.2f} target_vals={sorted(o['satisfaction'].unique())} "
      f"pos_rate={(o['satisfaction']=='satisfied').mean():.3f} na={o.isna().sum().sum()}")
