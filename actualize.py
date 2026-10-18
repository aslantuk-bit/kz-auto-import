"""Актуализация базы: курсы НБРК, сверка с текстами актов, самопроверка калькулятора и пересборка.

Что делает run():
1. Курсы — официальные курсы НБРК на сегодня; обновляются сами (calc_params.json → fx).
2. Акты — метка «Обновленный с изменениями на» на зеркале ИЗПИ (zakon.uchet.kz) против редакции
   в watch.json; свежая редакция ЕТТ (гр. 87) на сайте ЕЭК. Новая редакция — «нужна проверка».
3. Ставки в текстах — НДС, МРП, таможенный сбор, порог акциза 10%. Найденное значение сравнивается
   с calc_params.json; расхождение не применяется само, а предлагается (apply_param).
4. Календарь — МРП текущего года, давность сверки.
5. Пересборка — база, сценарии, «Как сэкономить», Excel, data.json для сайта.
6. Самопроверка — test_calc (нормы и сверка констант с базой), сетка сценариев, сверка JS (если есть node).
Отчёт — out/актуализация.json, журнал — out/актуализация_журнал.csv.

Запуск без приложения: .venv/bin/python actualize.py [--offline]
"""
import contextlib
import csv
import html
import importlib
import io
import json
import re
import shutil
import ssl
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree

from paths import HOME, OUT, RAW

PARAMS = RAW / "calc_params.json"
WATCH = RAW / "watch.json"
REPORT = OUT / "актуализация.json"
JOURNAL = OUT / "актуализация_журнал.csv"
MIRROR = "https://zakon.uchet.kz/rus/docs/"
ADILET = "https://adilet.zan.kz/rus/docs/"
ETT_INDEX = "https://eec.eaeunion.org/comission/department/catr/ett/"
NBK = "https://nationalbank.kz/rss/get_rates.cfm?fdate={:%d.%m.%Y}"
REPO = "aslantuk-bit/kz-auto-import"

ACTS = [   # код ИЗПИ, название
    ("K2500000214", "Налоговый кодекс РК № 214-VIII"),
    ("K1700000123", "Кодекс РК о таможенном регулировании № 123-VI"),
    ("P1800000171", "ПП РК № 171 о таможенных сборах"),
    ("H15EV000059", "Решение Совета ЕЭК № 59 (ставки РК по ВТО)"),
    ("H17EV000107", "Решение Совета ЕЭК № 107 (товары для личного пользования)"),
    ("Z030000446_", "Закон об обязательном страховании ГПО владельцев ТС"),
    ("V2100025100", "Методика расчёта утилизационного платежа (приказ № 448)"),
]

# Ставки в текстах: ключ calc_params, акт, шаблон, перевод найденного в значение параметра.
PROBES = [
    ("VAT", "K2500000214", "НДС, НК ст. 503 п. 1",
     r"составляет (\d+) процент\w* и применяется к размеру облагаемого оборота и облагаемого импорта",
     lambda s: int(s) / 100),
    ("LUX_MRP", "K2500000214", "порог акциза 10% на легковые, НК ст. 537",
     r"из 8703 Автомобили легковые, стоимость приобретения которых составляет ([\d ]+)-кратный",
     lambda s: int(s.replace(" ", ""))),
    ("CUSTOMS_FEE_MRP", "P1800000171", "таможенный сбор за ДТ, ПП № 171",
     r"с использованием декларации на товары; (\d+) МРП", int),
]

_CTX = None


def _ctx():
    global _CTX
    if _CTX is None:
        try:
            import certifi
            _CTX = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _CTX = ssl.create_default_context()
    return _CTX


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kz-auto-import)"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read().decode("utf-8", "replace")


def plain(page):
    page = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", page)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _d(s):
    return datetime.strptime(s, "%d.%m.%Y").date()


class Report:
    def __init__(self):
        self.items = []
        self.started = datetime.now()

    def add(self, stage, item, status, detail, url=None, action=None):
        """status: ok, info, warn (нужна проверка), change (найдено новое значение), fail."""
        self.items.append({"этап": stage, "что": item, "статус": status, "подробно": detail,
                           "ссылка": url, "действие": action})

    def summary(self):
        n = {s: sum(i["статус"] == s for i in self.items) for s in ("ok", "info", "warn", "change", "fail")}
        return n


