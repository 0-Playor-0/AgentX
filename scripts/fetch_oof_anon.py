"""Tokenless fallback for the slim bundle: download the public OOF libraries anonymously with kagglehub into
$S6_DATA/public_oof/<dataset-name>/ and check every file against the md5s pinned in public_oof/MD5SUMS.
Exits non-zero (-> use the full bundle) if any download fails or any pinned file is missing or changed upstream.
Without a pinned list, it records the md5s of what it downloaded to $S6_ART/public_oof_MD5SUMS instead."""
import hashlib, os, shutil, sys
from pathlib import Path

SLUGS = ["cdeotte/s6e10-124-public-oof-and-test-predictions", "cdeotte/s6e10-tfm-oof-and-test-predictions",
         "sachith7/s6e10-stack-oof-predictions", "megayak/s6e10-oof-library", "dariushafshar/s6e10-golem-oof-library",
         "arhancanli12/s6e10-oof-test-predictions", "abdullahsafwan333/oof-dataset",
         "goodpjw2008/s6e10-goodpjw2008-extra-members-oof"]
out = Path(os.environ.get("S6_DATA", "data")) / "public_oof"
pin_file = out / "MD5SUMS"
pins = {}
if pin_file.exists():
    for l in pin_file.read_text().splitlines():
        if l.strip():
            h, f = l.split(maxsplit=1)
            pins[f.strip().removeprefix("./")] = h
out.mkdir(parents=True, exist_ok=True)

try:
    import kagglehub
except ImportError:
    sys.exit("[anon] kagglehub not installed")
failed = []
for s in SLUGS:
    name = s.split("/")[1]
    try:
        src = Path(kagglehub.dataset_download(s))
        shutil.copytree(src, out / name, dirs_exist_ok=True)
    except Exception as e:                                   # noqa: BLE001 - any failure means "use full bundle"
        failed.append(f"{name}: {type(e).__name__}")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


if not pins:                                               # unpinned: record what this run will stack
    got = sorted(str(f.relative_to(out)) for f in out.rglob("*") if f.suffix in (".npy", ".npz", ".parquet", ".csv"))
    art = Path(os.environ.get("S6_ART", "artifacts")); art.mkdir(parents=True, exist_ok=True)
    (art / "public_oof_MD5SUMS").write_text("".join(f"{md5(out / f)}  ./{f}\n" for f in got))
missing = [p for p in pins if not (out / p).exists()]
changed = [p for p in pins if (out / p).exists() and md5(out / p) != pins[p]]
ok = not (failed or missing or changed)
print(f"[anon] sources={len(SLUGS) - len(failed)}/{len(SLUGS)} pinned_files={len(pins) or 'none (md5s recorded to S6_ART/public_oof_MD5SUMS)'} missing={len(missing)} "
      f"changed_upstream={len(changed)} -> {'OK' if ok else 'FAIL, use full bundle'}"
      + (f" | failed: {failed[:3]}" if failed else "") + (f" | e.g. {(missing + changed)[:3]}" if missing or changed else ""))
sys.exit(0 if ok else 1)
