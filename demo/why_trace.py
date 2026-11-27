"""Rebuild the seller's reason trace ("why" per seller turn) by replaying logged negotiations.

    python demo/why_trace.py logs/transcripts.jsonl --out logs/why.jsonl

The seller keeps the trace in memory only (Seller.trace); it is never sent to the buyer. The seller is
deterministic and never reads buyer text, so feeding it the logged buyer messages reproduces the run.
Every replayed decision (type + items) is checked against the log; any mismatch is an error.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT))

from harness import load_policy, load_store   # noqa: E402
from seller.agent import Seller                # noqa: E402


def replay(row, seller):
    seller.start(row["id"])
    out, msgs = [], row["transcript"]
    for k, m in enumerate(msgs):
        if m.get("from") != "buyer" or k + 1 >= len(msgs) or msgs[k + 1].get("from") != "seller":
            continue
        logged = msgs[k + 1]
        buyer_msg = {key: v for key, v in m.items() if key != "from"}
        got = seller.respond(json.loads(json.dumps(buyer_msg)))
        if (got.get("type"), got.get("items")) != (logged.get("type"), logged.get("items")):
            raise SystemExit(f"{row['id']} round {m.get('round')}: replay differs from the log")
        out.append({"id": row["id"], "round": m.get("round"), "type": got["type"], "why": seller.trace[-1]["why"]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log", help="a kit/evaluate.py --log file for our seller")
    ap.add_argument("--out", default=str(ROOT / "logs/why.jsonl"))
    args = ap.parse_args()
    seller = Seller(load_store(), load_policy())
    n = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for line in open(args.log, encoding="utf-8"):
            for t in replay(json.loads(line), seller):
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {args.out}: {n} seller turns, all replayed decisions match the log")


if __name__ == "__main__":
    main()
