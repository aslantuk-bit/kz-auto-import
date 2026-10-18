"""Грузовики, тягачи, спецмашины, мотоциклы и самоходная техника: платежи по маршрутам ввоза."""
from dataclasses import replace

import pandas as pd
import streamlit as st

import calc
import vehicles as V
from ui.common import TODAY, as_of_line, fx_rates, keep, money, pct, remember

GROUPS = list(dict.fromkeys(v[1] for v in V.KINDS.values()))
YEARS = list(range(TODAY.year, 1989, -1))
DEFAULTS = {"vh_group": GROUPS[0], "vh_kind": "truck_diesel", "vh_price": 40000.0, "vh_cur": "EUR",
            "vh_deliv": 3000.0, "vh_year": TODAY.year - 4, "vh_month": 6, "vh_mass": 18.0, "vh_payload": 10.0,
            "vh_cc": 7700, "vh_kw": 150, "vh_eco4": True, "vh_electric": False}
ROUTE_LABEL = {"dt": "Третьи страны · ДТ", "ptd": "Третьи страны · ПТД", "ru_ul": "Россия/Беларусь · ЮЛ",
               "ru_fl": "Россия/Беларусь · ФЛ"}
LINES = [("пошлина", "Пошлина", "ЕТТ ЕАЭС (Решение № 80) или ставки РК по ВТО (Решение № 59)"),
         ("ЕТП_СТП", "Совокупный платёж (ПТД)", "Решение № 107, прил. 2, табл. 2, п. 1: пошлина по ЕТТ + НДС"),
         ("таможенный_сбор", "Таможенный сбор", "ПП РК № 171: 6 МРП"),
         ("НДС", "НДС 16%", "НК ст. 503"),
         ("утильсбор", "Утильсбор", "приказ МЭПР № 54, прил. 4 (мото и строительная техника не облагаются)"),
         ("сбор_первичная_регистрация", "Сбор за регистрацию", "НК ст. 615 п. 3"),
         ("СРТС_и_номера", "Техпаспорт и номера", "НК ст. 667")]


