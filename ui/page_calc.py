"""Калькулятор: одна машина → платежи по всем маршрутам ввоза."""
import pandas as pd
import streamlit as st

import calc
from ui import charts
from ui.common import (COMP_LABEL, COMP_NORM, COMPONENTS, FUEL_LABEL, ROUTES, RU_ROUTES, TODAY,
                       fx_rates, long_components, money, pct)


def _ages(year, month):
    """Возраст для таможни (полных лет с выпуска) и для сбора за регистрацию (год − год выпуска)."""
    months = (TODAY.year - year) * 12 + (TODAY.month - month) - (1 if TODAY.day < 15 else 0)
    return max(months // 12, 0), TODAY.year - year


def _inputs():
    fx = fx_rates()
    st.subheader("Машина")
    c1, c2 = st.columns([3, 2])
    price = c1.number_input("Стоимость", min_value=0.0, value=15000.0, step=500.0, format="%.0f", key="calc_price")
    cur = c2.selectbox("Валюта", list(fx), index=0, key="calc_cur")
    st.caption("Цена сделки плюс доставка до границы ЕАЭС. Для ПТД берётся цена покупки без доставки. "
               f"Курсы НБРК на {TODAY:%d.%m.%Y}.")
    fuel = st.selectbox("Двигатель", list(FUEL_LABEL), format_func=FUEL_LABEL.get, key="calc_fuel")
    ev = fuel == "электро"
    vol = st.number_input("Объём двигателя, см³", min_value=0, max_value=9000, value=2000,
                          step=100, disabled=ev, key="calc_vol")
    c3, c4 = st.columns(2)
    year = c3.selectbox("Год выпуска", list(range(TODAY.year, 1994, -1)), index=4, key="calc_year")
    month = c4.selectbox("Месяц выпуска", list(range(1, 13)), index=5, key="calc_month")
    market = st.toggle("Добавить рыночные расходы", value=False, key="calc_market",
                       help="ОГПО, брокер, СВХ, СБКТС, ЭПТС — по серединам рыночных диапазонов, не госплатежи.")
    price_eur = price * fx[cur] / fx["EUR"]
    return price_eur, fuel, 0 if ev else int(vol), year, month, market


def render():
    st.title("Калькулятор ввоза")
    st.caption("Все платежи при ввозе легкового автомобиля в РК с постановкой на учёт, сразу по шести маршрутам. "
               f"Ставки на {TODAY:%d.%m.%Y}, МРП {money(calc.MRP)} тг.")
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        price_eur, fuel, vol, year, month, with_market = _inputs()
    age, age_reg = _ages(year, month)
    rows = []
    for rid, mode, origin, label, who in ROUTES:
        car = calc.Car(price_eur, fuel, vol, age, mode, origin, age_reg)
        r = calc.calc(car)
        r["акциз"] = r["акциз_объём"] + r["акциз_10pct"]
        rows.append({"id": rid, "маршрут": label, "как": who, **r})
    df = pd.DataFrame(rows)
    total_col = "итого_с_рыночными" if with_market else "итого_обязательные"
    blocked = df["примечания"].str.contains("регистрация невозможна|нельзя передавать")
    ok = df[~blocked]
    best = ok.loc[ok[total_col].idxmin()]

    with right:
        st.subheader("Итог")
        st.markdown(f"Дешевле всего: **{best['маршрут']}** — {best['как'][0].lower() + best['как'][1:]}.")
        m2, m3 = st.columns(2)
        m2.metric("Платежи", money(best[total_col]) + " тг",
                  help="Обязательные госплатежи и утильсбор" + (" плюс рыночные расходы" if with_market else ""))
        m3.metric("От стоимости машины", pct(100 * best[total_col] / best["стоимость_кзт"]))
        st.caption(f"Стоимость {money(best['стоимость_кзт'])} тг ({money(price_eur)} €). "
                   f"Для таможни машине {age} полных лет, для сбора за регистрацию — {age_reg} "
                   "(считается «включая год выпуска»).")
        show_ru = st.toggle("Показать Россию и Беларусь на графике", value=False, key="calc_show_ru",
                            help="Утильсбор по коэффициенту 2 в десятки раз больше остальных платежей "
                                 "и сжимает остальные бары.")
        plot = df if show_ru else df[~df["маршрут"].isin(RU_ROUTES)]
        order = plot["маршрут"].tolist()
        st.altair_chart(charts.stacked(long_components(plot, "маршрут"), "маршрут", order,
                                       plot.rename(columns={"итого_обязательные": "итог"})[["маршрут", "итог"]]),
                        use_container_width=True)
        if not show_ru:
            ru = df[df["маршрут"].isin(RU_ROUTES)]
            st.caption("Россия/Беларусь: " + "; ".join(
                f"{r['маршрут'].split(' · ')[1]} — {money(r['итого_обязательные'], 'млн')} тг" for _, r in ru.iterrows()))

    st.subheader("Сравнение маршрутов")
    table = pd.DataFrame({
        "Маршрут": df["маршрут"],
        "Итого, тг": df[total_col].map(money),
        "От стоимости": (100 * df[total_col] / df["стоимость_кзт"]).map(pct),
        "Пошлина / ЕТП": (df["пошлина"] + df["ЕТП_СТП"]).map(money),
        "НДС": df["НДС"].map(money),
        "Акциз": df["акциз"].map(money),
        "Утильсбор": df["утильсбор"].map(money),
        "Сбор за регистрацию": df["сбор_первичная_регистрация"].map(money),
        "Налог на транспорт в год": df["налог_на_транспорт_год"].map(money),
        "Ограничения": df["примечания"],
    })
    st.dataframe(table, hide_index=True, use_container_width=True)

    st.subheader("Разбивка по маршруту")
    tabs = st.tabs([r[3] for r in ROUTES])
    for tab, (_, r) in zip(tabs, df.iterrows()):
        with tab:
            st.caption(r["как"] + (f" · ставка пошлины: {r['ставка_пошлины']}" if r["ставка_пошлины"] != "—" else ""))
            lines = [{"Платёж": COMP_LABEL[k], "Сумма, тг": money(r[k]), "Норма": COMP_NORM[k]}
                     for k, _, _ in COMPONENTS if r[k] > 0]
            lines.append({"Платёж": "Итого обязательные", "Сумма, тг": money(r["итого_обязательные"]), "Норма": ""})
            if with_market:
                lines.append({"Платёж": "Рыночные расходы (оценка)", "Сумма, тг": money(r["рыночные_оценка"]),
                              "Норма": "ОГПО, брокер, СВХ, СБКТС, ЭПТС — рыночные диапазоны"})
            st.dataframe(pd.DataFrame(lines), hide_index=True, use_container_width=True)
            if r["примечания"]:
                for n in r["примечания"].split("; "):
                    st.warning(n)
            st.caption(f"После регистрации — налог на транспорт около {money(r['налог_на_транспорт_год'])} тг в год "
                       "(НК ст. 565).")
