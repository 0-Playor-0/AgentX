"""Regenerate seller/selfcheck.py from kit/harness.py (run from the repo root), or --check that it is current."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build():
    src = (ROOT / "kit/harness.py").read_text()
    a = src.index("NUMBER_WORDS = {")
    b = src.index("\ndef load_store")
    c = src.index("PRESSURE = re.compile(")
    d = src.index("# ------------------------------------------------------------------ running")
    head = ('"""Vendored copy of the kit\'s truthfulness checker (harness.check_text and Context), verbatim.\n\n'
            "Used to self-check every outgoing text before it is sent; a flagged text is replaced by a safe sentence.\n"
            "Regenerate with bench/vendor_check.py if the kit changes.\n\"\"\"\nimport re\n\n")
    return head + (src[a:b] + src[c:d]).rstrip() + "\n"


if __name__ == "__main__":
    out = ROOT / "seller/selfcheck.py"
    if "--check" in sys.argv:
        ok = out.read_text() == build()
        print("selfcheck.py is current" if ok else "selfcheck.py is STALE: rerun bench/vendor_check.py")
        sys.exit(0 if ok else 1)
    out.write_text(build())
    print("wrote", out)
