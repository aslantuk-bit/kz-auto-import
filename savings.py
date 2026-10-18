"""«Как сэкономить»: выводы по полной сетке вариантов, посчитанные калькулятором calc.py.

Один источник для приложения (ui/page_savings.py) и сайта (web/export_data.py → data.json).
Машины из третьих стран (ДТ, ПТД) — с типовой доставкой calc.DELIVERY_EUR до границы ЕАЭС.
"""
from itertools import product

import calc

ENGINES = calc.SCENARIO_ENGINES
AGES = range(0, 16)
PRICES = (5000, 8000, 12000, 15000, 20000, 25000, 30000, 40000, 55000, 70000, 100000, 150000)
ROUTES = (("ДТ", "третьи", "dt"), ("ПТД", "третьи", "ptd"), ("ЕАЭС_ЮЛ", "третьи", "kg_ul"),
          ("ЕАЭС_ФЛ", "третьи", "kg_fl"), ("ЕАЭС_ЮЛ", "РФ_РБ", "ru_ul"), ("ЕАЭС_ФЛ", "РФ_РБ", "ru_fl"))
BLOCKS = ("регистрация невозможна", "нельзя передавать")


D = calc.DELIVERY_EUR


def total(price, fuel, cc, age, mode="ДТ", origin="третьи"):
    return calc.calc(calc.Car(price, fuel, cc, age, mode, origin, доставка_eur=D))["итого_обязательные"]


def _grid():
    rows = []
    for (fuel, cc), age, price in product(ENGINES, AGES, PRICES):
        for mode, origin, rid in ROUTES:
            car = calc.Car(price, fuel, cc, age, mode, origin, доставка_eur=D)
            r = calc.calc(car)
            rows.append({
                "key": (fuel, cc, age, price), "fuel": fuel, "route": rid,
                "blocked": any(b in r["примечания"] for b in BLOCKS),
                "kz": r["итого_обязательные"],
                # пошлина ЕТТ, уплаченная в стране ЕАЭС и заложенная в цену; без их НДС и сборов — оценка снизу;
                # для третьих стран — плюс сама доставка до границы ЕАЭС
                "landed": price * calc.EUR + r["итого_обязательные"] + r["доставка_кзт"]
                          + (calc.duty_ett(car) if mode.startswith("ЕАЭС") else 0),
            })
    return rows


def _winners(rows, col):
    best = {}
    for r in rows:
        if r["blocked"] or r["route"].startswith("ru"):
            continue
        b = best.get(r["key"])
        if b is None or r[col] < b[col]:
            best[r["key"]] = r
    return best


def _shares(best):
    n = len(best)
    out = {}
    for r in best.values():
        out[r["route"]] = out.get(r["route"], 0) + 1
    return {k: round(100 * v / n, 1) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}


def compute():
    rows = _grid()
    by_kz, by_landed = _winners(rows, "kz"), _winners(rows, "landed")
    ru = sorted(r["kz"] - by_kz[r["key"]]["kz"] for r in rows if r["route"] == "ru_fl")
    ev = [w for k, w in by_landed.items() if k[0] == "электро"]

    p, a = 15000, 1
    ptd_dt = {age: {pr: total(pr, "бензин", 2000, age, "ПТД") - total(pr, "бензин", 2000, age, "ДТ") for pr in PRICES}
              for age in range(0, 6)}
    return {
        "delivery_eur": D,
        "configs": len(by_kz),
        "routes_total": len(rows),
        "ru": {"min": ru[0], "median": ru[len(ru) // 2]},
        "ev": {"wins": sum(w["route"] == "dt" for w in ev), "n": len(ev),
               "example_price": 30000,
               "example": {"электро": total(30000, "электро", 0, a), "гибрид_эл": total(30000, "гибрид_эл", 1500, a),
                           "бензин": total(30000, "бензин", 2000, a)}},
        "age": {"price": p,
                "dt_1_2": total(p, "бензин", 2000, 2) - total(p, "бензин", 2000, 1),
                "dt_2_3": total(p, "бензин", 2000, 3) - total(p, "бензин", 2000, 2),
                "ptd_5_6": total(p, "бензин", 2000, 6, "ПТД") - total(p, "бензин", 2000, 5, "ПТД")},
        "volume": {"price": 25000,
                   "v2000_2100": total(25000, "бензин", 2100, 4) - total(25000, "бензин", 2000, 4),
                   "v3000_3100": total(25000, "бензин", 3100, 4) - total(25000, "бензин", 3000, 4),
                   "new_2900": total(25000, "бензин", 2900, 1), "new_2000": total(25000, "бензин", 2000, 1)},
        "ptd_dt": {"prices": list(PRICES), "rows": {str(k): [v[pr] for pr in PRICES] for k, v in ptd_dt.items()},
                   # с какой цены б/у 3–5 лет по ПТД дешевле, чем по ДТ
                   "from_price": min((pr for pr in PRICES if ptd_dt[4][pr] < 0), default=None)},
        "eaeu": {"by_kz": _shares(by_kz), "by_landed": _shares(by_landed)},
        "lux": {"kzt": calc.LUX_THRESHOLD, "eur": calc.LUX_THRESHOLD / calc.EUR},
        "cheap": {"price": 8000,
                  "share_min": min(100 * total(8000, f, c, 4, m) / (8000 * calc.EUR)
                                   for f, c in (("бензин", 1500), ("бензин", 2000)) for m in ("ДТ",)),
                  "share_max": max(100 * total(8000, "бензин", 2000, ag, m) / (8000 * calc.EUR)
                                   for ag in (1, 4) for m in ("ДТ", "ПТД"))},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compute(), ensure_ascii=False, indent=1, default=float)[:3000])
