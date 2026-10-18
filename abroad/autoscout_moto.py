"""Цены мотоциклов на AutoScout24 (8 стран ЕС) по моделям, которые чаще всего продают на Kolesa, — по году регистрации.

Бережно: один запрос в 3 с, остановка при ответе дольше 10 с. Цена — брутто; у дилеров с вычитаемым НДС при вывозе
из ЕС — нетто (делим на 1,19 как ориентир). Запуск: python -m abroad.autoscout_moto
"""
import json
import re
import statistics
import time
import urllib.request

from paths import RAW

OUT = RAW / "abroad_autoscout_moto.json"
COUNTRIES = "D%2CA%2CB%2CE%2CF%2CI%2CL%2CNL"
YEARS = range(2012, 2026)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0 Safari/537.36")
# модель → (адрес на AutoScout24, шаблон заголовка Kolesa, объём см³, мощность кВт)
MODELS = {
    "Yamaha YZF-R1": ("yamaha/yzf-r1", r"YZF-?R1\b(?!25)", 998, 147), "Yamaha YZF-R6": ("yamaha/yzf-r6", r"YZF-?R6", 599, 87),
    "Yamaha YZF-R3": ("yamaha/yzf-r3", r"YZF-?R3", 321, 31), "Yamaha MT-09": ("yamaha/mt-09", r"MT-?09", 890, 87),
    "Yamaha MT-07": ("yamaha/mt-07", r"MT-?07", 689, 54),
    "Honda CBR 600RR": ("honda/cbr-600", r"CBR ?600", 599, 89), "Honda CBR 1000RR": ("honda/cbr-1000", r"CBR ?1000|Fireblade", 999, 140),
    "Honda Africa Twin": ("honda/crf-1100", r"Africa Twin", 1084, 75), "Honda Gold Wing": ("honda/gl-1800", r"GL ?1800|Gold ?Wing", 1833, 93),
    "Kawasaki Ninja 650": ("kawasaki/ninja-650", r"Ninja 650", 649, 50), "Kawasaki ZX-6R": ("kawasaki/ninja-zx-6r", r"ZX-?6", 636, 95),
    "Kawasaki Ninja 400": ("kawasaki/ninja-400", r"Ninja 400", 399, 33), "Kawasaki ZX-10R": ("kawasaki/ninja-zx-10r", r"ZX-?10", 998, 150),
    "Suzuki GSX-R1000": ("suzuki/gsx-r-1000", r"GSX-?R ?1000", 999, 148), "Suzuki GSX-R750": ("suzuki/gsx-r-750", r"GSX-?R ?750", 750, 110),
    "Suzuki Boulevard M109R": ("suzuki/vzr-1800", r"M ?109|VZR ?1800", 1783, 92),
    "BMW S 1000 RR": ("bmw/s-1000-rr", r"S ?1000 ?RR", 999, 152),
    "BMW R 1200/1250 GS": ("bmw/r-1250-gs", r"R ?12[05]0 ?GS", 1254, 100),
    "Harley-Davidson Sportster": ("harley-davidson/sportster", r"Sportster|XL ?883|XL ?1200", 1200, 50),
    "Harley-Davidson Fat Boy": ("harley-davidson/fat-boy", r"Fat ?Boy", 1745, 69),
    "Harley-Davidson Road Glide": ("harley-davidson/road-glide", r"Road Glide", 1868, 70),
}


def _page(slug, year):
    from actualize import _ctx
    url = (f"https://www.autoscout24.de/lst-moto/{slug}?fregfrom={year}&fregto={year}&cy={COUNTRIES}"
           "&damaged_listing=exclude")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
        h = r.read().decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    pp = json.loads(m.group(1))["props"]["pageProps"] if m else {}
    return pp.get("listings", []), pp.get("numberOfResults", 0), time.time() - t


def summarize(ls):
    rows = []
    for x in ls:
        p = (x.get("price") or {})
        eur = p.get("priceRaw") or 0
        if eur > 500:
            rows.append(eur / 1.19 if "ausweisbar" in (p.get("vatLabel") or "") else eur)
    if len(rows) < 3:
        return None
    rows.sort()
    return {"n": len(rows), "med_export_eur": round(statistics.median(rows)), "p25_export_eur": round(rows[len(rows) // 4])}


def main():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"source": "autoscout24.de (8 стран ЕС)", "date": time.strftime("%Y-%m-%d"), "models": {}}
    for name, (slug, _, _, _) in MODELS.items():
        for y in YEARS:
            if str(y) in data["models"].get(name, {}):
                continue
            ls, found, dt = _page(slug, y)
            if dt > 10:
                raise SystemExit("AutoScout24 отвечает медленно — останавливаюсь")
            s = summarize(ls)
            if s:
                s["found"] = found
            data["models"].setdefault(name, {})[str(y)] = s
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(name, y, found, s and (s["n"], s["med_export_eur"]), flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
