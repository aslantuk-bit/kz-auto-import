"""Что выгодно ввезти: цена объявлений за рубежом + доставка + платежи против медианы Kolesa по той же модели и году.

Источники за рубежом — sources/raw/abroad_*.json (Encar — Корея, AutoScout24 — Германия, dubizzle — ОАЭ).
Расчёт платежей — calc.calc: из ДТ и ПТД берём дешёвый маршрут, на котором регистрация возможна.
Запуск: python -m abroad.deals — печатает рейтинг и пишет out/abroad_deals.csv.
"""
import csv
import json

import calc
import kolesa
from paths import OUT, RAW

TODAY_YEAR = calc.AS_OF.year
KRW_KZT = 33.97 / 100        # НБРК на 18.10.2026
AED_KZT = 123.11
# Доставка до границы ЕАЭС и вывоз из страны покупки, EUR — рыночные ориентиры («Г»):
# Корея — паром/контейнер через Китай или Владивосток $2,5–3 тыс. и экспортное оформление ~$500;
# Германия — автовоз €2–3 тыс. и вывозные номера/экспортная декларация ~€400;
# ОАЭ — контейнер через Иран/Туркменистан или Актау $2–2,8 тыс. и экспортный сертификат ~$300.
ROUTE = {"KR": {"name": "Корея (Encar)", "file": "abroad_encar.json", "delivery_eur": 2500, "export_eur": 450},
         "DE": {"name": "Германия (AutoScout24)", "file": "abroad_autoscout.json", "delivery_eur": 2500, "export_eur": 400},
         "AE": {"name": "ОАЭ (dubizzle)", "file": "abroad_dubizzle.json", "delivery_eur": 2200, "export_eur": 280}}
FUEL = {"бензин": "бензин", "дизель": "дизель", "гибрид": "гибрид_двс", "электро": "электро"}
MIN_N = 5


def _price_eur(src, y):
    if "med_export_eur" in y:
        return y["med_export_eur"]
    if "med_krw" in y:
        return y["med_krw"] * KRW_KZT / calc.EUR
    return y["med_aed"] * AED_KZT / calc.EUR


def _cc(y, k):
    fuel = y.get("f")
    if fuel == "электро":
        return 0
    if y.get("cc"):
        return int(y["cc"])
    v = y.get("v") or (k.get("v") if k.get("f") == fuel else None) or k.get("v")
    return int(round(float(v) * 1000)) if v else 2000


def landed(price_eur, fuel, cc, year, route):
    """Полная стоимость машины в РК на учёте, тг: цена + вывоз + доставка + платежи + рыночные расходы."""
    age = max(TODAY_YEAR - year, 0)
    best = None
    for mode in ("ДТ", "ПТД"):
        car = calc.Car(price_eur, FUEL[fuel], cc, age, mode, "третьи", TODAY_YEAR - year, route["delivery_eur"])
        r = calc.calc(car)
        if any(f in r["примечания"] for f in ("регистрация невозможна",)):
            continue
        total = r["стоимость_кзт"] + route["export_eur"] * calc.EUR + r["итого_с_рыночными"]
        if best is None or total < best[0]:
            best = (total, mode, r)
    return best


