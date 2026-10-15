"""Дымовые проверки страниц через AppTest: каждая отрисовывается без исключений.

Запуск: .venv/bin/python tests/test_app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402


def page(mod, fn):
    return AppTest.from_string(
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        f"import importlib; importlib.import_module({mod!r}).{fn}()\n", default_timeout=60)


def check(at, name):
    at.run()
    assert not at.exception, f"{name}: {at.exception}"
    print("ok ", name)
    return at


def test_calc():
    at = check(page("ui.page_calc", "render"), "калькулятор")
    assert any("Дешевле всего" in m.value for m in at.markdown)
    at.selectbox(key="calc_fuel").set_value("электро")
    check(at, "калькулятор: электромобиль")
    at.selectbox(key="calc_fuel").set_value("бензин")
    at.run()
    at.number_input(key="calc_vol").set_value(3500)
    at.selectbox(key="calc_year").set_value(2012)
    at.selectbox(key="calc_cur").set_value("USD")
    at.toggle(key="calc_market").set_value(True)
    at.toggle(key="calc_show_ru").set_value(True)
    check(at, "калькулятор: старый 3,5 л, USD, рынок, РФ")


def test_analytics():
    at = check(page("ui.page_analytics", "render"), "аналитика")
    at.selectbox(key="an_engine").set_value("Электромобиль")
    at.toggle(key="an_ru").set_value(True)
    check(at, "аналитика: электромобиль + РФ")


def test_savings():
    at = check(page("ui.page_savings", "render"), "как сэкономить")
    assert any("Как сэкономить" in t.value for t in at.title)


def test_rates():
    at = check(page("ui.page_rates", "render"), "база ставок")
    at.text_input(key="rt_text").set_value("электромобиль")
    at.toggle(key="rt_current").set_value(False)
    check(at, "база ставок: поиск")


def test_misc():
    check(page("ui.page_misc", "questions"), "спорные вопросы")
    check(page("ui.page_misc", "update"), "обновление")


if __name__ == "__main__":
    for t in (test_calc, test_savings, test_analytics, test_rates, test_misc):
        t()
    print("все страницы отрисованы")
