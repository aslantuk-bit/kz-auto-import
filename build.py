"""Сводит четыре исследовательских блока (sources/raw/*.json) в единую базу ставок.

Выход: out/ставки.csv, out/параметры.csv, out/условия.csv, out/источники.csv,
out/kz_auto_import.sqlite. Excel собирает report.py (после calc.py).
"""
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

import calc
from paths import OUT, RAW
TODAY = date.today()

COLUMNS = [
    "id", "блок", "этап", "вид_платежа", "получатель", "обязательность",
    "категория_ТС", "категория_ЕЭК", "код_ТНВЭД", "тип_двигателя",
    "объём_от_см3", "объём_до_см3", "масса_от_т", "масса_до_т",
    "возраст_от_лет", "возраст_до_лет", "стоимость_от", "стоимость_до", "валюта_стоимости",
    "субъект", "происхождение", "режим",
    "ставка_адвалорная_пct", "ставка_специфическая", "единица_специфической", "минимум",
    "ставка_МРП", "коэффициент", "ставка_текст", "единица",
    "база", "формула", "сумма_тг_2026",
    "правовой_акт", "статья", "url", "действует_с", "действует_по",
    "актуальна", "достоверность", "статус_проверки", "примечание",
    "исходный_файл", "исходный_номер",
]

# А — текст акта; Б — официальное разъяснение госоргана; В — СМИ/вторичные;
# Г — рыночная оценка; Д — спорно или не подтверждено.
RELIABILITY = {
    "А": "текст нормативного акта",
    "Б": "официальное разъяснение госоргана",
    "В": "СМИ / вторичные источники",
    "Г": "рыночная оценка",
    "Д": "спорно или не подтверждено",
}


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def reliability(status):
    s = (status or "").lower()
    if any(k in s for k in ("не подтвержд", "спорно", "не принят")):
        return "Д"
    if s.startswith(("подтверждено: текст", "подтверждено текстом", "подтверждено первоисточником")) \
            and "сми" not in s.split(";")[0]:
        return "А"
    if "рыноч" in s:
        return "Г"
    if "сми" in s or "вторичн" in s:
        return "В"
    if "разъяснен" in s:
        return "Б"
    return "А"


def is_current(rec):
    s = (rec.get("статус_проверки") or "").lower()
    if "историческ" in s or "недействующ" in s:
        return "нет"
    till = rec.get("действует_по")
    if till:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(till))
        if m and date(*map(int, m.groups())) < TODAY:
            return "нет"
    return "да"


def base_row(rec, src, i):
    row = {c: None for c in COLUMNS}
    for c in ("категория_ТС", "код_ТНВЭД", "тип_двигателя", "субъект", "вид_платежа",
              "база", "формула", "правовой_акт", "url", "действует_с", "действует_по",
              "статус_проверки", "примечание", "единица", "сумма_тг_2026", "обязательность"):
        if c in rec:
            row[c] = rec[c]
    row["статья"] = rec.get("статья") or rec.get("пункт")
    row["объём_от_см3"] = num(rec.get("объём_от"))
    row["объём_до_см3"] = num(rec.get("объём_до"))
    row["возраст_от_лет"] = num(rec.get("возраст_от_лет"))
    row["возраст_до_лет"] = num(rec.get("возраст_до_лет"))
    row["достоверность"] = reliability(rec.get("статус_проверки"))
    row["актуальна"] = is_current(rec)
    row["исходный_файл"] = src
    row["исходный_номер"] = i
    return row


# ---------- A: таможенные пошлины и сборы ----------
PTD_RANGE = re.compile(r"стоимость авто:\s*(?:>\s*([\d\s]+?)\s*)?(?:≤\s*([\d\s]+?)\s*)?EUR")


