"""Цены объявлений Encar (Корея) по моделям из kolesa_prices.json — медиана по году выпуска.

Бережно: один запрос в 2,5 с, остановка при ответе дольше 10 с или ошибке. Цена на Encar — в 만원 (10 000 вон).
Исключены LPG, аренда и лизинг. Запуск: python -m abroad.encar
"""
import json
import re
import statistics
import time
import urllib.parse
import urllib.request

from paths import RAW

OUT = RAW / "abroad_encar.json"
# адрес Kolesa → (производитель, группа моделей, Y — корейская марка / N — импорт)
MAP = {
    "hyundai/tucson": ("현대", "투싼", "Y"), "hyundai/santa-fe": ("현대", "싼타페", "Y"),
    "hyundai/elantra": ("현대", "아반떼", "Y"), "hyundai/sonata": ("현대", "쏘나타", "Y"),
    "hyundai/palisade": ("현대", "팰리세이드", "Y"), "kia/sportage": ("기아", "스포티지", "Y"),
    "kia/k5": ("기아", "K5", "Y"), "kia/sorento": ("기아", "쏘렌토", "Y"), "kia/seltos": ("기아", "셀토스", "Y"),
    "kia/carnival": ("기아", "카니발", "Y"), "chevrolet/malibu": ("쉐보레(GM대우)", "말리부", "Y"),
    "toyota/camry": ("도요타", "캠리", "N"), "toyota/rav-4": ("도요타", "RAV4", "N"),
    "lexus/serii-rx-vse": ("렉서스", "RX", "N"), "lexus/serii-lx-vse": ("렉서스", "LX", "N"),
    "bmw/x5": ("BMW", "X5", "N"), "bmw/5-series": ("BMW", "5시리즈", "N"),
    "mercedes-benz/e-klasse": ("벤츠", "E-클래스", "N"), "mercedes-benz/gle-klasse": ("벤츠", "GLE-클래스", "N"),
    "volkswagen/tiguan": ("폭스바겐", "티구안", "N"),
}
FUEL = {"가솔린": "бензин", "디젤": "дизель", "가솔린+전기": "гибрид", "전기": "электро"}
YEARS = range(2016, 2026)


def _get(make, group, ctype, year):
    q = (f"(And.Hidden.N._.CarType.{ctype}._.(C.Manufacturer.{make}._.ModelGroup.{group}.)"
         f"_.Year.range({year}00..{year}12).)")
    url = ("https://api.encar.com/search/car/list/general?count=true&q=" + urllib.parse.quote(q, safe="()._")
           + "&sr=" + urllib.parse.quote("|ModifiedDate|0|100"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    t = time.time()
    from actualize import _ctx
    with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
        d = json.load(r)
    return d, time.time() - t


def summarize(rows):
    ok = [r for r in rows if r.get("FuelType") in FUEL and r.get("SellType") == "일반" and r.get("Price", 0) > 100
          and r.get("Price") < 99999]
    if not ok:
        return None
    fuel = max(FUEL, key=lambda f: sum(r["FuelType"] == f for r in ok))
    same = [r for r in ok if r["FuelType"] == fuel]
    vols = [m.group(1) for r in same if (m := re.search(r"(\d\.\d)", r.get("Badge", "")))]
    prices = sorted(r["Price"] * 10_000 for r in same)
    return {"n": len(same), "med_krw": statistics.median(prices),
            "p25_krw": prices[len(prices) // 4], "p75_krw": prices[(3 * len(prices)) // 4],
            "km": round(statistics.median(r.get("Mileage", 0) for r in same)),
            "f": FUEL[fuel], "v": max(set(vols), key=vols.count) if vols else None}


def main():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"source": "api.encar.com", "date": time.strftime("%Y-%m-%d"), "models": {}}
    for slug, (make, group, ctype) in MAP.items():
        for y in YEARS:
            if str(y) in data["models"].get(slug, {}):
                continue
            d, dt = _get(make, group, ctype, y)
            s = summarize(d.get("SearchResults", []))
            if s:
                s["found"] = d.get("Count", 0)
            data["models"].setdefault(slug, {})[str(y)] = s
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(slug, y, s and (s["n"], s["med_krw"], s["f"], s["v"]), f"{dt:.1f}s", flush=True)
            if dt > 10:
                raise SystemExit("Encar отвечает медленно — останавливаюсь")
            time.sleep(2.5)


if __name__ == "__main__":
    main()
