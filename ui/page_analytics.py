"""Аналитика по сетке сценариев out/сценарии.csv."""
import pandas as pd
import streamlit as st

import calc
from ui import charts
from ui.common import (ROUTE_COLOR, ROUTES, RU_ROUTES, SLOTS, load_rates, load_scenarios, long_components,
                       money, pct)

ROUTE_ORDER = [r[3] for r in ROUTES]
BASE_ROUTES = [r for r in ROUTE_ORDER if r not in RU_ROUTES]


def _controls(df):
    engines = df.drop_duplicates("двигатель")["двигатель"].tolist()
    c1, c2, c3 = st.columns(3)
    eng = c1.selectbox("Двигатель", engines, index=engines.index("Бензин 2.0 л"), key="an_engine")
    prices = sorted(df["стоимость_eur"].unique())
    price = c2.select_slider("Стоимость, €", prices, value=15000, key="an_price",
                             format_func=lambda v: money(v))
    ages = sorted(df["возраст"].unique())
    age = c3.select_slider("Возраст, лет", ages, value=4, key="an_age")
    return eng, price, age


def _findings(df, eng, price, age):
    cur = df[(df["двигатель"] == eng) & (df["стоимость_eur"] == price) & (df["возраст"] == age)]
    by = cur.set_index("маршрут")["итого_обязательные"]
    young = df[(df["двигатель"] == eng) & (df["стоимость_eur"] == price) & (df["маршрут"] == "Третьи страны · ДТ")]
    jump = young.set_index("возраст")["итого_обязательные"]
    out = []
    ok = cur[~cur["маршрут"].isin(RU_ROUTES) & ~cur["примечания"].fillna("").str.contains(calc.BLOCKING)]
    cheap = ok.set_index("маршрут")["итого_обязательные"].idxmin()
    out.append(f"Дешевле всего — **{cheap}**: {money(by[cheap], 'млн')} тг против "
               f"{money(by['Третьи страны · ДТ'], 'млн')} тг по ДТ из третьих стран.")
    out.append(f"Из России или Беларуси та же машина обойдётся в **{money(by['Россия/Беларусь · ФЛ'], 'млн')} тг** "
               f"платежей — в {by['Россия/Беларусь · ФЛ'] / by[cheap]:.0f} раз больше, почти целиком утильсбор.")
    if 2 in jump and 3 in jump:
        out.append(f"Переход машины из 2 в 3 года добавляет **{money(jump[3] - jump[2], 'млн')} тг** по ДТ: "
                   "сбор за регистрацию растёт с 50 до 500 МРП, пошлина переходит на ставки для б/у.")
    p, d = by.get("Третьи страны · ПТД"), by["Третьи страны · ДТ"]
    if p is not None:
        word = "дешевле" if p < d else "дороже"
        out.append(f"ПТД для физлица здесь {word} ДТ на {money(abs(p - d), 'млн')} тг.")
    return out


