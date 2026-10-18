"""Ввоз авто в РК: калькулятор, аналитика и база ставок. Запуск: ./launch.sh"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st  # noqa: E402

from ui import page_analytics, page_calc, page_deals, page_misc, page_rates, page_savings, page_vehicles  # noqa: E402
from ui.common import as_of_line  # noqa: E402

st.set_page_config(page_title="Ввоз авто в РК", page_icon=":material/directions_car:", layout="wide")

nav = st.navigation([
    st.Page(page_calc.render, title="Калькулятор", default=True),
    st.Page(page_vehicles.render, title="Грузовики, мото, спецтехника", url_path="vehicles"),
    st.Page(page_deals.render, title="Что выгодно ввезти", url_path="deals"),
    st.Page(page_savings.render, title="Как сэкономить", url_path="savings"),
    st.Page(page_analytics.render, title="Аналитика", url_path="analytics"),
    st.Page(page_rates.render, title="База ставок", url_path="rates"),
    st.Page(page_misc.questions, title="Спорные вопросы", url_path="questions"),
    st.Page(page_misc.update, title="Актуализация", url_path="update"),
])
with st.sidebar:
    st.caption(as_of_line())
    st.caption("Автор — TAS · Aseke. Бесплатно, в помощь всем, кто везёт машину в Казахстан.")
    page_misc.shutdown()
nav.run()