def rows():
    kd = kolesa.load()
    out = []
    for code, route in ROUTE.items():
        try:
            src = json.loads((RAW / route["file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for slug, years in src["models"].items():
            for ys, y in years.items():
                m = kolesa.market(slug, int(ys), kd)
                if not y or not m or y.get("n", 0) < MIN_N or y.get("f") not in FUEL:
                    continue
                p = _price_eur(src, y)
                cc = _cc(y, m)
                tot, mode, r = landed(p, y["f"], cc, int(ys), route)
                out.append({"категория": "Легковые", "страна": route["name"], "модель": kolesa.NAMES.get(slug, slug), "slug": slug,
                            "год": int(ys), "топливо": y["f"], "объём": cc, "пробег_там": y.get("km"),
                            "объявлений_там": y["n"], "цена_там_кзт": round(p * calc.EUR),
                            "платежи_кзт": r["итого_обязательные"], "режим": mode,
                            "доставка_и_услуги_кзт": round(tot - p * calc.EUR - r["итого_обязательные"]),
                            "итого_ввоз_кзт": round(tot), "kolesa_медиана": m["med"], "kolesa_25": m["p25"],
                            "kolesa_объявлений": m["n"], "kolesa_топливо": m.get("f"), "kolesa_объём": m.get("v"),
                            "выгода_кзт": round(m["med"] - tot), "выгода_pct": round(100 * (m["med"] - tot) / m["med"], 1),
                            "выгода_к_25_кзт": round(m["p25"] - tot), "kolesa_url": m["url"],
                            "детали": f"{y['f']}, {cc / 1000:.1f} л" if cc else y["f"]})
    return sorted(out, key=lambda r: -r["выгода_кзт"])


def all_rows():
    from abroad import deals_machines
    return sorted(rows() + deals_machines.rows(), key=lambda r: -r["выгода_кзт"])


RELIABLE = 10   # объявлений и там, и на Kolesa — меньше в рейтинг не берём


def summary(rs):
    """По модели и стране: в скольких годах ввоз дешевле Kolesa, медиана выгоды и лучший год."""
    import statistics
    groups = {}
    for r in rs:
        groups.setdefault((r["категория"], r["модель"], r["страна"]), []).append(r)
    out = []
    for (cat, model, country), g in groups.items():
        best = max(g, key=lambda r: r["выгода_кзт"])
        out.append({"категория": cat, "модель": model, "страна": country, "годов": len(g),
                    "в_плюсе": sum(r["выгода_кзт"] > 0 for r in g),
                    "медиана_выгоды_кзт": round(statistics.median(r["выгода_кзт"] for r in g)),
                    "лучший_год": best["год"], "лучшая_выгода_кзт": best["выгода_кзт"],
                    "лучшая_выгода_pct": best["выгода_pct"], "лучший_итого_кзт": best["итого_ввоз_кзт"],
                    "лучший_kolesa_кзт": best["kolesa_медиана"]})
    return sorted(out, key=lambda r: -r["медиана_выгоды_кзт"])


def compute():
    """Для сайта и приложения: надёжные пары модель-год и сводка по моделям."""
    from abroad import deals_machines as M

    def ok(r):
        need_abroad, need_kolesa = r.get("порог") or (RELIABLE, RELIABLE)
        return r["объявлений_там"] >= need_abroad and r["kolesa_объявлений"] >= need_kolesa
    rs = [r for r in all_rows() if ok(r)]
    keep = ("категория", "модель", "страна", "год", "детали", "режим", "пробег_там", "объявлений_там",
            "kolesa_объявлений", "цена_там_кзт", "платежи_кзт", "доставка_и_услуги_кзт", "итого_ввоз_кзт",
            "kolesa_медиана", "kolesa_25", "выгода_кзт", "выгода_pct", "выгода_к_25_кзт", "kolesa_url")
    routes = {**ROUTE, "EU_T": M.ROUTE_DE, "EU_M": M.ROUTE_MOTO}
    return {"date": kolesa.load().get("date"), "reliable": RELIABLE, "reliable_other": [M.MIN_ABROAD, M.MIN_KOLESA],
            "routes": routes,
            "rows": [{k: r.get(k) for k in keep} for r in rs], "summary": summary(rs)}


def main():
    rs = all_rows()
    OUT.mkdir(exist_ok=True)
    with open(OUT / "abroad_deals.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rs for k in r)))
        w.writeheader()
        w.writerows(rs)
    print(len(rs), "пар модель-год")
    for r in rs[:40]:
        print(f"{r['модель']:<28}{r['год']} {r['страна']:<22} {(r.get('детали') or '')[:14]:<14} там {r['цена_там_кзт']/1e6:6.1f} "
              f"ввоз {r['итого_ввоз_кзт']/1e6:6.1f} ({r['режим']}) Kolesa {r['kolesa_медиана']/1e6:6.1f} "
              f"выгода {r['выгода_кзт']/1e6:+5.1f} млн ({r['выгода_pct']:+.0f}%) n={r['объявлений_там']}/{r['kolesa_объявлений']}")


if __name__ == "__main__":
    main()
