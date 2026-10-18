"""Мотоциклы и спецтехника: цена за рубежом + доставка + платежи против цен Kolesa по той же модели и году.

Kolesa — sources/raw/kolesa_machines.json (собрано в браузере: заголовок, цена, год по каждому объявлению).
За рубежом — abroad_autoline.json (тягачи, экскаваторы; сырые объявления по годам) и abroad_autoscout_moto.json.
Платежи — vehicles.calc_machine, самый дешёвый маршрут из третьих стран, на котором регистрация возможна.
На Kolesa по каждой модели мало объявлений одного года, поэтому порог ниже, чем у легковых, — MIN_KOLESA.
"""
import json
import re
import statistics
from dataclasses import replace

import calc
import vehicles as V
from abroad import autoline, autoscout_moto
from paths import RAW

YEAR = calc.AS_OF.year
MIN_KOLESA, MIN_ABROAD = 4, 5
# Доставка до границы ЕАЭС и вывоз, EUR — ориентиры («Г»): тягач своим ходом €1,8 тыс.; экскаватор на трале
# €6 тыс.; мотоцикл в сборном грузе €800; вывозные документы €400 / €400 / €200.
ROUTE_DE = {"name": "ЕС (Autoline)", "delivery": {"tractor_unit": 1800, "excavator": 6000}, "export": 400}
ROUTE_MOTO = {"name": "ЕС (AutoScout24)", "delivery": 800, "export": 200}
TRACTOR = {"kind": "tractor_unit", "mass": 18.0, "cc": 12800, "eco4": True}
SEGMENTS = {   # сегмент → (раздел и марки Kolesa, шаблон заголовка, параметры расчёта, ключ Autoline)
    "Тягач Volvo FH": ("tyagach", ["volvo"], r"\bFH", TRACTOR, "tyagach|volvo-fh"),
    "Тягач DAF XF": ("tyagach", ["daf"], r"\bXF", TRACTOR, "tyagach|daf-xf"),
    "Тягач MAN TGX": ("tyagach", ["man"], r"\bTGX", TRACTOR, "tyagach|man-tgx"),
    "Тягач Mercedes-Benz Actros": ("tyagach", ["mercedes-benz"], r"Actros", TRACTOR, "tyagach|actros"),
    "Тягач Scania R/S": ("tyagach", ["scania"], r"[RS]-Series|\b[RS] ?\d{3}", TRACTOR, "tyagach|scania-rs"),
    "Экскаватор гусеничный 20–25 т": ("ekskavatory", ["caterpillar", "komatsu", "hyundai", "doosan", "volvo", "jcb",
                                                       "hitachi"], autoline.TRACKED, {"kind": "excavator", "kw": 110},
                                       "ekskavator|gusenichnyj-20-25"),
    "Экскаватор колёсный 14–16 т": ("ekskavatory", ["caterpillar", "hyundai", "doosan", "volvo", "jcb"], autoline.WHEELED,
                                     {"kind": "excavator", "kw": 100}, "ekskavator|kolesnyj-14-16"),
}
KOLESA_PATH = {"tyagach": "spectehnika/gruzoviki/tyagach", "ekskavatory": "spectehnika/gruzovaja-tehnika/ekskavatory",
               "moto": "mototehnika/motocikly"}


