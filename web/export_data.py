"""Готовит docs/data.json для веб-версии: константы калькулятора из calc.py и база из out/.

Запуск после пересборки базы: .venv/bin/python web/export_data.py
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import calc  # noqa: E402
import savings  # noqa: E402
from paths import OUT  # noqa: E402

DOCS = ROOT / "docs"
RATE_COLS = {
    "id": "id", "блок": "block", "этап": "stage", "вид_платежа": "kind", "категория_ТС": "category",
    "категория_ЕЭК": "eec", "код_ТНВЭД": "hs", "тип_двигателя": "fuel", "объём_от_см3": "cc_from",
    "объём_до_см3": "cc_to", "возраст_от_лет": "age_from", "возраст_до_лет": "age_to", "субъект": "subject",
    "происхождение": "origin", "режим": "regime", "ставка_адвалорная_пct": "pct", "ставка_специфическая": "spec",
    "единица_специфической": "spec_unit", "минимум": "minimum", "ставка_МРП": "mrp", "коэффициент": "coef",
    "ставка_текст": "rate_text", "формула": "formula", "сумма_тг_2026": "kzt", "правовой_акт": "act",
    "статья": "article", "url": "url", "действует_с": "from", "действует_по": "to", "актуальна": "current",
    "достоверность": "rel", "примечание": "note",
}


def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, float) and math.isinf(v):
        return None   # бесконечная верхняя граница → null
    return v


def records(df):
    return [{k: clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def constants():
    return {
        "MRP": calc.MRP, "EUR": calc.EUR, "VAT": calc.VAT, "CUSTOMS_FEE_MRP": calc.CUSTOMS_FEE_MRP,
        "LUX_THRESHOLD": calc.LUX_THRESHOLD, "MARKET": calc.MARKET,
        "ETT_PETROL_EDGES": calc.ETT_PETROL_EDGES, "ETT_PETROL_MIN_3_7": calc.ETT_PETROL_MIN_3_7,
        "ETT_PETROL_OVER7": calc.ETT_PETROL_OVER7, "ETT_DIESEL_EDGES": calc.ETT_DIESEL_EDGES,
        "ETT_DIESEL_MIN_3_7": calc.ETT_DIESEL_MIN_3_7, "ETT_DIESEL_OVER7": calc.ETT_DIESEL_OVER7,
        "PTD_NEW": [[clean(a), b, c] for a, b, c in calc.PTD_NEW], "PTD_EDGES": calc.PTD_EDGES,
        "PTD_3_5": calc.PTD_3_5, "PTD_OVER5": calc.PTD_OVER5,
        "UTIL_EDGES": calc.UTIL_EDGES, "UTIL_K1": calc.UTIL_K1, "UTIL_K2": calc.UTIL_K2, "UTIL_EV": calc.UTIL_EV,
        "SCENARIO": {"engines": calc.SCENARIO_ENGINES, "ages": calc.SCENARIO_AGES,
                     "prices": calc.SCENARIO_PRICES},
    }


def main():
    DOCS.mkdir(exist_ok=True)
    params = pd.read_csv(OUT / "параметры.csv").set_index("параметр")["значение"]
    rates = pd.read_csv(OUT / "ставки.csv")[list(RATE_COLS)].rename(columns=RATE_COLS)
    with sqlite3.connect(OUT / "kz_auto_import.sqlite") as con:
        questions = pd.read_sql("select * from спорные", con)
        conditions = pd.read_sql("select * from условия", con)
        sources = pd.read_sql("select * from источники", con)
    data = {
        "asOf": "2026-10-15",
        "constants": constants(),
        "fx": {"EUR": params["EUR_KZT_15.10.2026"], "USD": params["USD_KZT_15.10.2026"],
               "CNY": params["CNY_KZT_15.10.2026"], "RUB": params["RUB_KZT_15.10.2026"], "KZT": 1},
        "rates": records(rates),
        "questions": records(questions.rename(columns={"вопрос": "q", "неясность": "issue", "как_учтено": "how"})),
        "conditions": records(conditions.rename(columns={
            "условие": "what", "категория_ТС": "category", "субъект": "subject", "правовой_акт": "act",
            "статья": "article", "url": "url", "действует_с": "from", "достоверность": "rel",
            "статус_проверки": "status", "примечание": "note"})),
        "savings": savings.compute(),
        "sources": records(sources.rename(columns={"правовой_акт": "act", "записей": "n", "блоки": "blocks"})),
    }
    out = DOCS / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(out, f"{out.stat().st_size / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