def render():
    df = load_scenarios()
    st.title("Аналитика")
    st.caption("3 888 расчётов: 9 двигателей × 12 возрастов × 6 цен × 6 маршрутов. Машины из третьих стран — "
               f"с доставкой {money(calc.DELIVERY_EUR)} € до границы ЕАЭС (по ДТ она в таможенной стоимости, "
               "по ПТД — нет). Выберите машину-ориентир — графики ниже пересчитаются для неё.")
    eng, price, age = _controls(df)
    for line in _findings(df, eng, price, age):
        st.markdown("- " + line)

    show_ru = st.toggle("Показывать Россию и Беларусь", value=False, key="an_ru",
                        help="Утильсбор по коэффициенту 2 в десятки раз больше остальных платежей и сжимает шкалу.")
    routes = ROUTE_ORDER if show_ru else BASE_ROUTES
    colors = [ROUTE_COLOR[r] for r in routes]

    st.header("Из чего складывается платёж")
    cur = df[(df["двигатель"] == eng) & (df["стоимость_eur"] == price) & (df["возраст"] == age)
             & df["маршрут"].isin(routes)]
    st.altair_chart(charts.stacked(long_components(cur, "маршрут"), "маршрут", routes,
                                   cur.rename(columns={"итого_обязательные": "итог"})[["маршрут", "итог"]]),
                    use_container_width=True)
    st.caption("Обязательные платежи без рыночных расходов. По ДТ основная доля — пошлина и НДС, "
               "через ЕАЭС — утильсбор и сбор за регистрацию.")

    st.header("Возраст: скачок на трёх годах")
    a = df[(df["двигатель"] == eng) & (df["стоимость_eur"] == price) & df["маршрут"].isin(routes)].copy()
    a["млн"] = a["итого_обязательные"] / 1e6
    a["тг"] = a["итого_обязательные"].map(lambda v: money(v) + " тг")
    st.altair_chart(charts.lines(a, "возраст", "млн", "маршрут", routes, colors, "возраст, лет",
                                 "платежи, млн тг", charts.RU_AXIS, rule_x=3, rule_label="3 года",
                                 tooltip_fmt="тг"), use_container_width=True)
    st.caption("С трёх лет сбор за первичную регистрацию — 500 МРП (2,16 млн тг) вместо 50 МРП, "
               "для электромобилей — 250 МРП. По ДТ пошлина переходит на ставки РК по ВТО для б/у (15%). "
               "По ПТД с трёх лет единая ставка считается от объёма, а не от цены, а старше 5 лет она выше "
               "(3,0–5,7 €/см³ вместо 1,5–3,6) — второй скачок на графике.")

    st.header("Цена: фиксированные платежи бьют по дешёвым машинам")
    p = df[(df["двигатель"] == eng) & (df["возраст"] == age) & df["маршрут"].isin(routes)].copy()
    p["доля"] = p["доля_обязательных_pct"]
    p["тг"] = p["доля"].map(lambda v: pct(v))
    p["цена"] = p["стоимость_eur"].map(lambda v: money(v) + " €")
    price_order = [money(v) + " €" for v in sorted(p["стоимость_eur"].unique())]
    st.altair_chart(charts.lines(p, "цена", "доля", "маршрут", routes, colors, "стоимость машины",
                                 "платежи, % от стоимости", tooltip_fmt="тг", x_sort=price_order),
                    use_container_width=True)
    st.caption("Утильсбор, сбор за регистрацию и минимумы пошлины в €/см³ не зависят от цены, "
               "поэтому у дешёвой машины их доля в разы выше.")

    st.header("ПТД или ДТ для физлица")
    h = df[(df["двигатель"] == eng) & df["маршрут"].isin(["Третьи страны · ПТД", "Третьи страны · ДТ"])]
    w = h.pivot_table(index=["возраст", "стоимость_eur"], columns="маршрут", values="итого_обязательные").reset_index()
    w["разница"] = (w["Третьи страны · ПТД"] - w["Третьи страны · ДТ"]) / 1e6
    w.loc[w["возраст"] > 5, "разница"] = 0.0   # сравнивать не с чем: ЭПТС не оформят
    w["подпись"] = w.apply(lambda r: "нет ЭПТС" if r["возраст"] > 5 else f"{r['разница']:+.1f}".replace(".", ","),
                           axis=1)
    w["цена"] = w["стоимость_eur"].map(lambda v: money(v) + " €")
    st.altair_chart(charts.heatmap(w, "цена", "возраст", "разница", "подпись", "стоимость машины", "возраст, лет",
                                   "ПТД минус ДТ, млн тг", x_sort=price_order,
                                   y_sort=sorted(w["возраст"].unique())), use_container_width=True)
    st.caption("Синий — ПТД дешевле, красный — дороже. По ДТ машина выпускается условно по ставкам ВТО и "
               "обращается только в РК. С 26.09.2026 ЭПТС по ПТД оформляют только на машины до 5 лет "
               "(приказ МПС № 474, по СМИ), поэтому старше 5 лет ПТД фактически закрыт.")

    st.header("Тип двигателя")
    e = df[(df["стоимость_eur"] == price) & (df["возраст"] == age) & (df["маршрут"] == "Третьи страны · ДТ")]
    eng_order = e.sort_values("итого_обязательные")["двигатель"].tolist()
    st.altair_chart(charts.stacked(long_components(e, "двигатель"), "двигатель", eng_order,
                                   e.rename(columns={"итого_обязательные": "итог"})[["двигатель", "итог"]],
                                   y_title=None), use_container_width=True)
    st.caption("Маршрут «Третьи страны · ДТ». Электромобиль и гибрид с более мощным электромотором идут по пошлине 0% "
               "(перечень ВТО) и без утильсбора; свыше 3 000 см³ добавляются акциз и утильсбор 11,5.")

    st.header("Утильсбор: Россия и Беларусь против остальных")
    r = load_rates()
    u = r[(r["блок"] == "Утилизационный платёж") & (r["актуальна"] == "да")
          & r["категория_ЕЭК"].fillna("").str.startswith("M1")].copy()
    def band(row):
        if pd.isna(row["объём_до_см3"]) and pd.isna(row["объём_от_см3"]):
            return "Электромобиль"
        lo = 0 if pd.isna(row["объём_от_см3"]) else int(row["объём_от_см3"])
        return f"свыше {lo - 1} см³" if pd.isna(row["объём_до_см3"]) else f"{lo}–{int(row['объём_до_см3'])} см³"
    u["объём"] = u.apply(band, axis=1)
    u["откуда"] = u["происхождение"].map(lambda s: "Россия, Беларусь" if "РФ" in s else "Другие страны и сборка РК")
    u["млн"] = u["сумма_тг_2026"] / 1e6
    u["подпись"] = u["сумма_тг_2026"].map(lambda v: money(v, "млн"))
    dom = ["Другие страны и сборка РК", "Россия, Беларусь"]
    band_order = ["Электромобиль", "0–1000 см³", "1001–2000 см³", "2001–3000 см³", "свыше 3000 см³"]
    st.altair_chart(charts.bars(u, "млн", "объём", "откуда", dom, [SLOTS[0], SLOTS[7]], "подпись", "млн тг",
                                y_order=band_order), use_container_width=True)
    st.caption("Легковые M1, 50 МРП × коэффициент. Коэффициент 2 для ввоза из РФ и РБ действует с 07–08.05.2026 "
               "(приказ МЭПР № 54). Возраст и статус ввозящего на утильсбор не влияют.")

    st.header("Надёжность базы")
    q = r.groupby(["блок", "достоверность"]).size().reset_index(name="записей")
    piv = q.pivot_table(index="блок", columns="достоверность", values="записей", fill_value=0)
    piv["всего"] = piv.sum(axis=1)
    st.dataframe(piv.sort_values("всего", ascending=False), use_container_width=True,
                 height=36 * (len(piv) + 1) + 4)
    st.caption("А — текст нормативного акта, Б — разъяснение госоргана, В — СМИ, Г — рыночная оценка, "
               "Д — спорно или не подтверждено. Подробности — в разделах «База ставок» и «Спорные вопросы».")
