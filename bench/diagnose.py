"""Where value is lost, per buyer: feasible-but-no-deal vs deal below the buyer's limit (oracle = deal at limit)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))
import buyers as kb                                             # noqa: E402
import evaluate                                                 # noqa: E402
from harness import floor_price, load_policy, load_store        # noqa: E402
from sweep import seller_with                                   # noqa: E402

store, policy = load_store(), load_policy()
prm = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
seeds = [0, 1, 2]
agg = {}
for seed in seeds:
    sc = kb.make_scenarios(store, policy, 210, seed)
    rows, _, _ = evaluate.run(seller_with(prm), sc, kb.BUYERS, store, policy)
    for s, r in zip(sc, rows):
        sell = [(store[i["sku"]], min(i["qty"], store[i["sku"]]["stock"])) for i in s["items"]]
        top = sum(q * x["price"] for x, q in sell)
        pot = sum(q * (x["price"] - x["cost"]) for x, q in sell)
        cost = sum(q * x["cost"] for x, q in sell)
        fl = sum(q * floor_price(x, policy) for x, q in sell)
        a = agg.setdefault(s["buyer"], {"n": 0, "oracle": 0, "floor": 0, "got": 0, "missed": 0, "under": 0})
        a["n"] += 1
        a["got"] += r["value"]
        if r["feasible"] and pot > 0:
            ov = (min(top, s["reservation"] * top) - cost) / pot
            a["oracle"] += ov
            a["floor"] += (fl - cost) / pot
            if r["deal"]:
                a["under"] += ov - r["value"]
            else:
                a["missed"] += ov
for b, a in agg.items():
    n = a["n"]
    print(f"{b:15} got {100*a['got']/n:5.1f}  oracle {100*a['oracle']/n:5.1f}  all-at-floor {100*a['floor']/n:5.1f}  "
          f"lost: no-deal {100*a['missed']/n:5.1f}  below-limit {100*a['under']/n:5.1f}")
