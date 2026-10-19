"""Калькулятор: одна машина → платежи по всем маршрутам ввоза."""
import pandas as pd
import streamlit as st

import calc
import glossary
import kolesa
import tips
from ui import charts
from ui.common import (COMP_LABEL, COMP_NORM, COMPONENTS, FUEL_LABEL, ROUTES, RU_ROUTES, TODAY,
                       as_of_line, fx_rates, keep, long_components, money, pct, remember)

YEARS = list(range(TODAY.year, 1994, -1))
DEFAULTS = {"calc_price": 15000.0, "calc_cur": "EUR", "calc_deliv": 2000.0, "calc_fuel": "бензин",
            "calc_vol": 2000, "calc_year": TODAY.year - 4, "calc_month": 6, "calc_market": False,
            "calc_show_ru": False, "calc_model": ""}
KIND = {"сейчас": "✅", "выбор": "🔁", "внимание": "⚠️"}


def _ages(year, month):
    """Возраст для таможни (полных лет с выпуска) и для сбора за регистрацию (год − год выпуска)."""
    months = (TODAY.year - year) * 12 + (TODAY.month - month) - (1 if TODAY.day < 15 else 0)
    return max(months // 12, 0), TODAY.year - year


def _inputs():
    fx = fx_rates()
    keep(DEFAULTS, valid={"calc_cur": list(fx), "calc_fuel": list(FUEL_LABEL), "calc_year": YEARS,
                          "calc_month": list(range(1, 13))})
    st.subheader("Машина")
    c1, c2 = st.columns([3, 2])
    price = c1.number_input("Цена покупки", min_value=0.0, step=500.0, format="%.0f", key="calc_price")
    cur = c2.selectbox("Валюта", list(fx), key="calc_cur")
    deliv = st.number_input("Доставка и страховка до границы ЕАЭС", min_value=0.0, step=100.0,
                            format="%.0f", key="calc_deliv",
                            help="В той же валюте, что и цена. Ориентиры: автовоз из Китая $2,5–4,5 тыс., "
                                 "из США $3,6–4,6 тыс. Дорога по ЕАЭС не входит, если выделена в документах. "
                                 "Для маршрута через Кыргызстан — доставка до границы КР.")
    st.caption("Цена — по договору в третьей стране, без доставки. По ДТ (в РК или в Кыргызстане) доставка входит "
               "в таможенную стоимость и увеличивает пошлину и НДС; по ПТД база — только цена покупки. Для России "
               f"и Беларуси цена — цена на их рынке. Курсы НБРК на {calc.FX_DATE:%d.%m.%Y}.")
    km = kolesa.models()
    names = dict(km)
    st.selectbox("Модель — для сравнения с ценами Kolesa", [""] + [k for k, _ in km], key="calc_model",
                 format_func=lambda k: names.get(k, "не выбрана"),
                 help="Необязательно. Покажет, сколько такие машины того же года стоят в объявлениях Kolesa.kz.")
    fuel = st.selectbox("Двигатель", list(FUEL_LABEL), format_func=FUEL_LABEL.get, key="calc_fuel")
    ev = fuel == "электро"
    vol = st.number_input("Объём двигателя, см³", min_value=0, max_value=9000, step=100, disabled=ev, key="calc_vol")
    c3, c4 = st.columns(2)
    year = c3.selectbox("Год выпуска", YEARS, key="calc_year")
    month = c4.selectbox("Месяц выпуска", list(range(1, 13)), key="calc_month")
    market = st.toggle("Доставка и рыночные расходы", key="calc_market",
                       help="Сама доставка, ОГПО, брокер, СВХ, СБКТС, ЭПТС, комиссия банка 0,5% и посредник за рубежом $500 — по серединам рыночных диапазонов, "
                            "не госплатежи.")
    price_eur = price * fx[cur] / fx["EUR"]
    deliv_eur = deliv * fx[cur] / fx["EUR"]
    return price_eur, deliv_eur, fuel, 0 if ev else int(vol), year, month, market


def render():
    st.title("Калькулятор ввоза")
    st.caption("Все платежи при ввозе легкового автомобиля в РК с постановкой на учёт, сразу по шести маршрутам. "
               + as_of_line() + ".")
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        price_eur, deliv_eur, fuel, vol, year, month, with_market = _inputs()
    age, age_reg = _ages(year, month)
    rows = []
    for rid, mode, origin, label, who in ROUTES:
        car = calc.Car(price_eur, fuel, vol, age, mode, origin, age_reg, deliv_eur)
        r = calc.calc(car)
        r["акциз"] = r["акциз_объём"] + r["акциз_10pct"]
        rows.append({"id": rid, "маршрут": label, "как": who, **r})
    df = pd.DataFrame(rows)
    total_col = "итого_с_рыночными" if with_market else "итого_обязательные"
    blocked = df["примечания"].str.contains(calc.BLOCKING)
    ok = df[~blocked]
    best = (ok if len(ok) else df).loc[(ok if len(ok) else df)[total_col].idxmin()]
    tp = tips.for_car(price_eur, deliv_eur, fuel, vol, age, age_reg, year, month, TODAY.year, TODAY.month)

    with right:
        st.subheader("Итог")
        st.markdown(f"Дешевле всего: **{best['маршрут']}** — {best['как'][0].lower() + best['как'][1:]}.")
        m2, m3 = st.columns(2)
        m2.metric("Платежи", money(best[total_col]) + " тг",
                  help="Обязательные госплатежи и утильсбор" + (" плюс доставка и рыночные расходы" if with_market else ""))
        m3.metric("От стоимости машины", pct(100 * best[total_col] / best["стоимость_кзт"]))
        customs = df.loc[df["id"] == "dt", "таможенная_стоимость_кзт"].iloc[0]
        st.caption(f"Цена покупки {money(best['стоимость_кзт'])} тг ({money(price_eur)} €), "
                   f"таможенная стоимость по ДТ с доставкой — {money(customs)} тг. "
                   f"Для таможни машине {age} полных лет, для сбора за регистрацию — {age_reg} "
                   "(считается «включая год выпуска»).")
        _tips_block(tp["general"])
        _kolesa_block(st.session_state.get("calc_model"), year, best)
        show_ru = st.toggle("Показать Россию и Беларусь на графике", key="calc_show_ru",
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
        "Как сэкономить": df["id"].map(lambda i: tp["routes"].get(i, "")),
        "Пошлина / ЕТП": (df["пошлина"] + df["ЕТП_СТП"]).map(money),
        "НДС": df["НДС"].map(money),
        "Акциз": df["акциз"].map(money),
        "Утильсбор": df["утильсбор"].map(money),
        "Сбор за регистрацию": df["сбор_первичная_регистрация"].map(money),
        "Налог на транспорт в год": df["налог_на_транспорт_год"].map(money),
        "Ограничения": df["примечания"],
    })
    st.dataframe(table, hide_index=True, use_container_width=True,
                 column_config={"Как сэкономить": st.column_config.TextColumn(width="large")})

    st.subheader("Разбивка по маршруту")
    tabs = st.tabs([r[3] for r in ROUTES])
    for tab, (_, r) in zip(tabs, df.iterrows()):
        with tab:
            st.caption(r["как"] + (f" · ставка пошлины: {r['ставка_пошлины']}" if r["ставка_пошлины"] != "—" else ""))
            hint = tp["lines"].get(r["id"], {})
            lines = [{"Платёж": COMP_LABEL[k], "Сумма, тг": money(r[k]), "Норма": COMP_NORM[k],
                      "Как сэкономить": hint.get(k, "")} for k, _, _ in COMPONENTS if r[k] > 0]
            lines.append({"Платёж": "Итого обязательные", "Сумма, тг": money(r["итого_обязательные"]), "Норма": "",
                          "Как сэкономить": tp["routes"].get(r["id"], "")})
            if with_market:
                if r["доставка_кзт"]:
                    lines.append({"Платёж": "Доставка и страховка до границы ЕАЭС", "Сумма, тг": money(r["доставка_кзт"]),
                                  "Норма": "ваша сумма; по ДТ входит в таможенную стоимость (ТК ЕАЭС ст. 40)"})
                lines.append({"Платёж": "Рыночные расходы (оценка)", "Сумма, тг": money(r["рыночные_оценка"]),
                              "Норма": "ОГПО, брокер, СВХ, СБКТС, ЭПТС, банк 0,5%, посредник за рубежом $500 — рыночные диапазоны"})
            _md_table(pd.DataFrame(lines).fillna(""))
            if r["примечания"]:
                for n in r["примечания"].split("; "):
                    st.warning(n)
            st.caption(f"После регистрации — налог на транспорт около {money(r['налог_на_транспорт_год'])} тг в год "
                       "(НК ст. 565).")

    _glossary()
    remember(DEFAULTS)


