"""Общее для страниц: данные, подписи, форматирование, палитра."""
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from paths import HOME as ROOT, OUT  # noqa: E402
DB = OUT / "kz_auto_import.sqlite"
TODAY = date(2026, 10, 15)   # дата, на которую собраны ставки

# Палитра: dataviz, категориальные слоты в фиксированном порядке (светлая тема).
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MUTED = "#b9bcc4"
DIVERGING = ["#1c5cab", "#86b6ef", "#f0efec", "#f2a3a2", "#c23131"]

# Платёж → подпись, норма, цвет. Порядок = порядок в стопке.
COMPONENTS = [
    ("пошлина", "Пошлина", "ЕТТ ЕАЭС (Решение № 80) или ставки РК по ВТО (Решение № 59)"),
    ("ЕТП_СТП", "Единая ставка физлица", "Решение Совета ЕЭК № 107, прил. 2, табл. 2"),
    ("таможенный_сбор", "Таможенный сбор", "ПП РК № 171: 6 МРП за декларацию"),
    ("акциз", "Акциз", "НК ст. 537: 100 тг/см³ свыше 3 000 см³; 10% от 18 000 МРП"),
    ("НДС", "НДС 16%", "НК ст. 503 (третьи страны — ст. 466, ЕАЭС — ст. 518)"),
    ("за_рубежом", "Платежи в Кыргызстане", "пошлина по ЕТТ, НДС 12% и сбор 0,4% при растаможке в КР"),
    ("утильсбор", "Утильсбор", "Приказ МЭПР № 54 от 20.03.2026, прил. 4"),
    ("сбор_первичная_регистрация", "Сбор за регистрацию", "НК ст. 615 п. 3"),
    ("СРТС_и_номера", "Техпаспорт и номера", "НК ст. 667: 1,25 + 2,8 МРП"),
]
COMP_LABEL = {k: lbl for k, lbl, _ in COMPONENTS}
COMP_NORM = {k: n for k, _, n in COMPONENTS}
# цвета прежних платежей не сдвигаются; платежи за рубежом — нейтральный серый
_OWN = [c for c in COMPONENTS if c[0] != "за_рубежом"]
COMP_COLOR = {lbl: SLOTS[i] for i, (_, lbl, _) in enumerate(_OWN)} | {"Платежи в Кыргызстане": "#7a8794"}

ROUTES = [
    # id, режим, происхождение, подпись, кто и как
    ("dt", "ДТ", "третьи", "Третьи страны · ДТ", "Юрлицо или физлицо, декларация на товары"),
    ("ptd", "ПТД", "третьи", "Третьи страны · ПТД", "Физлицо, личное пользование, единая ставка"),
    ("kg_ul", "ЕАЭС_ЮЛ", "третьи", "Через Кыргызстан · ЮЛ",
     "Растаможка в КР по ЕТТ, в РК — НДС 16% через ФНО 328.00"),
    ("kg_fl", "ЕАЭС_ФЛ", "третьи", "Через Кыргызстан · ФЛ",
     "Растаможка в КР по ЕТТ с НДС 12%, в РК — утильсбор и регистрация"),
    ("ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ", "Россия/Беларусь · ЮЛ", "Машина с рынка России или Беларуси; утильсбор по коэффициенту 2"),
    ("ru_fl", "ЕАЭС_ФЛ", "РФ_РБ", "Россия/Беларусь · ФЛ", "Машина с рынка России или Беларуси; утильсбор по коэффициенту 2"),
]
ROUTE_LABEL = {r[0]: r[3] for r in ROUTES}
ROUTE_COLOR = {r[3]: SLOTS[i] for i, r in enumerate(ROUTES)}
RU_ROUTES = {"Россия/Беларусь · ЮЛ", "Россия/Беларусь · ФЛ"}

FUEL_LABEL = {
    "бензин": "Бензин", "дизель": "Дизель", "гибрид_двс": "Гибрид (мощнее ДВС)",
    "гибрид_эл": "Гибрид (мощнее электромотор)", "электро": "Электромобиль",
}


def money(x, unit=""):
    """1234567 → «1 234 567»; unit='млн' → «1,2 млн»."""
    if x is None or pd.isna(x):
        return "—"
    if unit == "млн":
        return f"{x / 1e6:,.1f} млн".replace(",", " ").replace(".", ",")
    return f"{x:,.0f}".replace(",", " ")


def pct(x, digits=0):
    return f"{x:.{digits}f}%".replace(".", ",")


@st.cache_data
def load_rates():
    return pd.read_csv(OUT / "ставки.csv")


@st.cache_data
def load_params():
    return pd.read_csv(OUT / "параметры.csv")


@st.cache_data
def load_table(name):
    with sqlite3.connect(DB) as con:
        return pd.read_sql(f'select * from "{name}"', con)


@st.cache_data
def load_scenarios():
    df = pd.read_csv(OUT / "сценарии.csv")
    label = {(mode, origin): lbl for _, mode, origin, lbl, _ in ROUTES}
    df["маршрут"] = [label[k] for k in zip(df["режим"], df["происхождение"])]
    df["акциз"] = df["акциз_объём"] + df["акциз_10pct"]
    df["двигатель"] = df.apply(
        lambda r: FUEL_LABEL[r["тип"]] + ("" if r["тип"] == "электро" else f" {r['объём'] / 1000:.1f} л"), axis=1)
    return df


def fx_rates():
    p = load_params().set_index("параметр")["значение"]
    return {"EUR": p["EUR_KZT_15.10.2026"], "USD": p["USD_KZT_15.10.2026"],
            "CNY": p["CNY_KZT_15.10.2026"], "RUB": p["RUB_KZT_15.10.2026"], "KZT": 1.0}


def long_components(df, id_col):
    """Строки сценариев → длинная таблица «id × платёж» для стопок."""
    keys = [k for k, _, _ in COMPONENTS]
    m = df[[id_col] + keys].melt(id_vars=id_col, var_name="ключ", value_name="сумма")
    m["платёж"] = m["ключ"].map(COMP_LABEL)
    m["порядок"] = m["ключ"].map({k: i for i, k in enumerate(keys)})
    return m[m["сумма"] > 0]


def note(text):
    st.caption(text)