def _ages(year, month):
    months = (TODAY.year - year) * 12 + (TODAY.month - month) - (1 if TODAY.day < 15 else 0)
    return max(months // 12, 0), TODAY.year - year


def _inputs():
    fx = fx_rates()
    keep(DEFAULTS, valid={"vh_group": GROUPS, "vh_kind": list(V.KINDS), "vh_cur": list(fx), "vh_year": YEARS,
                          "vh_month": list(range(1, 13))})
    ss = st.session_state
    group = st.selectbox("Группа", GROUPS, key="vh_group")
    kinds = [k for k, v in V.KINDS.items() if v[1] == group]
    if ss.vh_kind not in kinds:
        ss.vh_kind = kinds[0]
    kind = st.selectbox("Вид техники", kinds, format_func=lambda k: V.KINDS[k][0], key="vh_kind")
    fields = V.KINDS[kind][3]
    c1, c2 = st.columns([3, 2])
    price = c1.number_input("Цена покупки", min_value=0.0, step=1000.0, format="%.0f", key="vh_price")
    cur = c2.selectbox("Валюта", list(fx), key="vh_cur")
    deliv = st.number_input("Доставка и страховка до границы ЕАЭС", min_value=0.0, step=100.0, format="%.0f",
                            key="vh_deliv", help="В той же валюте. По ДТ входит в таможенную стоимость, по ПТД — нет.")
    c3, c4 = st.columns(2)
    year = c3.selectbox("Год выпуска", YEARS, key="vh_year")
    month = c4.selectbox("Месяц выпуска", list(range(1, 13)), key="vh_month")
    vals = {}
    if "mass" in fields:
        vals["mass"] = st.number_input("Полная масса, т", min_value=0.5, max_value=150.0, step=0.5, key="vh_mass",
                                       help="Технически допустимая максимальная масса из документов производителя")
    if "payload" in fields:
        vals["payload"] = st.number_input("Грузоподъёмность, т", min_value=0.0, max_value=100.0, step=0.5,
                                          key="vh_payload", help="Для налога на транспорт")
    if "cc" in fields:
        vals["cc"] = st.number_input("Объём двигателя, см³", min_value=0, max_value=30000, step=100, key="vh_cc")
    if "kw" in fields:
        vals["kw"] = st.number_input("Мощность, кВт", min_value=1, max_value=1500, step=5, key="vh_kw",
                                     help=f"1 кВт = 1,36 л.с. Для утильсбора тракторов и комбайнов, ставки трактора "
                                          f"и налога на мотоцикл")
    if "eco4" in fields:
        vals["eco4"] = st.toggle("Экокласс 4 и выше (Евро-4+)", key="vh_eco4",
                                 help="Новый тягач с экоклассом 4+ — пошлина 5% вместо 10%")
    if "electric" in fields:
        vals["electric"] = st.toggle("Электрический", key="vh_electric")
    k_eur = fx[cur] / fx["EUR"]
    age, age_reg = _ages(year, month)
    return V.Machine(kind, price * k_eur, age, age_reg, deliv * k_eur, **vals)


def render():
    st.title("Грузовики, мотоциклы, спецтехника")
    st.caption("Платежи при ввозе в РК с постановкой на учёт: грузовики, седельные тягачи, спецмашины на шасси, "
               "мотоциклы, тракторы, комбайны, погрузчики и дорожно-строительная техника. " + as_of_line() + ".")
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        m = _inputs()
    rows = []
    for rid, mode, origin in V.routes_for(m):
        r = V.calc_machine(replace(m, mode=mode, origin=origin))
        rows.append({"id": rid, "маршрут": ROUTE_LABEL[rid], **r})
    df = pd.DataFrame(rows)
    ok = df[~df["примечания"].str.contains(calc.BLOCKING)]
    third = ok[ok["id"].isin(["dt", "ptd"])]
    best = third.loc[third["итого_обязательные"].idxmin()]
    tp = V.tips(m, TODAY.year)
    with right:
        st.subheader("Итог")
        st.markdown(f"Дешевле всего из третьих стран: **{best['маршрут']}**. Регистрирует: {best['регистрирует']}.")
        a, b, c = st.columns(3)
        a.metric("Платежи", money(best["итого_обязательные"]) + " тг")
        b.metric("От цены", pct(100 * best["итого_обязательные"] / best["стоимость_кзт"]) if best["стоимость_кзт"] else "—")
        c.metric("Налог на транспорт в год", money(best["налог_на_транспорт_год"]) + " тг")
        if tp:
            with st.container(border=True):
                st.markdown("**Как сэкономить на этой технике**")
                st.markdown("\n".join(f"- {t['text']}" for t in tp))
        st.caption(f"Для таможни технике {m.age} полных лет, для сбора за регистрацию — {m.рег} (включая год выпуска).")
    st.subheader("Сравнение маршрутов")
    st.dataframe(pd.DataFrame({
        "Маршрут": df["маршрут"], "Итого, тг": df["итого_обязательные"].map(money),
        "С доставкой и услугами, тг": df["итого_с_рыночными"].map(money),
        "Пошлина / СТП": (df["пошлина"] + df["ЕТП_СТП"]).map(money), "НДС": df["НДС"].map(money),
        "Утильсбор": df["утильсбор"].map(money), "Сбор за регистрацию": df["сбор_первичная_регистрация"].map(money),
        "Примечания": df["примечания"]}), hide_index=True, use_container_width=True)
    st.subheader("Разбивка по маршруту")
    for tab, (_, r) in zip(st.tabs(df["маршрут"].tolist()), df.iterrows()):
        with tab:
            st.caption(f"Ставка пошлины: {r['ставка_пошлины']} · регистрирует {r['регистрирует']}")
            lines = [{"Платёж": lbl, "Сумма, тг": money(r[k]), "Норма": norm} for k, lbl, norm in LINES if r[k] > 0]
            lines.append({"Платёж": "Итого обязательные", "Сумма, тг": money(r["итого_обязательные"]), "Норма": ""})
            lines.append({"Платёж": "Доставка и рыночные расходы (оценка)",
                          "Сумма, тг": money(r["доставка_кзт"] + r["рыночные_оценка"]),
                          "Норма": "доставка; брокер, СВХ, СБКТС или сертификат, ОГПО — рыночные диапазоны"})
            st.dataframe(pd.DataFrame(lines), hide_index=True, use_container_width=True)
            for n in filter(None, r["примечания"].split("; ")):
                st.warning(n)
    st.caption("Не учтены: тарифные льготы по инвестконтрактам и промсборке, преференции по происхождению, спорные "
               "трактовки — на вкладке «Спорные вопросы». Рыночные расходы для грузовиков и техники — ориентиры, "
               "официальных тарифов СБКТС и ЭПСМ нет.")
    remember(DEFAULTS)
