#!/usr/bin/env bash
# QGIS 公式プラグインリポジトリ配布用の ZIP を dist/ に生成する。
#
#   ./scripts/package.sh
#
# ZIP のトップレベルはプラグインフォルダ（sateais_qgis/）である必要がある。
# tests / キャッシュ類は配布物から除外する。
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^version=//p' sateais_qgis/metadata.txt | tr -d '[:space:]')
if [ -z "$VERSION" ]; then
  echo "error: version= not found in sateais_qgis/metadata.txt" >&2
  exit 1
fi

OUT="dist/sateais_qgis-${VERSION}.zip"
mkdir -p dist
rm -f "$OUT"

zip -r -q "$OUT" sateais_qgis \
  -x "sateais_qgis/tests/*" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "*/.DS_Store"

echo "built: $OUT"
unzip -l "$OUT" | awk 'END {print $1 " bytes, " NR-2 " entries"}'

# 配布物に含まれてはいけないものが混ざっていないか最終確認
if unzip -l "$OUT" | grep -E "__pycache__|/tests/|\.pyc" >/dev/null; then
  echo "error: packaging leaked excluded files" >&2
  exit 1
fi
echo "metadata version: $VERSION / experimental: $(sed -n 's/^experimental=//p' sateais_qgis/metadata.txt)"
