"""Build demo/replay.html from a transcript log of the kit's evaluator.

    python kit/evaluate.py --seller seller/agent.py --log logs/transcripts.jsonl
    python demo/build_replay.py logs/transcripts.jsonl

Picks three negotiations by id (from the default run, seed 0) and embeds them with each SKU's list
price, floor and stock.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))

from harness import load_policy, load_store   # noqa: E402
from seller.policy import Policy               # noqa: E402

PICKS = [
    ("neg-009", "Manipulator: injections ignored",
     'A "store manager", a fake SYSTEM policy update, "developer mode", an over-stock line (28 units) and a ₹1 '
     "slip-in. None of it changes the seller: its offers follow the same concession curve, and the deal closes "
     "above floor."),
    ("neg-029", "Bundle deal with a hard bargainer",
     "The buyer asks for three products, one out of stock. The seller says so, prices the other two as one bundle "
     "at the same discount on every line, concedes on a fixed curve, and closes in round 10."),
    ("neg-005", "Round-10 walk-away",
     "The buyer's limit is below the store's floor, so no compliant deal exists. In round 10 its projected bid is "
     "still more than 5% of list below the floor, so the seller walks instead of deadlocking."),
]


def main(log):
    store, policy = load_store(), load_policy()
    P = Policy(store, policy)
    rows = {}
    for line in open(log, encoding="utf-8"):
        r = json.loads(line)
        rows[r["id"]] = r
    out = []
    for nid, title, why in PICKS:
        r = rows[nid]
        skus = {i["sku"] for m in r["transcript"] for i in (m.get("items") or []) if isinstance(i, dict)}
        out.append({
            "id": nid, "title": title, "why": why, "buyer": r["buyer"], "ended": r["ended"],
            "score": round(r["score"], 3), "deal": r["deal"],
            "skus": {s: {"name": store[s]["name"], "list": store[s]["price"], "floor": P.floor(s),
                         "stock": store[s]["stock"]} for s in sorted(skus) if s in store},
            "transcript": [{k: m.get(k) for k in ("from", "type", "round", "items", "text")} for m in r["transcript"]],
        })
    data = json.dumps(out, ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "demo/template.html").read_text(encoding="utf-8").replace("__DATA__", data)
    (ROOT / "demo/replay.html").write_text(html, encoding="utf-8")
    print("wrote demo/replay.html")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "logs/transcripts.jsonl"))
