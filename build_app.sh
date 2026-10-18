#!/bin/zsh
# Собирает «Ввоз авто в РК.app» (PyInstaller) в dist/. Установка: ./build_app.sh --install
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-.venv/bin/python}
APP="Ввоз авто в РК.app"
$PY icons/make_icns.py >/dev/null
DATA=()
for f in ставки.csv параметры.csv условия.csv источники.csv сценарии.csv kz_auto_import.sqlite kz_auto_import_2026-10.xlsx; do
  DATA+=(--add-data "out/$f:out")
done
HIDDEN=()
for m in paths build calc report test_calc savings glossary ui ui.common ui.charts ui.page_calc ui.page_analytics ui.page_rates ui.page_misc ui.page_savings; do
  HIDDEN+=(--hidden-import "$m")
done
rm -rf .pyibuild dist/VvozAuto.app "dist/$APP"
$PY -m PyInstaller --noconfirm --windowed --workpath .pyibuild --name VvozAuto --icon icons/app.icns \
  --osx-bundle-identifier kz.aslantuk.vvoz-auto --paths . \
  --add-data "app.py:." --add-data "ui:ui" --add-data "sources/raw:sources/raw" "${DATA[@]}" "${HIDDEN[@]}" \
  --collect-all streamlit --collect-all altair --collect-all pyarrow --collect-all narwhals \
  --exclude-module PyInstaller --exclude-module pytest \
  kzai_app.py
mv dist/VvozAuto.app "dist/$APP"
PL="dist/$APP/Contents/Info.plist"
plutil -replace CFBundleName -string "Ввоз авто в РК" "$PL"
plutil -replace CFBundleDisplayName -string "Ввоз авто в РК" "$PL"
plutil -replace CFBundleShortVersionString -string "${VERSION:-1.2.0}" "$PL"
plutil -replace LSUIElement -bool true "$PL"
codesign --force --deep -s - "dist/$APP"
du -sh "dist/$APP"
if [[ "$1" == "--install" ]]; then
  rm -rf "/Applications/$APP"
  cp -R "dist/$APP" /Applications/
  xattr -dr com.apple.quarantine "/Applications/$APP" 2>/dev/null || true
  echo "установлено: /Applications/$APP"
fi