def _load(name):
    try:
        return json.loads((RAW / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _kolesa(kd, section, brands, pattern):
    """Объявления Kolesa сегмента: [(год, цена)] без аварийных и сцепок."""
    found = []
    for b in brands:
        for title, price, year, _km, _vol, bad in kd.get(f"{KOLESA_PATH[section]}|{b}", {}).get("rows", []):
            if not bad and year and price > 0 and re.search(pattern, title, re.I):
                found.append((year, price))
    return found


def landed(price_eur, year, params, delivery, export_eur):
    """Ввоз под ключ, тг: самый дешёвый маршрут из третьих стран с возможной регистрацией → (итого, режим, расчёт)."""
    m = V.Machine(params["kind"], price_eur, max(YEAR - year, 0), YEAR - year, delivery,
                  **{k: v for k, v in params.items() if k != "kind"})
    best = None
    for _rid, mode, origin in V.routes_for(m):
        if origin != "третьи":
            continue
        r = V.calc_machine(replace(m, mode=mode, origin=origin))
        if re.search(calc.BLOCKING, r["примечания"]):
            continue
        tot = r["стоимость_кзт"] + export_eur * calc.EUR + r["итого_с_рыночными"]
        if best is None or tot < best[0]:
            best = (tot, mode, r)
    return best


def _clean(ads):
    if not ads:
        return ads
    med = statistics.median(p for _, p in ads)
    return [(y, p) for y, p in ads if med * 0.25 < p < med * 4]


def _row(cat, model, country, year, ads, abroad_eur, n_abroad, params, delivery, export_eur, url, details):
    tot, mode, r = landed(abroad_eur, year, params, delivery, export_eur)
    prices = sorted(p for _, p in ads)
    med = statistics.median(prices)
    return {"категория": cat, "страна": country, "модель": model, "год": year, "детали": details, "режим": mode,
            "пробег_там": None, "объявлений_там": n_abroad, "kolesa_объявлений": len(prices),
            "цена_там_кзт": round(abroad_eur * calc.EUR), "платежи_кзт": r["итого_обязательные"],
            "доставка_и_услуги_кзт": round(tot - abroad_eur * calc.EUR - r["итого_обязательные"]),
            "итого_ввоз_кзт": round(tot), "kolesa_медиана": round(med), "kolesa_25": prices[len(prices) // 4],
            "выгода_кзт": round(med - tot), "выгода_pct": round(100 * (med - tot) / med, 1),
            "выгода_к_25_кзт": round(prices[len(prices) // 4] - tot), "kolesa_url": url,
            "порог": (MIN_ABROAD, MIN_KOLESA)}


def _machines(kd):
    al = _load("abroad_autoline.json").get("rows", {})
    out = []
    for model, (section, brands, pat, params, akey) in SEGMENTS.items():
        if params["kind"] == "excavator":
            continue
        ads = _kolesa(kd, section, brands, pat)
        for ys, raw in al.get(akey, {}).items():
            y = int(ys)
            s = autoline.summarize(raw or [])
            same = _clean([a for a in ads if a[0] == y])
            if not s or s["n"] < MIN_ABROAD or len(same) < MIN_KOLESA:
                continue
            base = f"https://kolesa.kz/{KOLESA_PATH[section]}/" + (f"{brands[0]}/" if len(brands) == 1 else "")
            out.append(_row("Спецтехника", model, ROUTE_DE["name"], y, same, s["med_eur"], s["n"], params,
                            ROUTE_DE["delivery"][params["kind"]], ROUTE_DE["export"],
                            base + f"?year[from]={y}&year[to]={y}",
                            "тягач, Евро-5+" if params["kind"] == "tractor_unit" else f"{params['kw']} кВт"))
    return out


def _per_listing(cat, model, country, ads, abroad, params, delivery, export_eur, url, details):
    """Когда на Kolesa по каждому году 1–3 объявления: каждое объявление сравниваем с ввозом того же года,
    строка модели — медианы по объявлениям. abroad(год) → (цена EUR, объявлений) или None."""
    cache, pairs = {}, []
    for y, price in _clean(ads):
        a = abroad(y)
        if not a or a[1] < MIN_ABROAD:
            continue
        if y not in cache:
            cache[y] = (a, landed(a[0], y, params, delivery, export_eur))
        pairs.append((y, price, cache[y]))
    if len(pairs) < MIN_KOLESA:
        return None
    med = statistics.median
    years = sorted(y for y, _, _ in pairs)
    tot = med([c[1][0] for _, _, c in pairs])
    kol = med([p for _, p, _ in pairs])
    gain = med([p - c[1][0] for _, p, c in pairs])
    there = med([c[0][0] for _, _, c in pairs]) * calc.EUR
    pay = med([c[1][2]["итого_обязательные"] for _, _, c in pairs])
    modes = [c[1][1] for _, _, c in pairs]
    p25 = sorted(p for _, p, _ in pairs)[len(pairs) // 4]
    return {"категория": cat, "страна": country, "модель": model, "год": int(med(years)),
            "детали": f"{details}, годы {years[0]}–{years[-1]}", "режим": max(set(modes), key=modes.count),
            "пробег_там": None, "объявлений_там": min(c[0][1] for _, _, c in pairs), "kolesa_объявлений": len(pairs),
            "цена_там_кзт": round(there), "платежи_кзт": round(pay), "доставка_и_услуги_кзт": round(tot - there - pay),
            "итого_ввоз_кзт": round(tot), "kolesa_медиана": round(kol), "kolesa_25": p25, "выгода_кзт": round(gain),
            "выгода_pct": round(100 * gain / kol, 1), "выгода_к_25_кзт": round(p25 - tot), "kolesa_url": url,
            "порог": (MIN_ABROAD, MIN_KOLESA), "по_объявлениям": True}


def _excavators(kd):
    al = _load("abroad_autoline.json").get("rows", {})
    out = []
    for model, (section, brands, pat, params, akey) in SEGMENTS.items():
        if params["kind"] != "excavator":
            continue

        def abroad(y, akey=akey):
            s = autoline.summarize(al.get(akey, {}).get(str(y)) or [])
            return s and (s["med_eur"], s["n"])
        r = _per_listing("Спецтехника", model, ROUTE_DE["name"], _kolesa(kd, section, brands, pat), abroad, params,
                         ROUTE_DE["delivery"]["excavator"], ROUTE_DE["export"],
                         f"https://kolesa.kz/{KOLESA_PATH[section]}/", f"{params['kw']} кВт")
        if r:
            out.append(r)
    return out


def _moto(kd):
    mo = _load("abroad_autoscout_moto.json").get("models", {})
    out = []
    for model, (_slug, pat, cc, kw) in autoscout_moto.MODELS.items():
        brand = model.split()[0].lower()

        def abroad(y, model=model):
            s = mo.get(model, {}).get(str(y))
            return s and (s["med_export_eur"], s["n"])
        r = _per_listing("Мотоциклы", model, ROUTE_MOTO["name"], _kolesa(kd, "moto", [brand], pat), abroad,
                         {"kind": "moto", "cc": cc, "kw": kw}, ROUTE_MOTO["delivery"], ROUTE_MOTO["export"],
                         f"https://kolesa.kz/{KOLESA_PATH['moto']}/{brand}/", f"{cc} см³")
        if r:
            out.append(r)
    return out


def rows():
    kd = _load("kolesa_machines.json").get("rows", {})
    return _machines(kd) + _excavators(kd) + _moto(kd)
