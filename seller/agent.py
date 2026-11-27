"""AgentX seller: deterministic, standard library only, no LLM.

    python kit/evaluate.py --seller seller/agent.py

Pipeline per turn: guard (parse type/round/items; buyer text is never read for decisions) -> buyer model
(bids as share of list) -> strategy (concession curve; AC_next acceptance, round-10 EV rule) -> policy check on every
outgoing price -> writer (templates) -> self-check of the text with the kit's own checker.
"""
import copy
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from seller import guard, selfcheck, writer          # noqa: E402
from seller.model import BuyerModel                   # noqa: E402
from seller.policy import Policy                      # noqa: E402
from seller.strategy import DEFAULTS, curve           # noqa: E402


class Seller:
    params = DEFAULTS

    def __init__(self, store, policy, params=None):
        self.store, self.policy = store, policy
        self.P = Policy(store, policy)
        self.R = int(policy.get("max_rounds", 10)) if isinstance(policy, dict) else 10
        self.prm = dict(DEFAULTS, **(self.params or {}), **(params or {}))
        self.start(None)

    # ------------------------------------------------------------------ lifecycle

    def start(self, negotiation_id):
        self.basket = None          # [(sku, qty)] we are selling
        self.asked = {}             # sku -> qty the buyer first asked for (clipped to stock)
        self.pending = set()        # new SKUs seen in the buyer's last bid, not yet in the basket
        self.model = BuyerModel()
        self.prev_x = None          # our last offer, in x units
        self.last_offer = None
        self.offers = 0
        self.notes = ""
        self.clipped = {}
        self.ctx = selfcheck.Context(self.store, self.policy)
        self.trace = []             # one plain-English "why" per turn. Log only: never sent to the buyer.
        self._why = None

    def respond(self, message):
        self._why = None
        try:
            self._observe(message)
        except Exception:
            pass
        try:
            out = self._respond(message)
        except Exception:
            out = self._fallback()
            self._why = "Internal error: repeat our last offer (safe fallback)."
        out = self._finish(out)
        try:
            self.trace.append({"round": message.get("round") if isinstance(message, dict) else None,
                               "type": out.get("type"), "why": self._why or ""})
        except Exception:
            pass
        return out

    def _explain(self, fn):
        """Set this turn's reason. Explanation only: it can never change a decision."""
        try:
            self._why = fn()
        except Exception:
            self._why = None

    # ------------------------------------------------------------------ bookkeeping

    def _observe(self, msg):
        """Mirror of the harness's Context, so our texts can be self-checked exactly."""
        if not isinstance(msg, dict):
            return
        self.ctx.add_items(msg.get("items"))
        self.ctx.add_text(msg.get("text"))
        if msg.get("type") == "request":
            for it in msg.get("items") or []:
                if isinstance(it, dict) and isinstance(it.get("qty"), int):
                    self.ctx.wanted[it.get("sku")] = it["qty"]

    def _finish(self, out):
        """Final gate: policy on items, self-check on text. Always returns a valid dict."""
        try:
            if out.get("type") == "offer":
                if not self.P.compliant(out.get("items")):
                    out = self._fallback()
                    self._why = "Policy check failed on the planned offer: repeat our last compliant offer."
                if out.get("type") == "offer":
                    self.ctx.add_items(out["items"])
                    self.last_offer = out["items"]
            text = out.get("text", "")
            if selfcheck.check_text(text, self.ctx.as_dict()):
                safe = writer.SAFE_OFFER if out["type"] == "offer" else \
                    writer.ACCEPT if out["type"] == "accept" else "Thank you."
                out["text"] = safe if not selfcheck.check_text(safe, self.ctx.as_dict()) else ""
            return out
        except Exception:
            return {"type": "message", "text": ""}

    def _fallback(self):
        if self.last_offer and self.P.compliant(self.last_offer):
            return {"type": "offer", "items": copy.deepcopy(self.last_offer), "text": writer.SAFE_OFFER}
        if self.basket:
            items = [{"sku": s, "qty": q, "unit_price": self.P.list_price(s)} for s, q in self.basket]
            if self.P.compliant(items):
                return {"type": "offer", "items": items, "text": writer.SAFE_OFFER}
        return {"type": "message", "text": ""}

    # ------------------------------------------------------------------ prices

    def _totals(self):
        L = sum(q * self.P.list_price(s) for s, q in self.basket)
        F = sum(q * self.P.floor(s) for s, q in self.basket)
        return L, F

    def _price(self, x):
        x = min(1.0, max(0.0, x))
        items = []
        for s, q in self.basket:
            f, lp = self.P.floor(s), self.P.list_price(s)
            items.append({"sku": s, "qty": q, "unit_price": min(lp, max(f, math.ceil(f + x * (lp - f) - 1e-9)))})
        return items

    def _to_x(self, share):
        L, F = self._totals()
        return (share * L - F) / (L - F) if L > F else (1.0 if share * L >= F else -1.0)

    # ------------------------------------------------------------------ basket

    def _update_basket(self, g):
        if g["type"] not in ("request", "counter") or not g["lines"]:
            return
        new, seen = [], set()
        for s, q, p in g["lines"]:
            if s in self.asked:
                new.append((s, min(q, self.asked[s])))           # never more than first asked for
            elif p is not None and p >= 0.5 * self.P.list_price(s):
                seen.add(s)                                      # a plausible new line, not a ₹1 slip-in:
                if s in self.pending:                            # added once it shows up in two bids in a row
                    self.asked[s] = q
                    new.append((s, q))
        self.pending = seen
        if new:
            self.basket = new

    # ------------------------------------------------------------------ decisions

    def _respond(self, msg):
        g = guard.parse(msg, self.P)
        r, R, prm = g["round"], self.R, self.prm

        if self.basket is None:
            if not g["lines"]:
                if g["oos"]:
                    self._explain(lambda: f"Every requested product is out of stock ({len(g['oos'])} line(s)): "
                                          "nothing to sell, so walk away politely.")
                    return {"type": "walk_away", "text": writer.oos_walk(self.store, g["oos"])}
                if r >= R:
                    self._explain(lambda: "Last round and no product to sell: walk away.")
                    return {"type": "walk_away", "text": writer.WALK}
                self._explain(lambda: "No sellable product named yet: ask what they want.")
                return {"type": "message", "text": writer.ASK}
            self.basket = [(s, q) for s, q, _ in g["lines"]]
            self.asked = dict(self.basket)
            self.notes = writer.notes(self.store, g["oos"], g["clipped"], self.basket)
            self.clipped = dict(g["clipped"])
        else:
            self._update_basket(g)

        L, F = self._totals()
        bid = {s: p for s, q, p in g["lines"] if p is not None}
        b_share = None
        if g["type"] in ("request", "counter") and all(s in bid for s, _ in self.basket):
            b_share = sum(q * bid[s] for s, q in self.basket) / L
            self.model.record(r, b_share)

        x_plan = self._plan(r)
        raw = g["raw"]
        if raw is not None and self.P.compliant(raw):
            # AC_next: take a compliant bid worth at least what we would offer next round
            if r >= R or self.P.profit(raw) >= self.P.profit(self._price(self._plan(r + 1))):
                self._explain(lambda: self._why_accept(raw, r, R, F))
                return {"type": "accept", "text": writer.accept_text(raw)}

        if r >= R:
            proj = self.model.projected(1)
            if proj is not None and F / L - proj > prm["walk_gap"]:
                self._explain(lambda: f"Last round: the buyer's projected bid {_rs(proj * L)} is "
                                      f"{100 * (F / L - proj):.0f}% of list below the floor {_rs(F)} "
                                      f"(walk if more than {100 * prm['walk_gap']:.0f}%): walk away, no deadlock.")
                return {"type": "walk_away", "text": writer.WALK}
            x_plan = max(0.0, prm["final_k"] * self._to_x(proj)) if proj is not None else 0.0

        x = x_plan
        if b_share is not None:
            x = max(x, self._to_x(b_share))        # never offer less than the buyer is bidding
        if self.prev_x is not None:
            x = min(x, self.prev_x)                # never raise our price
        x = min(1.0, max(0.0, x))
        self._explain(lambda: self._why_offer(r, R, x_plan, x, b_share, raw, L, F))
        self.prev_x = x
        items = self._price(x)
        at_floor = all(i["unit_price"] == self.P.floor(i["sku"]) for i in items)
        text = writer.offer_text(items, self.store, self.offers == 0, at_floor,
                                 prefix=self.notes if self.offers == 0 else
                                 writer.clip_note(self.store, self.clipped, self.basket))
        self.offers += 1
        return {"type": "offer", "items": items, "text": text}

    def _why_accept(self, raw, r, R, F):
        bid = sum(i["qty"] * i["unit_price"] for i in raw)
        if r >= R:
            return f"Last round: the bid {_rs(bid)} is within policy (floor {_rs(F)}), so accept it."
        nxt = self._price(self._plan(r + 1))
        return (f"Accept (AC_next): the bid {_rs(bid)} earns {_rs(self.P.profit(raw))} profit, at least the "
                f"{_rs(self.P.profit(nxt))} our next offer ({_rs(_total(nxt))}) would.")

    def _why_offer(self, r, R, x_plan, x, b_share, raw, L, F):
        offer = _total(self._price(x))
        parts = []
        bid = b_share * L if b_share is not None else None
        if raw is not None and not self.P.compliant(raw):
            if bid is not None and bid < F:
                parts.append(f"The bid {_rs(bid)} is below the floor {_rs(F)}.")
            else:
                parts.append("The bid has a line we can't accept (unknown, out of stock, over stock, "
                             "or below that item's floor).")
        elif raw is not None:
            nxt = self._price(self._plan(r + 1))
            parts.append(f"The bid {_rs(_total(raw))} earns less than our next offer would ({_rs(_total(nxt))}).")
        elif bid is not None and bid < F:
            parts.append(f"The bid {_rs(bid)} is below the floor {_rs(F)}.")
        if r >= R:
            proj = self.model.projected(1)
            parts.append(f"Final offer {_rs(offer)}: aims halfway from the floor {_rs(F)} toward the buyer's "
                         f"projected bid {_rs(proj * L)}." if proj is not None else f"Final offer {_rs(offer)}.")
        elif self.prev_x is None:
            parts.append(f"Opening offer {_rs(offer)}: {100 * x:.0f}% of the way from the floor {_rs(F)} "
                         f"to list {_rs(L)}.")
        else:
            parts.append(f"Round {r} of the concession curve: {_rs(offer)} (floor {_rs(F)}, list {_rs(L)}).")
        if x > x_plan + 1e-9:
            parts.append("Raised to the buyer's own bid: we never offer less than they bid.")
        elif x < x_plan - 1e-9:
            parts.append("Capped at our last offer: we never raise our price.")
        return " ".join(parts)

    def _plan(self, r):
        prm = self.prm
        x = prm["x0"] * curve(r, self.R, prm["e"])
        if self.prev_x is not None:
            x = min(x, self.prev_x)
        return min(1.0, max(0.0, x))


def _total(items):
    return sum(i["qty"] * i["unit_price"] for i in items)


def _rs(v):
    return f"₹{int(round(v)):,}"
