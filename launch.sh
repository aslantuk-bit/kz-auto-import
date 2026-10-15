#!/bin/zsh
# Запускает приложение «Ввоз авто в РК» на http://localhost:8790 и открывает браузер.
cd "$(dirname "$0")"
if ! lsof -tnP -iTCP:8790 -sTCP:LISTEN >/dev/null; then
  nohup .venv/bin/streamlit run app.py > out/app.log 2>&1 &
  sleep 3
fi
open http://localhost:8790
