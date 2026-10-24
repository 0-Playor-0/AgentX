"""Tokenless OOF fetch for the slim bundle: download the public OOF libraries anonymously with kagglehub into
$S6_DATA/public_oof/<dataset-name>/; a source that fails anonymously is taken from $DRV/extra_<source>.zip (or a
known alias such as s6e10_golem.zip) if present. Every file is checked against the md5s pinned in public_oof/MD5SUMS.
Exits non-zero if a source is unavailable or any pinned file is missing or changed upstream.
Without a pinned list, it records the md5s of what it downloaded to $S6_ART/public_oof_MD5SUMS instead."""
import hashlib, os, shutil, sys, zipfile
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
EXTRA_DIR = Path(os.environ.get("S6_EXTRA_DIR", os.environ.get("DRV", ".")))
ALIASES = {"s6e10-golem-oof-library": "s6e10_golem.zip"}   # its whole-dataset zip fails on Kaggle's side


def extra_zip(name):
    """Hand-made zip of one library (files at the zip root): extra_<source>.zip, or a known alias."""
    for z in (EXTRA_DIR / f"extra_{name}.zip", EXTRA_DIR / ALIASES.get(name, f"extra_{name}.zip")):
        if z.exists():
            return z


failed, via = [], {}
for s in SLUGS:
    name = s.split("/")[1]
    try:
        src = Path(kagglehub.dataset_download(s))
        shutil.copytree(src, out / name, dirs_exist_ok=True)
        via[name] = "anon"
    except Exception as e:                                   # noqa: BLE001 - any failure -> try the extra zip
        z = extra_zip(name)
        if z:
            zipfile.ZipFile(z).extractall(out / name)
            via[name] = z.name
        else:
            failed.append(f"{name}: {type(e).__name__} -> upload {ALIASES.get(name, f'extra_{name}.zip')} to {EXTRA_DIR}")


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
      f"changed_upstream={len(changed)} -> {'OK' if ok else 'FAIL'}"
      + " | via: " + " ".join(f"{k.replace('s6e10-', '')}={v}" for k, v in via.items() if v != "anon") + (f" | failed: {failed}" if failed else "") + (f" | e.g. {(missing + changed)[:3]}" if missing or changed else ""))
sys.exit(0 if ok else 1)
