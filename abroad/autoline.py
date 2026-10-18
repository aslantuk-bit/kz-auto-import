"""Цены объявлений Autoline (autoline.info, machineryline.info, agroline.com) — тягачи, экскаваторы, погрузчики, тракторы.

Бережно: один запрос в 30 с, остановка при ответе дольше 10 с. Цены в евро; объявления «цена по запросу» отсекает
фильтр pr0. Великобритания и Ирландия исключены — там техника праворульная. Запуск: python -m abroad.autoline
"""
import html
import json
import re
import statistics
import time
import urllib.request

from paths import RAW

OUT = RAW / "abroad_autoline.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0 Safari/537.36")
RHD = ("United Kingdom", "Ireland")
PAUSE = 30   # и 3 с, и 8 с Autoline счёл слишком частыми (429)
YEARS = range(2014, 2025)
AL, ML = "https://autoline.info/-/truck-tractors/", "https://machineryline.info/-/"
TRACKED = r"\b(?:32[0-5]|PC ?2[0-4]0|R ?2[0-2]0(?!W)|HX ?2[0-2]0|DX ?22[05](?!W)|DX ?210(?!W)|EC ?2[0-2]0|JS ?2(?:05|10|20)(?!W)|ZX ?2[01]0)"
WHEELED = r"\b(?:R ?1[46]0W|HW ?1[46]0|EW ?1[46]0|DX ?1[46]0W|JS ?1[46][05]W|M ?31[5-8])"
# ключ — сегмент, как в deals_machines.SEGMENTS; значение — [(адрес выдачи, шаблон модели в заголовке)]
MAP = {
    "tyagach|volvo-fh": [(AL + "Volvo/FH--c42tm2819m200", r"\bFH")],
    "tyagach|daf-xf": [(AL + "DAF/XF--c42tm2525m3", r"\bXF")],
    "tyagach|man-tgx": [(AL + "MAN/TGX--c42tm2665m394", r"\bTGX")],
    "tyagach|actros": [(AL + "Mercedes-Benz/Actros--c42tm2675m888", r"Actros")],
    "tyagach|scania-rs": [(AL + "Scania--c42tm2742", r"\b[RS] ?\d{3}|[RS]-series")],
    "ekskavator|gusenichnyj-20-25": [(ML + f"tracked-excavators/{b}--c167tm{i}", TRACKED) for b, i in (
        ("Caterpillar", 2512), ("Komatsu", 2637), ("Hyundai", 2611), ("Doosan", 3881), ("Volvo", 2819), ("JCB", 2618),
        ("Hitachi", 2604))],
    "ekskavator|kolesnyj-14-16": [(ML + f"wheel-excavators/{b}--c164tm{i}", WHEELED) for b, i in (
        ("Caterpillar", 2512), ("Hyundai", 2611), ("Doosan", 3881), ("Volvo", 2819), ("JCB", 2618))],
}


def get(url):
    """Страница выдачи; на 429 — пауза 2 мин и один повтор, потом остановка."""
    import urllib.error
    from actualize import _ctx
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    for attempt in (1, 2):
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
                return r.read().decode("utf-8", "replace"), time.time() - t
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise SystemExit(f"Autoline ответил {e.code} — останавливаюсь")
            time.sleep(120)


def parse(h, year):
    rows = []
    for p in h.split("sl-item__title")[1:]:
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", p[:4000])))
        pm = re.search(r"€([\d,]+)", t)
        ym = re.search(r"\b(19|20)(\d{2})\b(?![\d,])", t[pm.end():] if pm else t)
        if not pm or any(c in t for c in RHD):
            continue
        y = int(ym.group(1) + ym.group(2)) if ym else None
        if year is not None and y != year or y is None:
            continue
        km = re.search(r"([\d,]+) km", t)
        mh = re.search(r"([\d,]+) m/h", t)
        rows.append({"y": y, "eur": int(pm.group(1).replace(",", "")), "km": int(km.group(1).replace(",", "")) if km else None,
                     "mh": int(mh.group(1).replace(",", "")) if mh else None, "t": t[:120]})
    return rows


def summarize(rows):  # noqa: D103 — оставлено для сводки по одному году
    ok = sorted(r["eur"] for r in rows if r["eur"] >= 3000)
    if not ok:
        return None
    med = statistics.median(ok)
    ok = [p for p in ok if med * 0.35 < p < med * 2.8]
    kms = [r["km"] for r in rows if r.get("km")]
    mhs = [r["mh"] for r in rows if r.get("mh")]
    return {"n": len(ok), "med_eur": statistics.median(ok), "p25_eur": ok[len(ok) // 4],
            "p75_eur": ok[(3 * len(ok)) // 4], "km": round(statistics.median(kms)) if kms else None,
            "mh": round(statistics.median(mhs)) if mhs else None}


POOLED = ("ekskavator|gusenichnyj-20-25", "ekskavator|kolesnyj-14-16")   # мало объявлений на год — все годы разом
POOL_PAGES = 4


def pooled(data, key):
    """Одна выдача на все годы по каждой марке, по POOL_PAGES страниц; годы разносятся при разборе."""
    done = data.setdefault("pooled_done", [])
    for url, pat in MAP[key]:
        if url in done:
            continue
        for page in range(1, POOL_PAGES + 1):
            h, _ = get(f"{url}?ym0={YEARS[0]}&ym1={YEARS[-1]}&pr0=1000" + (f"&page={page}" if page > 1 else ""))
            got = [r for r in parse(h, None) if re.search(pat, r["t"], re.I)]
            for r in got:
                data["rows"].setdefault(key, {}).setdefault(str(r["y"]), []).append(r)
            time.sleep(PAUSE)
            if h.count("sl-item__title") < 25:
                break
        done.append(url)
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(key, url.rsplit("/", 1)[-1], sum(len(v) for v in data["rows"].get(key, {}).values()), flush=True)


def main():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"source": "autoline.info / machineryline.info", "date": time.strftime("%Y-%m-%d"), "rows": {}}
    for key, sources in MAP.items():
        if key in POOLED:
            pooled(data, key)
            continue
        for y in YEARS:
            if str(y) in data["rows"].get(key, {}):
                continue
            rows = []
            for url, pat in sources:
                for page in (1, 2):
                    h, dt = get(f"{url}?ym0={y}&ym1={y}&pr0=1000" + (f"&page={page}" if page > 1 else ""))
                    if dt > 10:
                        raise SystemExit("Autoline отвечает медленно — останавливаюсь")
                    rows += [r for r in parse(h, y) if re.search(pat, r["t"], re.I)]
                    time.sleep(PAUSE)
                    if h.count("sl-item__title") < 25:
                        break
            data["rows"].setdefault(key, {})[str(y)] = rows
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            s = summarize(rows)
            print(key, y, len(rows), s and (s["n"], s["med_eur"]), flush=True)


if __name__ == "__main__":
    main()
