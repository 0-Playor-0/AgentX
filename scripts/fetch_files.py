"""Download a Kaggle dataset file by file (for datasets whose whole-dataset zip fails). Needs Kaggle auth.
  python scripts/fetch_files.py <owner/slug> <out_dir>"""
import subprocess, sys, zipfile
from pathlib import Path

slug, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
K = str(Path(sys.executable).parent / "kaggle")
ls = subprocess.run([K, "datasets", "files", slug, "--page-size", "200"], capture_output=True, text=True).stdout
names = [l.split()[0] for l in ls.splitlines()[2:] if l.strip() and not l.startswith("-")]
ok, bad = 0, []
for f in names:
    if f.endswith(".png") or (out / f).stat().st_size if (out / f).exists() else False:
        ok += not f.endswith(".png"); continue
    subprocess.run([K, "datasets", "download", slug, "-f", f, "-p", str(out), "-q"], capture_output=True)
    z = out / f"{f}.zip"
    if z.exists() and zipfile.is_zipfile(z):
        zipfile.ZipFile(z).extractall(out)           # the .zip copy is left in place; bundling excludes *.zip
    if (out / f).exists() and (out / f).stat().st_size > 0:
        ok += 1
    else:
        bad.append(f)
print(f"[files] {slug}: ok={ok}/{len([n for n in names if not n.endswith('.png')])} failed={bad[:5]}")