# ---------- шаги ----------
def step_fx(rep, today):
    try:
        root = ElementTree.fromstring(fetch(NBK.format(today)))
    except Exception as e:  # сеть или формат
        rep.add("Курсы", "Курсы НБРК", "fail", f"не удалось получить: {e}", NBK.format(today))
        return
    rates = {}
    for it in root.iter("item"):
        code, val, quant = it.findtext("title"), it.findtext("description"), it.findtext("quant") or "1"
        if code in ("EUR", "USD", "CNY", "RUB"):
            rates[code] = round(float(val) / float(quant), 4)
    fx_date = _d(root.findtext("date")) if root.findtext("date") else today
    p = load(PARAMS)
    old = p["fx"]
    if set(rates) != {"EUR", "USD", "CNY", "RUB"}:
        rep.add("Курсы", "Курсы НБРК", "fail", f"в ответе не все валюты: {sorted(rates)}", NBK.format(today))
        return
    p["fx"] = {"date": fx_date.isoformat(), **rates}
    save(PARAMS, p)
    diff = ", ".join(f"{c} {old.get(c)} → {rates[c]}" for c in ("EUR", "USD", "CNY", "RUB") if old.get(c) != rates[c])
    rep.add("Курсы", "Курсы НБРК", "ok",
            f"на {fx_date:%d.%m.%Y}: " + (diff or "не изменились") + " — применено", NBK.format(today))


def step_acts(rep, texts):
    w = load(WATCH)
    for code, name in ACTS:
        url = MIRROR + code
        try:
            texts[code] = plain(fetch(url))
        except Exception as e:
            rep.add("Акты", name, "fail", f"зеркало не открылось: {e}", url)
            continue
        m = re.search(r"Обновленный с изменениями на:\s*([\d.]+)", texts[code])
        known = w["editions"].get(code)
        if not m:
            rep.add("Акты", name, "info", "метки редакции на странице нет — проверяется по ставкам", ADILET + code)
        elif known is None:
            rep.add("Акты", name, "warn", f"редакция {m.group(1)} — раньше не записана; сверьте ставки и отметьте",
                    ADILET + code, {"type": "edition", "key": code, "value": m.group(1)})
        elif _d(m.group(1)) > _d(known):
            rep.add("Акты", name, "warn", f"новая редакция: {known} → {m.group(1)}. Проверьте ставки этого акта",
                    ADILET + code, {"type": "edition", "key": code, "value": m.group(1)})
        else:
            rep.add("Акты", name, "ok", f"редакция {m.group(1)}, как в базе", ADILET + code)
    # ЕТТ: свежий файл группы 87 на сайте ЕЭК
    try:
        files = re.findall(r"ru\.87_2022_([\d.]+)\.pdf", fetch(ETT_INDEX))
        latest = max(files, key=_d)
        known = w["editions"].get("ETT87")
        if _d(latest) > _d(known):
            rep.add("Акты", "ЕТТ ЕАЭС, группа 87", "warn", f"новая редакция группы 87: {known} → {latest}",
                    ETT_INDEX, {"type": "edition", "key": "ETT87", "value": latest})
        else:
            rep.add("Акты", "ЕТТ ЕАЭС, группа 87", "ok", f"редакция {latest}, как в базе", ETT_INDEX)
    except Exception as e:
        rep.add("Акты", "ЕТТ ЕАЭС, группа 87", "fail", f"страница ЕЭК не разобрана: {e}", ETT_INDEX)


