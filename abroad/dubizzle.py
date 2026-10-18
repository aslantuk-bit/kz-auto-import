"""Цены объявлений dubizzle (ОАЭ) — сводка по модели и году из выгрузки, собранной в браузере.

Сбор: страницы выдачи dubizzle открываются в Chrome (программам сайт отвечает 403), по 1 запросу в 3 с;
выгрузка — scratchpad JSON {"<адрес Kolesa>|<год>": [{aed, km, y, fuel, side, spec, cc}]}.
Берём только левый руль (праворульные в РК не регистрируют) и спецификацию GCC.
Запуск: python -m abroad.dubizzle <выгрузка.json>
"""
import json
import re
import statistics
import sys
import time

from paths import RAW

OUT = RAW / "abroad_dubizzle.json"
FUEL = {"Petrol": "бензин", "Diesel": "дизель", "Hybrid": "гибрид", "Electric": "электро", "Plug-in Hybrid": "гибрид"}


def summarize(rows, year):
    ok = [r for r in rows if r.get("side") == "Left Hand" and r.get("spec") == "GCC Specs" and r.get("y") == year
          and FUEL.get(r.get("fuel")) and r.get("aed", 0) > 5000]
    if not ok:
        return None
    fuel = max({r["fuel"] for r in ok}, key=lambda f: sum(r["fuel"] == f for r in ok))
    same = sorted((r for r in ok if r["fuel"] == fuel), key=lambda r: r["aed"])
    ccs = [int(m.group(1)) for r in same if (m := re.match(r"(\d{4})", r.get("cc") or ""))]
    return {"n": len(same), "med_aed": statistics.median(r["aed"] for r in same),
            "p25_aed": same[len(same) // 4]["aed"], "p75_aed": same[(3 * len(same)) // 4]["aed"],
            "km": round(statistics.median(r["km"] for r in same)), "f": FUEL[fuel],
            "cc_band": statistics.median_low(ccs) if ccs else None}


def main(path):
    raw = json.loads(open(path, encoding="utf-8").read())
    data = {"source": "uae.dubizzle.com", "date": time.strftime("%Y-%m-%d"), "models": {}}
    for key, rows in raw.items():
        slug, y = key.split("|")
        data["models"].setdefault(slug, {})[y] = summarize(rows, int(y))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(sum(1 for m in data["models"].values() for v in m.values() if v), "пар модель-год")


if __name__ == "__main__":
    main(sys.argv[1])
