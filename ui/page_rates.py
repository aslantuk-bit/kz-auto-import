"""База ставок: поиск, фильтры, карточка записи с нормой и ссылкой."""
import pandas as pd
import streamlit as st

from ui.common import load_params, load_rates, load_table, money

RELIABILITY = {"А": "А — текст акта", "Б": "Б — разъяснение госоргана", "В": "В — СМИ",
               "Г": "Г — рыночная оценка", "Д": "Д — спорно"}
SHOW = ["id", "блок", "вид_платежа", "категория_ТС", "тип_двигателя", "объём_от_см3", "объём_до_см3",
        "возраст_от_лет", "возраст_до_лет", "субъект", "происхождение", "режим", "ставка_адвалорная_пct",
        "ставка_специфическая", "ставка_МРП", "коэффициент", "сумма_тг_2026", "достоверность", "правовой_акт", "статья"]
LABELS = {"вид_платежа": "платёж", "категория_ТС": "категория ТС", "тип_двигателя": "двигатель",
          "объём_от_см3": "см³ от", "объём_до_см3": "см³ до", "возраст_от_лет": "лет от", "возраст_до_лет": "лет до",
          "ставка_адвалорная_пct": "%", "ставка_специфическая": "за ед.", "ставка_МРП": "МРП",
          "сумма_тг_2026": "тг (2026)", "правовой_акт": "акт"}


def _filter(df):
    c1, c2, c3 = st.columns([2, 1.3, 1])
    blocks = c1.multiselect("Блок", sorted(df["блок"].unique()), placeholder="все блоки", key="rt_blocks")
    rel = c2.multiselect("Достоверность", list(RELIABILITY), format_func=RELIABILITY.get,
                         placeholder="любая", key="rt_rel")
    current = c3.toggle("Только действующие", value=True, key="rt_current")
    text = st.text_input("Поиск", placeholder="например: электромобиль, 8703 23, ст. 615, Решение № 59",
                         key="rt_text")
    if blocks:
        df = df[df["блок"].isin(blocks)]
    if rel:
        df = df[df["достоверность"].isin(rel)]
    if current:
        df = df[df["актуальна"] == "да"]
    if text.strip():
        hay = df.fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        for word in text.lower().split():
            df = df[hay.loc[df.index].str.contains(word, regex=False)]
    return df


def _card(row):
    st.subheader(f"{row['id']} · {row['вид_платежа']}")
    st.markdown(f"**{row['блок']}** · этап: {row['этап']} · получатель: {row['получатель']}")
    fields = [(k, row[k]) for k in ["категория_ТС", "категория_ЕЭК", "код_ТНВЭД", "тип_двигателя", "субъект",
                                    "происхождение", "режим", "ставка_текст", "минимум", "база", "формула",
                                    "сумма_тг_2026", "действует_с", "действует_по", "статус_проверки", "примечание"]
              if pd.notna(row[k]) and str(row[k]).strip()]
    for k, v in fields:
        st.markdown(f"**{k.replace('_', ' ')}:** {money(v) if k == 'сумма_тг_2026' else v}")
    st.markdown(f"**Норма:** {row['правовой_акт']}" + (f", {row['статья']}" if pd.notna(row["статья"]) else ""))
    if pd.notna(row["url"]):
        st.markdown(f"[Открыть источник]({row['url']})")
    st.caption(f"Достоверность: {RELIABILITY.get(row['достоверность'], row['достоверность'])}. "
               f"Исходная запись: sources/raw/{row['исходный_файл']} № {row['исходный_номер']}.")


def render():
    st.title("База ставок")
    rates = load_rates()
    tab_rates, tab_params, tab_conds, tab_src = st.tabs(["Ставки", "Параметры", "Условия ввоза", "Нормативные акты"])
    with tab_rates:
        df = _filter(rates)
        st.caption(f"Найдено {len(df)} из {len(rates)}. Щёлкните строку, чтобы открыть карточку с нормой.")
        ev = st.dataframe(df[SHOW].rename(columns=LABELS), hide_index=True, use_container_width=True, height=420,
                          on_select="rerun", selection_mode="single-row", key="rt_table")
        sel = ev.selection.rows if ev and ev.selection else []
        if sel:
            _card(df.iloc[sel[0]])
    with tab_params:
        st.dataframe(load_params(), hide_index=True, use_container_width=True)
    with tab_conds:
        st.caption("Запреты и ограничения, которые влияют на ввоз и регистрацию, но не являются платежами.")
        st.dataframe(load_table("условия"), hide_index=True, use_container_width=True)
    with tab_src:
        st.dataframe(load_table("источники"), hide_index=True, use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn("ссылка")})
