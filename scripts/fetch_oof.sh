#!/usr/bin/env bash
# Download the public OOF libraries into $1/<dataset-name>/ (one dir per source) and unzip.
set -euo pipefail
OUT="$1"; mkdir -p "$OUT"
for d in cdeotte/s6e10-124-public-oof-and-test-predictions cdeotte/s6e10-tfm-oof-and-test-predictions \
         sachith7/s6e10-stack-oof-predictions megayak/s6e10-oof-library dariushafshar/s6e10-golem-oof-library \
         arhancanli12/s6e10-oof-test-predictions abdullahsafwan333/oof-dataset goodpjw2008/s6e10-goodpjw2008-extra-members-oof; do
  n=$(basename "$d"); [ -f "$OUT/$n/.done" ] && continue
  mkdir -p "$OUT/$n"; kaggle datasets download "$d" -p "$OUT/$n" -q --unzip && touch "$OUT/$n/.done"
  kaggle datasets metadata "$d" -p "$OUT/$n" >/dev/null 2>&1 || true
done
( cd "$OUT" && find . \( -name "*.npy" -o -name "*.npz" -o -name "*.parquet" -o -name "*.csv" \) -type f | sort | while read -r f; do if command -v md5sum >/dev/null; then md5sum "$f"; else echo "$(md5 -q "$f")  $f"; fi; done ) > "$OUT/MD5SUMS"
echo "fetched $(ls -d "$OUT"/*/ | wc -l) sources, $(wc -l < "$OUT/MD5SUMS") files (md5s in MD5SUMS)"