def map_a(rec, i, fname="A_customs.json"):
    row = base_row(rec, fname, i)
    vid = (rec.get("вид_платежа") or "").lower()
    cat = rec.get("категория_ТС") or ""
    subj = rec.get("субъект") or ""
    if "сбор" in vid and "таможенн" in vid:
        row["блок"], row["этап"] = "Таможенные сборы", "таможенное оформление"
    else:
        row["блок"], row["этап"] = "Таможенные пошлины", "таможенное оформление"
    if "ВТО" in cat:
        row["режим"] = "ДТ: ставки РК по ВТО (Решение № 59)"
    elif "ПТД" in subj or "личного пользования" in cat:
        row["режим"] = "ПТД: личное пользование (Решение № 107)"
    elif "пошлина" in vid and (rec.get("код_ТНВЭД") or "").startswith("87"):
        row["режим"] = "ДТ: ЕТТ ЕАЭС (Решение № 80)"
    if "ЕАЭС" in cat and ("ввозимые из" in cat or "РФ" in cat):
        row["происхождение"] = "ЕАЭС"
    elif row["блок"] == "Таможенные пошлины":
        row["происхождение"] = "третьи страны"
    row["ставка_адвалорная_пct"] = num(rec.get("ставка_адвалорная_%"))
    spec = rec.get("ставка_специфическая")
    row["ставка_специфическая"] = num(spec)
    if spec is not None and num(spec) is None:
        row["ставка_текст"] = str(spec)
    if row["ставка_специфическая"] is not None:
        row["единица_специфической"] = "МРП" if (rec.get("единица") or "").startswith("МРП") else "EUR/см³"
    row["минимум"] = rec.get("минимум")
    if row["единица_специфической"] == "МРП":
        row["ставка_МРП"] = row["ставка_специфическая"]
        row["ставка_специфическая"] = None
        row["единица_специфической"] = None
    m = PTD_RANGE.search(rec.get("формула") or "")
    if m and (m.group(1) or m.group(2)):
        row["стоимость_от"] = num(m.group(1)) if m.group(1) else 0
        row["стоимость_до"] = num(m.group(2)) if m.group(2) else None
        row["валюта_стоимости"] = "EUR"
    row["получатель"] = "бюджет (пошлины распределяются между странами ЕАЭС)" \
        if row["блок"] == "Таможенные пошлины" else "республиканский бюджет РК"
    row["обязательность"] = "обязательный госплатёж"
    return row


# ---------- B: налоги и сборы по НК ----------
def map_b(rec, i, fname="B_taxes.json"):
    row = base_row(rec, fname, i)
    vid = (rec.get("вид_платежа") or "").lower()
    if vid.startswith(("мрп", "мзп", "официальный курс")):
        return None  # уходит в параметры
    if "налог на транспорт" in vid or "налог на тс" in vid:
        row["блок"], row["этап"] = "Налог на транспорт", "после регистрации (ежегодно)"
    elif "регистрац" in vid or "дубликат" in vid:
        row["блок"], row["этап"] = "Сборы за регистрацию", "регистрация"
    elif "акциз" in vid:
        row["блок"], row["этап"] = "Акциз", "таможенное оформление / до регистрации"
    else:
        row["блок"], row["этап"] = "НДС", "таможенное оформление / до регистрации"
    if "третьих стран" in vid:
        row["происхождение"] = "третьи страны"
    elif "еаэс" in vid:
        row["происхождение"] = "ЕАЭС"
    unit = rec.get("единица") or ""
    val = num(rec.get("ставка"))
    if unit.startswith("%"):
        row["ставка_адвалорная_пct"] = val
    elif unit.startswith("МРП"):
        row["ставка_МРП"] = val
    elif "см³" in unit:
        row["ставка_специфическая"] = val
        row["единица_специфической"] = "тг/см³"
    if val is None and rec.get("ставка") is not None:
        row["ставка_текст"] = str(rec.get("ставка"))
    if "роскош" in vid or "дорогие" in vid:
        row["стоимость_от"] = calc.LUX_THRESHOLD
        row["валюта_стоимости"] = "KZT (18 000 МРП)"
    row["получатель"] = "местный бюджет" if row["блок"] in ("Налог на транспорт", "Сборы за регистрацию") \
        else "республиканский бюджет РК"
    row["обязательность"] = "обязательный госплатёж"
    return row