def _md_table(df):
    """Таблица с переносом длинных строк (st.dataframe обрезает текст)."""
    esc = lambda v: str(v).replace("|", "\\|")  # noqa: E731
    head = "| " + " | ".join(df.columns) + " |\n|" + "|".join("---:" if c == "Сумма, тг" else "---" for c in df.columns) + "|"
    st.markdown(head + "\n" + "\n".join("| " + " | ".join(esc(v) for v in row) + " |" for row in df.values))


def _kolesa_any(year):
    """Любая модель: один запрос к Kolesa из приложения (Kolesa может не ответить программе)."""
    with st.expander("Цена на Kolesa для другой модели"):
        st.caption("Адрес модели — из ссылки на Kolesa: kolesa.kz/cars/**toyota/alphard**/ → toyota/alphard. "
                   "Один запрос; если Kolesa не ответит программе, откройте выдачу по ссылке.")
        slug = st.text_input("Модель на Kolesa", placeholder="toyota/alphard", key="calc_kolesa_any").strip().strip("/")
        if slug and st.button(f"Узнать цену {year} года", key="calc_kolesa_go"):
            try:
                r = kolesa.fetch_live(slug, year)
                if r["n"] < kolesa.MIN_ADS:
                    st.info(f"Объявлений {year} года мало ({r['n']}). [Выдача]({kolesa.search_url(slug, year)})")
                else:
                    st.success(f"{slug} {year}: медиана {money(r['med'])} тг, разброс {money(r['p25'])}–"
                               f"{money(r['p75'])} тг по {r['n']} объявлениям из {r['found']}. Модель добавлена в "
                               "список сравнения.")
                    st.cache_data.clear()
            except RuntimeError as e:
                st.warning(f"{e}: [выдача на Kolesa]({kolesa.search_url(slug, year)})")