def step_probes(rep, texts, today):
    p = load(PARAMS)
    for key, code, what, pattern, conv in PROBES:
        txt = texts.get(code)
        if txt is None:
            rep.add("Ставки", what, "fail", "текст акта не получен", ADILET + code)
            continue
        m = re.search(pattern, txt)
        if not m:
            rep.add("Ставки", what, "warn", "формулировка в тексте не найдена — норма могла измениться", ADILET + code)
            continue
        val = conv(m.group(1))
        if val == p.get(key):
            rep.add("Ставки", what, "ok", f"{_fmt(key, val)}, как в расчёте", ADILET + code)
        else:
            rep.add("Ставки", what, "change", f"в тексте {_fmt(key, val)}, в расчёте {_fmt(key, p.get(key))}",
                    ADILET + code, {"type": "param", "key": key, "value": val})
    # МРП: закон о бюджете на текущий год
    w = load(WATCH)
    law = w["mrp_law"]
    if today.year > law["year"] or p["MRP_year"] < today.year:
        rep.add("Ставки", f"МРП на {today.year} год", "warn",
                f"в расчёте МРП {p['MRP']} тг на {p['MRP_year']} год. Нужен закон о бюджете на {today.year} год: "
                "задайте МРП вручную ниже и обновите mrp_law в watch.json", ADILET)
        return
    try:
        txt = plain(fetch(MIRROR + law["code"]))
        m = re.search(r"месячный расчетный показатель\s*[–-]\s*([\d ]+)\s*тенге", txt)
        if not m:
            rep.add("Ставки", "МРП", "warn", "значение в законе о бюджете не найдено", ADILET + law["code"])
            return
        val = int(m.group(1).replace(" ", ""))
        if val == p["MRP"]:
            rep.add("Ставки", f"МРП {law['year']}", "ok", f"{_fmt('MRP', val)} тг, как в расчёте",
                    ADILET + law["code"])
        else:
            rep.add("Ставки", f"МРП {law['year']}", "change", f"в законе {val} тг, в расчёте {p['MRP']} тг",
                    ADILET + law["code"], {"type": "param", "key": "MRP", "value": val})
    except Exception as e:
        rep.add("Ставки", "МРП", "fail", f"закон о бюджете не открылся: {e}", ADILET + law["code"])


def _fmt(key, v):
    if v is None:
        return "—"
    return f"{v * 100:g}%" if key == "VAT" else f"{v:,}".replace(",", " ") + (" МРП" if key.endswith("_MRP") else "")


def step_calendar(rep, today):
    p = load(PARAMS)
    as_of = date.fromisoformat(p["as_of"])
    days = (today - as_of).days
    rep.add("Календарь", "Давность сверки ставок", "ok" if days <= 31 else "warn",
            f"ставки сверены {as_of:%d.%m.%Y}, {days} дн. назад")
    if today.month == 12:
        rep.add("Календарь", "Конец года", "info", "с 1 января машины становятся на год старше для сбора за "
                                                  "регистрацию и меняется МРП — регистрируйте до 31 декабря")


def _reload(*names):
    mods = []
    for n in names:
        mods.append(importlib.reload(sys.modules[n]) if n in sys.modules else importlib.import_module(n))
    return mods


def step_rebuild(rep):
    calc, = _reload("calc")
    _reload("glossary", "savings")
    for title, fn in (("База ставок", lambda: _reload("build")[0].build()),
                      ("Сетка сценариев", lambda: calc.write_scenarios()),
                      ("Книга Excel", lambda: _reload("report")[0].main()),
                      ("Данные сайта", lambda: _reload("export_web")[0].main())):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            rep.add("Пересборка", title, "ok", "пересобрано")
        except Exception as e:
            rep.add("Пересборка", title, "fail", f"{type(e).__name__}: {e}")


def step_selfcheck(rep):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            _reload("test_calc")[0].run_all()
        rep.add("Самопроверка", "Калькулятор и база", "ok", buf.getvalue().strip().splitlines()[-1])
    except Exception as e:
        rep.add("Самопроверка", "Калькулятор и база", "fail", f"{type(e).__name__}: {e}")
    try:
        import pandas as pd
        n = len(pd.read_csv(OUT / "сценарии.csv"))
        rep.add("Самопроверка", "Сетка сценариев", "ok" if n == 3888 else "fail", f"{n} сценариев")
    except Exception as e:
        rep.add("Самопроверка", "Сетка сценариев", "fail", str(e))
    parity = HOME / "web" / "parity_test.mjs"
    if shutil.which("node") and parity.exists():
        r = subprocess.run(["node", str(parity)], capture_output=True, text=True, cwd=HOME)
        rep.add("Самопроверка", "Сайт = приложение", "ok" if r.returncode == 0 else "fail",
                (r.stdout.strip().splitlines() or ["нет вывода"])[-1])


