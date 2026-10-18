"""Цены объявлений AutoScout24 (Германия) по моделям из kolesa_prices.json — медиана по году первой регистрации.

Бережно: один запрос в 3 с, остановка при ответе дольше 10 с. Цена — брутто с НДС 19%; у дилерских машин
с вычитаемым НДС (MwSt. ausweisbar) при вывозе из ЕС продают нетто — считаем и нетто. Запуск: python -m abroad.autoscout
"""
import json
import re
import statistics
import time
import urllib.request

from paths import RAW

OUT = RAW / "abroad_autoscout.json"
MAP = {   # адрес Kolesa → адрес модели на AutoScout24; Camry, Outlander, Zeekr, BYD в Германии почти не продают,
         # Polo там хэтчбек, а не седан из РФ — не сравниваем
    "toyota/rav-4": "toyota/rav-4", "toyota/land-cruiser-prado": "toyota/land-cruiser",
    "toyota/corolla": "toyota/corolla", "toyota/highlander": "toyota/highlander", "lexus/serii-rx-vse": "lexus/rx-(alle)",
    "hyundai/tucson": "hyundai/tucson", "hyundai/santa-fe": "hyundai/santa-fe", "kia/sportage": "kia/sportage",
    "kia/sorento": "kia/sorento", "volkswagen/tiguan": "volkswagen/tiguan",
"bmw/x5": "bmw/x5", "bmw/5-series": "bmw/5er-(alle)",
    "mercedes-benz/e-klasse": "mercedes-benz/e-klasse-(alle)", "mercedes-benz/gle-klasse": "mercedes-benz/gle-(alle)",
    "nissan/x-trail": "nissan/x-trail", "honda/cr-v": "honda/cr-v", 
    "subaru/forester": "subaru/forester",
}
FUEL = {"Benzin": "бензин", "Diesel": "дизель", "Elektro/Benzin": "гибрид", "Elektro": "электро",
        "Elektro/Diesel": "гибрид"}
YEARS = range(2016, 2026)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0 Safari/537.36")


def _page(slug, year, page):
    from actualize import _ctx
    url = (f"https://www.autoscout24.de/lst/{slug}?fregfrom={year}&fregto={year}&atype=C&cy=D&damaged_listing=exclude"
           f"&page={page}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
        h = r.read().decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    pp = json.loads(m.group(1))["props"]["pageProps"] if m else {}
    return pp.get("listings", []), pp.get("numberOfResults", 0), time.time() - t


def _row(x):
    v, p = x.get("vehicle", {}), x.get("price", {})
    cc = re.sub(r"\D", "", v.get("engineDisplacementInCCM") or "")
    return {"eur": p.get("priceRaw") or 0, "net": "ausweisbar" in (p.get("vatLabel") or ""),
            "fuel": FUEL.get(v.get("fuel")), "cc": int(cc) if cc else None,
            "km": int(re.sub(r"\D", "", v.get("mileageInKm") or "0") or 0)}


def summarize(rows):
    ok = [r for r in rows if r["fuel"] and r["eur"] > 1000]
    if not ok:
        return None
    fuel = max({r["fuel"] for r in ok}, key=lambda f: sum(r["fuel"] == f for r in ok))
    same = [r for r in ok if r["fuel"] == fuel]
    exp = sorted(r["eur"] / 1.19 if r["net"] else r["eur"] for r in same)   # цена при вывозе из ЕС
    ccs = [r["cc"] for r in same if r["cc"]]
    return {"n": len(same), "med_eur": statistics.median(r["eur"] for r in same),
            "med_export_eur": round(statistics.median(exp)), "p25_export_eur": round(exp[len(exp) // 4]),
            "p75_export_eur": round(exp[(3 * len(exp)) // 4]), "net_share": round(sum(r["net"] for r in same) / len(same), 2),
            "km": round(statistics.median(r["km"] for r in same)), "f": fuel,
            "cc": statistics.median_low(ccs) if ccs else None}


def main():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"source": "autoscout24.de", "date": time.strftime("%Y-%m-%d"), "models": {}}
    for k, slug in MAP.items():
        for y in YEARS:
            if str(y) in data["models"].get(k, {}):
                continue
            rows, found = [], 0
            for page in (1, 2):
                ls, found, dt = _page(slug, y, page)
                rows += [_row(x) for x in ls]
                if dt > 10:
                    raise SystemExit("AutoScout24 отвечает медленно — останавливаюсь")
                time.sleep(3)
                if found <= 20:
                    break
            s = summarize(rows)
            if s:
                s["found"] = found
            data["models"].setdefault(k, {})[str(y)] = s
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(k, y, found, s and (s["n"], s["med_export_eur"], s["f"], s["cc"]), flush=True)


if __name__ == "__main__":
    main()
