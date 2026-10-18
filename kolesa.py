"""Сравнение «ввезти самому или купить в Казахстане» по ценам объявлений Kolesa.kz.

Данные — sources/raw/kolesa_prices.json: по модели и году выпуска медиана, 25-й и 75-й процентили цен
из первой страницы выдачи Kolesa (до 20 объявлений, без аварийных и выбросов), общее число объявлений,
типичный объём и топливо. Собраны бережно через браузер (1 запрос в 2,5–3,5 с). Цены объявлений —
цены продавцов, а не сделок; машины в объявлениях уже растаможены и стоят на учёте в РК.
"""
import json

from paths import RAW

FILE = RAW / "kolesa_prices.json"

NAMES = {   # адрес модели на Kolesa → название
    "toyota/camry": "Toyota Camry", "toyota/rav-4": "Toyota RAV4", "toyota/land-cruiser-prado": "Toyota Land Cruiser Prado",
    "toyota/land-cruiser": "Toyota Land Cruiser", "toyota/corolla": "Toyota Corolla", "toyota/highlander": "Toyota Highlander",
    "lexus/serii-rx-vse": "Lexus RX", "lexus/serii-lx-vse": "Lexus LX", "hyundai/tucson": "Hyundai Tucson",
    "hyundai/santa-fe": "Hyundai Santa Fe", "hyundai/elantra": "Hyundai Elantra", "hyundai/sonata": "Hyundai Sonata",
    "hyundai/palisade": "Hyundai Palisade", "hyundai/creta": "Hyundai Creta", "kia/sportage": "Kia Sportage",
    "kia/k5": "Kia K5", "kia/sorento": "Kia Sorento", "kia/rio": "Kia Rio", "kia/seltos": "Kia Seltos",
    "kia/carnival": "Kia Carnival", "chevrolet/cobalt": "Chevrolet Cobalt", "chevrolet/onix": "Chevrolet Onix",
    "chevrolet/tracker": "Chevrolet Tracker", "chevrolet/malibu": "Chevrolet Malibu", "volkswagen/polo": "Volkswagen Polo",
    "volkswagen/tiguan": "Volkswagen Tiguan", "volkswagen/id4": "Volkswagen ID.4", "bmw/x5": "BMW X5",
    "bmw/5-series": "BMW 5 серии", "mercedes-benz/e-klasse": "Mercedes-Benz E-класс",
    "mercedes-benz/gle-klasse": "Mercedes-Benz GLE", "haval/jolion": "Haval Jolion", "haval/h6": "Haval H6",
    "chery/tiggo-7-pro": "Chery Tiggo 7 Pro", "chery/tiggo-8-pro": "Chery Tiggo 8 Pro", "geely/monjaro": "Geely Monjaro",
    "geely/coolray": "Geely Coolray", "zeekr/001": "Zeekr 001", "byd/song-plus": "BYD Song Plus",
    "changan/cs55-plus": "Changan CS55 Plus", "nissan/x-trail": "Nissan X-Trail", "honda/cr-v": "Honda CR-V",
    "mitsubishi/outlander": "Mitsubishi Outlander", "subaru/forester": "Subaru Forester",
}
FUEL = {"бензин": "бензин", "дизель": "дизель", "гибрид": "гибрид", "электричество": "электро", "газ": "газ"}
MIN_ADS = 3   # меньше объявлений на первой странице — медиану не показываем


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"date": None, "models": {}}


def models(data=None):
    """[(адрес, название)] моделей, по которым есть хотя бы один год с данными."""
    data = data or load()
    return [(k, NAMES.get(k, k)) for k, v in data["models"].items()
            if any(isinstance(y, dict) and y.get("n", 0) >= MIN_ADS for y in v.get("years", {}).values())]


def search_url(slug, year):
    return f"https://kolesa.kz/cars/{slug}/?year[from]={year}&year[to]={year}"


def market(slug, year, data=None):
    """Цена на Kolesa для модели и года: {med, p25, p75, n, found, v, f, url} или None."""
    data = data or load()
    y = data["models"].get(slug, {}).get("years", {}).get(str(year))
    if not y or y.get("n", 0) < MIN_ADS:
        return None
    return {**y, "url": search_url(slug, year)}


def compare(slug, year, landed_kzt, data=None):
    """Полная стоимость ввоза против медианы объявлений. diff > 0 — ввезти дешевле рынка."""
    m = market(slug, year, data)
    if m is None:
        return None
    return {**m, "landed": landed_kzt, "diff": m["med"] - landed_kzt, "name": NAMES.get(slug, slug)}


def _stats(prices):
    s = sorted(prices)
    if not s:
        return None, None, None

    def q(p):
        i = (len(s) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(s) - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (i - lo))
    return q(0.5), q(0.25), q(0.75)


def parse_page(html, year):
    """Страница выдачи Kolesa → {n, found, med, p25, p75, v, f}; тот же разбор, что при сборе в браузере."""
    import re
    from collections import Counter
    from html import unescape
    m = re.search(r"Найдено((?:&nbsp;|[\s\d ])+)объявлен", html)
    found = int(re.sub(r"\D", "", m.group(1).replace("&nbsp;", ""))) if m else 0
    ads = []
    for part in re.split(r'class="a-card\s', html)[1:]:
        t = re.sub(r"[\s   ]+", " ", unescape(re.sub(r"<[^>]+>", " ", part[:8000])))
        pm, ym = re.search(r"(\d{1,3}(?: \d{3})+) ₸", t), re.search(r"(\d{4}) г\.", t)
        if not pm or not ym or int(ym.group(1)) != year or re.search(r"аварийн|на запчаст|не на ходу", t, re.I):
            continue
        vm, fm = re.search(r"(\d\.\d) л", t), re.search(r"бензин|дизель|гибрид|электричество|газ", t)
        ads.append((int(re.sub(r"\D", "", pm.group(1))), vm and vm.group(1), fm and fm.group(0)))
    ps = [p for p, _, _ in ads]
    med, _, _ = _stats(ps)
    ps = [p for p in ps if med and med * 0.4 < p < med * 2.5]
    med, p25, p75 = _stats(ps)
    mode = lambda xs: Counter(x for x in xs if x).most_common(1)[0][0] if any(xs) else None  # noqa: E731
    return {"n": len(ps), "found": found, "med": med, "p25": p25, "p75": p75,
            "v": mode([v for _, v, _ in ads]), "f": FUEL.get(mode([f for _, _, f in ads]), mode([f for _, _, f in ads]))}


def fetch_live(slug, year):
    """Один запрос к Kolesa для любой модели. Kolesa часто отвечает программам кодом 418 — тогда RuntimeError."""
    import urllib.request
    from actualize import _ctx
    req = urllib.request.Request(search_url(slug, year), headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/141.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml", "Accept-Language": "ru-RU,ru;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ctx()) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        raise RuntimeError(f"Kolesa не ответил программе ({e}); откройте выдачу в браузере") from e
    res = parse_page(html, year)
    data = load()
    data.setdefault("models", {}).setdefault(slug, {"years": {}})["years"][str(year)] = res
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