def step_as_of(rep, today):
    """Все акты и ставки совпали с текстами — дата сверки становится сегодняшней (до пересборки)."""
    if not any(i["статус"] in ("warn", "change", "fail") and i["этап"] in ("Акты", "Ставки") for i in rep.items):
        p = load(PARAMS)
        p["as_of"] = today.isoformat()
        save(PARAMS, p)


def _finish(rep, today):
    s = rep.summary()
    p = load(PARAMS)
    data = {"начало": rep.started.isoformat(timespec="seconds"), "конец": datetime.now().isoformat(timespec="seconds"),
            "итог": s, "as_of": p["as_of"], "пункты": rep.items}
    save(REPORT, data)
    new = not JOURNAL.exists()
    with JOURNAL.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["время", "ok", "внимание", "изменения", "ошибки", "ставки_сверены"])
        w.writerow([data["конец"], s["ok"], s["warn"], s["change"], s["fail"], p["as_of"]])
    return data


def run(offline=False, today=None, progress=None):
    """Полная актуализация. progress(stage) вызывается перед каждым этапом (для интерфейса)."""
    today = today or date.today()
    rep, texts = Report(), {}
    stages = [("Курсы НБРК", lambda: step_fx(rep, today)),
              ("Тексты актов", lambda: step_acts(rep, texts)),
              ("Ставки в текстах", lambda: step_probes(rep, texts, today)),
              ("Дата сверки", lambda: step_as_of(rep, today))] if not offline else []
    stages += [("Календарь", lambda: step_calendar(rep, today)),
               ("Пересборка", lambda: step_rebuild(rep)),
               ("Самопроверка", lambda: step_selfcheck(rep))]
    for title, fn in stages:
        if progress:
            progress(title)
        fn()
    return _finish(rep, today)


def apply(action):
    """Принять найденное: новое значение параметра или проверенную редакцию акта. Затем — пересборка."""
    if action["type"] == "param":
        p = load(PARAMS)
        p[action["key"]] = action["value"]
        if action["key"] == "MRP":
            p["MRP_year"] = load(WATCH)["mrp_law"]["year"]
        save(PARAMS, p)
    elif action["type"] == "edition":
        w = load(WATCH)
        w["editions"][action["key"]] = action["value"]
        save(WATCH, w)
    if REPORT.exists():   # пометить пункт выполненным
        data = load(REPORT)
        for i in data["пункты"]:
            if i.get("действие") == action:
                i["статус"], i["действие"] = "ok", None
                i["подробно"] += " — принято"
        save(REPORT, data)


def set_params(**values):
    """Ручная правка параметров (МРП нового года, НДС и т. п.)."""
    p = load(PARAMS)
    p.update({k: v for k, v in values.items() if v is not None})
    save(PARAMS, p)


def last_report():
    return load(REPORT) if REPORT.exists() else None


def github_token():
    try:
        r = subprocess.run(["git", "credential-osxkeychain", "get"], input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=10)
        return next((ln.split("=", 1)[1] for ln in r.stdout.splitlines() if ln.startswith("password=")), None)
    except Exception:
        return None


def publish_site(token=None):
    """Заливает out/data.json в docs/data.json репозитория через GitHub API — сайт обновится за 1–2 минуты."""
    import base64
    token = token or github_token()
    if not token:
        raise RuntimeError("нет токена GitHub в связке ключей (git credential-osxkeychain)")
    api = f"https://api.github.com/repos/{REPO}/contents/docs/data.json"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
           "User-Agent": "kz-auto-import"}
    req = urllib.request.Request(api, headers=hdr)
    with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
        sha = json.load(r)["sha"]
    body = json.dumps({"message": f"Актуализация данных {date.today():%d.%m.%Y}", "sha": sha,
                       "content": base64.b64encode((OUT / "data.json").read_bytes()).decode()}).encode()
    req = urllib.request.Request(api, data=body, method="PUT", headers={**hdr, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=_ctx()) as r:
        return json.load(r)["commit"]["html_url"]


if __name__ == "__main__":
    out = run(offline="--offline" in sys.argv, progress=lambda t: print("·", t))
    for i in out["пункты"]:
        print(f"[{i['статус']:6}] {i['этап']} · {i['что']}: {i['подробно']}")
    print("итог:", out["итог"], "ставки сверены", out["as_of"])
