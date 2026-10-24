#!/usr/bin/env bash
# Build bundle/s6e10_bundle_slim.zip (code + comp/orig data; Colab fetches the OOFs anonymously via kagglehub)
# (--slim) or the fallback bundle/s6e10_bundle.zip (+ every public OOF library, md5-pinned) (--full). Each mode touches only its own zip.
# Unzipped in Colab at /content/s6e10: code at the root, data under data/.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE=${1:?usage: make_bundle.sh --slim|--full}
mkdir -p bundle
CODE=$(git ls-files)                                   # committed code only, no secrets or local junk
DATA="data/comp/train.csv data/comp/test.csv data/comp/sample_submission.csv data/orig/train.csv data/orig/test.csv"
if [ "$MODE" = "--slim" ]; then
  rm -f bundle/s6e10_bundle_slim.zip
  # no OOFs; ships the md5 pin list only if the full download has finished
  PIN=$( [ -f data/public_oof/MD5SUMS ] && echo data/public_oof/MD5SUMS || true )
  zip -q bundle/s6e10_bundle_slim.zip $CODE $DATA $PIN
  echo "slim bundle: bundle/s6e10_bundle_slim.zip $(du -h bundle/s6e10_bundle_slim.zip | cut -f1) pins=${PIN:-none}"
else
  [ -f data/public_oof/MD5SUMS ] || { echo "OOF download not finished (no MD5SUMS)"; exit 1; }
  rm -f bundle/s6e10_bundle.zip
  zip -q -r bundle/s6e10_bundle.zip $CODE $DATA data/public_oof -x '*.zip' '*/.done' '*.png'
  echo "full bundle: bundle/s6e10_bundle.zip $(du -h bundle/s6e10_bundle.zip | cut -f1)"
fi