def _kolesa_block(slug, year, best):
    if not slug:
        _kolesa_any(year)
        return
    landed = best["стоимость_кзт"] + best["итого_с_рыночными"]
    c = kolesa.compare(slug, year, landed)
    with st.container(border=True):
        st.markdown(f"**Ввезти самому или купить в Казахстане** — {kolesa.NAMES.get(slug, slug)} {year} года")
        if c is None:
            st.caption(f"На Kolesa мало объявлений этого года — сравнить не с чем. [Открыть выдачу]({kolesa.search_url(slug, year)})")
            return
        a, b, d = st.columns(3)
        a.metric("Ввоз под ключ", money(landed, "млн") + " тг",
                 help="Цена покупки, доставка, все платежи и рыночные расходы по самому дешёвому маршруту")
        b.metric("Kolesa, медиана", money(c["med"], "млн") + " тг",
                 help=f"Половина объявлений дешевле, половина дороже; разброс {money(c['p25'], 'млн')}–"
                      f"{money(c['p75'], 'млн')} тг")
        d.metric("Ввоз выгоднее" if c["diff"] > 0 else "Купить здесь дешевле", money(abs(c["diff"]), "млн") + " тг")
        same = []
        if c.get("v"):
            same.append(f"обычно {c['v']} л")
        if c.get("f"):
            same.append(c["f"])
        st.caption(f"По {c['n']} объявлениям из {c['found']} ({', '.join(same)}), Kolesa.kz на "
                   f"{kolesa.load().get('date', '')[:10]}. Цены объявлений — цены продавцов, торг обычно 5–10%; "
                   f"машины в объявлениях уже на учёте в РК. [Объявления на Kolesa]({c['url']})")


def _tips_block(items):
    if not items:
        return
    with st.container(border=True):
        st.markdown("**Как сэкономить на этой машине**")
        def line(t):
            return f"{KIND[t['kind']]} {t['text']}"
        st.markdown("\n".join(f"- {line(t)}" for t in items[:5]))
        if len(items) > 5:
            with st.expander(f"Ещё {len(items) - 5}"):
                st.markdown("\n".join(f"- {line(t)}" for t in items[5:]))
        st.caption("✅ можно сделать с этой машиной · 🔁 если выбирать машину или уточнить код · ⚠️ учесть. "
                   "Порядок — по размеру выгоды.")


def _glossary():
    st.divider()
    st.subheader("ДТ и ПТД: в чём разница")
    st.markdown("| | ДТ — декларация на товары | ПТД — пассажирская таможенная декларация |\n|---|---|---|\n"
                + "\n".join(f"| **{k}** | {dt} | {ptd} |" for k, dt, ptd in glossary.DT_VS_PTD))
    st.subheader("Термины и сокращения")
    groups = dict.fromkeys(g for g, _, _ in glossary.TERMS)
    for g in groups:
        with st.expander(g):
            st.markdown("\n".join(f"- **{t}** — {d}" for gg, t, d in glossary.TERMS if gg == g))