# ---------- C: утилизационный платёж ----------
def map_c(rec, i):
    row = base_row(rec, "C_util.json", i)
    row["блок"], row["этап"] = "Утилизационный платёж", "до выпуска / до первичной регистрации"
    row["вид_платежа"] = "утилизационный платёж (РОП)"
    row["категория_ЕЭК"] = rec.get("категория_ЕЭК")
    row["масса_от_т"] = num(rec.get("масса_от_т"))
    row["масса_до_т"] = num(rec.get("масса_до_т"))
    org = rec.get("происхождение") or ""
    row["происхождение"] = "ЕАЭС: РФ, РБ (коэффициент 2)" if org.startswith("ЕАЭС: Росс") \
        else ("третьи страны, АМ, КГ, РК (коэффициент 1)" if org.startswith("третьи") else org)
    row["коэффициент"] = num(rec.get("коэффициент"))
    row["ставка_МРП"] = row["коэффициент"] * 50 if row["коэффициент"] is not None else None
    row["единица"] = "50 МРП × коэффициент"
    row["база"] = rec.get("базовая_величина")
    row["статья"] = rec.get("пункт")
    row["получатель"] = "оператор РОП — АО «Жасыл даму»"
    row["обязательность"] = "обязательный платёж"
    return row


# ---------- D: регистрация, соответствие, ОГПО, рынок ----------
D_DUPLICATES = set(range(0, 17)) | {96, 97, 108}  # дубли блоков A и B, оставлены для сверки в raw


def map_d(rec, i):
    if i in D_DUPLICATES:
        return None
    sec = rec.get("блок") or ""
    if sec.startswith("6."):
        return None  # уходит в условия
    row = base_row(rec, "D_registration.json", i)
    if sec.startswith("1."):
        row["блок"], row["этап"] = "Госпошлины за документы и номера", "регистрация"
        row["получатель"] = "республиканский бюджет РК"
    elif sec.startswith("2."):
        row["блок"], row["этап"] = "Подтверждение соответствия (СБКТС/ЭПТС)", "до регистрации"
        row["получатель"] = "испытательные лаборатории / органы по сертификации"
    elif sec.startswith("3."):
        row["блок"], row["этап"] = "ОГПО ВТС", "регистрация"
        row["получатель"] = "страховая компания"
    elif sec.startswith("4."):
        row["блок"], row["этап"] = "Техосмотр", "после регистрации"
        row["получатель"] = "оператор техосмотра"
    elif sec.startswith("5."):
        fee = "сбор" in (rec.get("вид_платежа") or "").lower()
        row["блок"] = "Таможенные сборы" if fee else "Таможенные услуги (рынок)"
        row["этап"] = "таможенное оформление"
        row["получатель"] = "республиканский бюджет РК" if fee else "частные поставщики"
    unit = rec.get("единица") or ""
    val = num(rec.get("ставка"))
    if unit.startswith("МРП"):
        row["ставка_МРП"] = val
    elif unit.startswith("коэффициент"):
        row["коэффициент"] = val
    elif unit.startswith("%"):
        row["ставка_адвалорная_пct"] = val
    if rec.get("ставка") is not None and val is None:
        row["ставка_текст"] = str(rec.get("ставка"))
    return row


