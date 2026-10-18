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
    from ui.common import STATE_FILE
    STATE_FILE.unlink(missing_ok=True)
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


def test_inputs_survive():
    """Введённое в калькуляторе остаётся после ухода со страницы и в новом сеансе (state/inputs.json)."""
    from ui.common import STATE_FILE
    STATE_FILE.unlink(missing_ok=True)
    at = check(page("ui.page_calc", "render"), "калькулятор: исходные значения")
    at.number_input(key="calc_price").set_value(31000.0)
    at.number_input(key="calc_vol").set_value(2400)
    at.selectbox(key="calc_cur").set_value("USD")
    at.run()
    again = check(page("ui.page_calc", "render"), "калькулятор: новый сеанс")
    assert again.number_input(key="calc_price").value == 31000.0
    assert again.number_input(key="calc_vol").value == 2400
    assert again.selectbox(key="calc_cur").value == "USD"
    assert any("Как сэкономить на этой машине" in m.value for m in again.markdown)
    STATE_FILE.unlink(missing_ok=True)


def test_vehicles():
    at = check(page("ui.page_vehicles", "render"), "техника: грузовик")
    for group, kind in (("Мотоциклы", "moto"), ("Самоходная техника", "excavator"), ("Самоходная техника", "combine"),
                        ("Грузовики и спецмашины", "tractor_unit")):
        at.selectbox(key="vh_group").set_value(group)
        at.run()
        at.selectbox(key="vh_kind").set_value(kind)
        check(at, f"техника: {kind}")


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
    at = check(page("ui.page_misc", "update"), "актуализация")
    at.button(key="upd_offline").click()
    check(at, "актуализация: пересборка без интернета")


if __name__ == "__main__":
    for t in (test_inputs_survive, test_calc, test_vehicles, test_savings, test_analytics, test_rates, test_misc):
        t()
    print("все страницы отрисованы")
