"""AgentX seller: deterministic, standard library only, no LLM.

    python kit/evaluate.py --seller seller/agent.py

Pipeline per turn: guard (parse type/round/items; buyer text is never read for decisions) -> buyer model
(bids as share of list) -> strategy (Boulware curve + behavioural adaptation) -> policy check on every
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
        self.model = BuyerModel()
        self.prev_x = None          # our last offer, in x units
        self.recip_bonus = 0.0
        self.stall_bonus = 0.0
        self.stall_used = False
        self.fast = False
        self.last_offer = None
        self.offers = 0
        self.notes = ""
        self.ctx = selfcheck.Context(self.store, self.policy)

    def respond(self, message):
        try:
            self._observe(message)
        except Exception:
            pass
        try:
            out = self._respond(message)
        except Exception:
            out = self._fallback()
        return self._finish(out)

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
        new = []
        for s, q, p in g["lines"]:
            if s in self.asked:
                new.append((s, min(q, self.asked[s])))           # never more than first asked for
            elif p is None or p >= 0.5 * self.P.list_price(s):   # a plausible new line, not a ₹1 slip-in
                self.asked[s] = q
                new.append((s, q))
        if new:
            self.basket = new

    # ------------------------------------------------------------------ decisions

    def _respond(self, msg):
        g = guard.parse(msg, self.P)
        r, R, prm = g["round"], self.R, self.prm

        if self.basket is None:
            if not g["lines"]:
                if g["oos"]:
                    return {"type": "walk_away", "text": writer.notes(self.store, g["oos"], {}, []) or writer.NOTHING}
                if r >= R:
                    return {"type": "walk_away", "text": writer.WALK}
                return {"type": "message", "text": writer.ASK}
            self.basket = [(s, q) for s, q, _ in g["lines"]]
            self.asked = dict(self.basket)
            self.notes = writer.notes(self.store, g["oos"], g["clipped"], self.basket)
        else:
            self._update_basket(g)

        L, F = self._totals()
        bid = {s: p for s, q, p in g["lines"] if p is not None}
        b_share = None
        if g["type"] in ("request", "counter") and all(s in bid for s, _ in self.basket):
            b_share = sum(q * bid[s] for s, q in self.basket) / L
            self.model.record(r, b_share)
            self._adapt(L, F)

        x_plan = self._plan(r)
        raw = g["raw"]
        if raw is not None and self.P.compliant(raw):
            if self.P.profit(raw) >= self.P.profit(self._price(x_plan)) or r >= prm["late"]:
                return {"type": "accept", "text": writer.ACCEPT}

        if r >= R:
            proj = self.model.projected(1)
            if proj is not None and F / L - proj > prm["walk_gap"]:
                return {"type": "walk_away", "text": writer.WALK}
            x_plan = max(0.0, prm["final_k"] * self._to_x(proj)) if proj is not None else 0.0

        x = x_plan
        if b_share is not None:
            x = max(x, self._to_x(b_share))        # never offer less than the buyer is bidding
        if self.prev_x is not None:
            x = min(x, self.prev_x)                # never raise our price
        x = min(1.0, max(0.0, x))
        self.prev_x = x
        items = self._price(x)
        at_floor = all(i["unit_price"] == self.P.floor(i["sku"]) for i in items)
        text = writer.offer_text(items, self.store, prm["mode"], self.offers == 0, at_floor,
                                 prefix=self.notes if self.offers == 0 else "")
        self.offers += 1
        return {"type": "offer", "items": items, "text": text}

    def _adapt(self, L, F):
        prm = self.prm
        m = self.model.move()
        if m is not None and m > 0 and L > F:
            self.recip_bonus += min(0.2, prm["recip"] * m * L / (L - F))
        sp = self.model.early_speed(2)
        if sp is not None and len(self.model.bids) == 3 and sp >= prm["fast_speed"]:
            self.fast = True
        if not self.stall_used and self.model.stalled(2):
            self.stall_bonus += prm["stall_step"]
            self.stall_used = True

    def _plan(self, r):
        prm = self.prm
        Rc = min(self.R, prm["fast_R"]) if self.fast else self.R
        x = prm["x0"] * curve(r, Rc, prm["e"]) - self.recip_bonus - self.stall_bonus
        if self.prev_x is not None:
            x = min(x, self.prev_x)
        return min(1.0, max(0.0, x))