def build():
    OUT.mkdir(exist_ok=True)
    rows = []
    # H — таможня прочей техники (формат A), I — сторона РК для прочей техники (формат B)
    for fname, mapper in (("A_customs.json", map_a), ("B_taxes.json", map_b),
                          ("C_util.json", map_c), ("D_registration.json", map_d),
                          ("H_customs_other.json", lambda r, i: map_a(r, i, "H_customs_other.json")),
                          ("I_kz_other.json", lambda r, i: map_b(r, i, "I_kz_other.json"))):
        if not (RAW / fname).exists():
            continue
        for i, rec in enumerate(json.loads((RAW / fname).read_text())):
            r = mapper(rec, i)
            if r:
                rows.append(r)
    # Общее сопровождение «МРП за расстояние» из A заменяется шкалой из D.
    rows = [r for r in rows if not (r["исходный_файл"] == "A_customs.json"
                                     and "сопровожд" in (r["вид_платежа"] or ""))]
    for n, r in enumerate(rows, 1):
        r["id"] = f"R{n:04d}"
        if r["ставка_МРП"] is not None and r["сумма_тг_2026"] in (None, ""):
            r["сумма_тг_2026"] = round(r["ставка_МРП"] * calc.MRP, 2)
    rates = pd.DataFrame(rows, columns=COLUMNS)

    params = [
        {"параметр": f"МРП_{calc.MRP_YEAR}", "значение": calc.MRP, "единица": "тг",
         "источник": "закон о республиканском бюджете на текущий год (2026 — № 239-VIII от 08.12.2025, ст. 7)"},
        {"параметр": "МЗП_2026", "значение": 85000, "единица": "тг",
         "источник": "Закон РК от 08.12.2025 № 239-VIII, ст. 7"},
        {"параметр": "НДС_импорт", "значение": round(calc.VAT * 100, 2), "единица": "%",
         "источник": "НК РК от 18.07.2025 № 214-VIII, ст. 503 п. 1"},
        {"параметр": "утильсбор_базовая_ставка", "значение": 50, "единица": "МРП",
         "источник": "Методика, приказ МЭГПР № 448 от 02.11.2021 (ред. приказа МЭПР № 54 от 20.03.2026)"},
        {"параметр": "порог_акциза_10pct", "значение": calc.LUX_THRESHOLD, "единица": f"тг ({calc.LUX_MRP:,} МРП)".replace(",", " "),
         "источник": "НК РК, ст. 537 п. 6, строка 24"},
        {"параметр": "таможенный_сбор_ДТ", "значение": calc.CUSTOMS_FEE_MRP, "единица": "МРП",
         "источник": "Постановление Правительства РК от 05.04.2018 № 171"},
    ]
    for cur in ("EUR", "USD", "CNY", "RUB"):
        params.append({"параметр": f"{cur}_KZT", "значение": calc.FX[cur], "единица": "тг",
                       "источник": f"НБРК, официальный курс на {calc.FX_DATE:%d.%m.%Y}"})
    params = pd.DataFrame(params)

    d = json.loads((RAW / "D_registration.json").read_text())
    conds = pd.DataFrame([{
        "условие": r.get("вид_платежа"), "категория_ТС": r.get("категория_ТС"),
        "субъект": r.get("субъект"), "правовой_акт": r.get("правовой_акт"),
        "статья": r.get("пункт"), "url": r.get("url"), "действует_с": r.get("действует_с"),
        "достоверность": reliability(r.get("статус_проверки")),
        "статус_проверки": r.get("статус_проверки"), "примечание": r.get("примечание"),
    } for r in d if (r.get("блок") or "").startswith("6.")])

    src = (rates.groupby("правовой_акт", dropna=True)
           .agg(записей=("id", "count"), блоки=("блок", lambda s: ", ".join(sorted(set(s)))),
                url=("url", "first"))
           .reset_index().sort_values("записей", ascending=False))

    rel = pd.DataFrame([{"код": k, "значение": v} for k, v in RELIABILITY.items()])

    rates.to_csv(OUT / "ставки.csv", index=False, encoding="utf-8-sig")
    params.to_csv(OUT / "параметры.csv", index=False, encoding="utf-8-sig")
    conds.to_csv(OUT / "условия.csv", index=False, encoding="utf-8-sig")
    src.to_csv(OUT / "источники.csv", index=False, encoding="utf-8-sig")
    with sqlite3.connect(OUT / "kz_auto_import.sqlite") as con:
        rates.to_sql("ставки", con, if_exists="replace", index=False)
        params.to_sql("параметры", con, if_exists="replace", index=False)
        conds.to_sql("условия", con, if_exists="replace", index=False)
        src.to_sql("источники", con, if_exists="replace", index=False)
        rel.to_sql("достоверность", con, if_exists="replace", index=False)
    print(f"ставок: {len(rates)}, параметров: {len(params)}, условий: {len(conds)}, актов: {len(src)}")
    print(rates.groupby(["блок", "достоверность"]).size().unstack(fill_value=0))
    return rates, params, conds, src


if __name__ == "__main__":
    build()
