"""Что выгодно ввезти: цена за рубежом + доставка + платежи против медианы Kolesa по модели и году."""
import pandas as pd
import streamlit as st

from abroad import deals
from ui.common import money


@st.cache_data(show_spinner=False)
def _data():
    return deals.compute()


def _mln(v):
    return f"{v / 1e6:+.1f} млн".replace(".", ",").replace("-", "−")


def render():
    st.title("Что выгодно ввезти")
    d = _data()
    routes = ", ".join(r["name"] for r in d["routes"].values())
    st.caption(f"Медиана объявлений за рубежом + вывоз и доставка + все платежи по самому дешёвому маршруту + брокер, "
               f"СВХ, СБКТС — против медианы тех же модели и года на Kolesa.kz ({d['date'] or '—'}). За рубежом: "
               f"{routes}. В расчёт берутся модель и год, где и там, и на Kolesa не меньше {d['reliable']} объявлений "
               f"(мотоциклы и спецтехника: за рубежом от {d['reliable_other'][0]}, на Kolesa от "
               f"{d['reliable_other'][1]} — объявлений меньше, цифры ориентировочные).")
    cats = list(dict.fromkeys(r["категория"] for r in d["summary"]))
    if not cats:
        st.info("Данных пока нет.")
        return
    cat = st.segmented_control("Что ввозим", cats, default=cats[0], key="dl_cat") or cats[0]
    st.subheader("По моделям")
    s = pd.DataFrame([r for r in d["summary"] if r["категория"] == cat])
    st.dataframe(pd.DataFrame({
        "Модель": s["модель"], "Откуда": s["страна"],
        "В плюсе": s["в_плюсе"].astype(str) + " из " + s["годов"].astype(str),
        "Медиана выгоды": s["медиана_выгоды_кзт"].map(_mln),
        "Лучший год": s["лучший_год"].astype(str) + ": " + s["лучшая_выгода_кзт"].map(_mln),
        "Ввоз под ключ, тг": s["лучший_итого_кзт"].map(money), "Kolesa, тг": s["лучший_kolesa_кзт"].map(money)}),
        hide_index=True, use_container_width=True)
    st.subheader("По годам")
    pos = st.toggle("Только где ввоз дешевле", value=True, key="dl_pos")
    r = pd.DataFrame([x for x in d["rows"] if x["категория"] == cat and (not pos or x["выгода_кзт"] > 0)])
    if r.empty:
        st.info("Нет пар модель-год, где ввоз дешевле Kolesa.")
    else:
        st.dataframe(pd.DataFrame({
            "Модель": r["модель"], "Год": r["год"], "Откуда": r["страна"],
            "Что": r["детали"].fillna("") + r["режим"].fillna("").map(lambda m: f" · {m}" if m else ""),
            "Цена там, тг": r["цена_там_кзт"].map(money), "Платежи, тг": r["платежи_кзт"].map(money),
            "Доставка и услуги, тг": r["доставка_и_услуги_кзт"].map(money),
            "Ввоз под ключ, тг": r["итого_ввоз_кзт"].map(money), "Kolesa, тг": r["kolesa_медиана"].map(money),
            "Выгода": r["выгода_кзт"].map(_mln), "Выгода, %": r["выгода_pct"], "Kolesa": r["kolesa_url"]}),
            hide_index=True, use_container_width=True,
            column_config={"Kolesa": st.column_config.LinkColumn("Объявления", display_text="открыть")})
    st.caption("Цены объявлений — цены продавцов, а не сделок; пробег на Kolesa не учтён, комплектации могут не совпадать. "
               "Для 2021–2023 годов часто дешевле ПТД — он для себя, не для перепродажи партиями. Из ЕС продавцы "
               "проверяют конечного покупателя из-за санкций. Доставка и вывоз — ориентиры, ставку уточнять у перевозчика.")
