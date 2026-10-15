"""Спорные вопросы, обновление базы и выключение приложения."""
import contextlib
import importlib
import io
import os
import signal
import subprocess
import threading
from datetime import datetime

import streamlit as st

from ui.common import OUT, ROOT, load_table


def _step_build():
    import build
    importlib.reload(build).build()


def _step_tests():
    import calc
    import test_calc
    importlib.reload(calc)
    importlib.reload(test_calc).run_all()


def _step_scenarios():
    import calc
    importlib.reload(calc).write_scenarios()


def _step_report():
    import report
    importlib.reload(report).main()


STEPS = [("Сборка базы ставок", _step_build), ("Проверки калькулятора", _step_tests),
         ("Сетка сценариев", _step_scenarios), ("Книга Excel", _step_report)]


def questions():
    st.title("Спорные вопросы")
    st.caption("Что не подтверждено первоисточником или трактуется по-разному, и как это учтено в расчётах.")
    q = load_table("спорные")
    for i, r in q.iterrows():
        with st.expander(f"{i + 1}. {r['вопрос']}"):
            st.markdown(f"**В чём неясность.** {r['неясность']}")
            st.markdown(f"**Как учтено.** {r['как_учтено']}")


def update():
    st.title("Обновление")
    built = datetime.fromtimestamp((OUT / "ставки.csv").stat().st_mtime)
    st.markdown(f"База собрана **{built:%d.%m.%Y %H:%M}**. Ставки действуют на 15.10.2026.")
    st.markdown(
        "Когда ставка меняется:\n"
        "1. поправьте запись в `sources/raw/*.json` (A — таможня, B — Налоговый кодекс, C — утильсбор, "
        "D — регистрация и рынок);\n"
        "2. если ставка участвует в калькуляторе, поправьте константу в `calc.py` — "
        "проверки не дадут базе и калькулятору разойтись (в собранном приложении `calc.py` "
        "внутри программы: такая правка требует новой сборки, `build_app.sh`);\n"
        "3. новый МРП меняется в `build.py`, `calc.py` и параметрах;\n"
        "4. нажмите «Пересобрать».")
    st.caption(f"Папка данных: {ROOT}")
    if st.button("Пересобрать", type="primary", key="upd_run"):
        ok = True
        for title, step in STEPS:
            with st.status(title, expanded=False) as s:
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        step()
                except Exception as e:  # показываем ошибку шага, не роняя страницу
                    st.code(buf.getvalue()[-3000:] + f"\n{type(e).__name__}: {e}", language=None)
                    s.update(label=f"{title}: ошибка", state="error", expanded=True)
                    ok = False
                    break
                st.code(buf.getvalue()[-3000:] or "готово", language=None)
                s.update(label=f"{title}: готово", state="complete")
        st.cache_data.clear()
        if ok:
            st.success("База, сценарии и книга Excel пересобраны.")
        else:
            st.error("Пересборка остановилась на шаге с ошибкой — подробности в его выводе выше.")
    st.divider()
    st.markdown(f"Книга Excel: `{OUT / 'kz_auto_import_2026-10.xlsx'}`  \nБаза SQLite: `{OUT / 'kz_auto_import.sqlite'}`")
    c1, c2 = st.columns(2)
    if c1.button("Показать книгу Excel в Finder", key="upd_reveal"):
        subprocess.run(["open", "-R", str(OUT / "kz_auto_import_2026-10.xlsx")], check=False)
    if c2.button("Открыть папку исходных ставок", key="upd_raw"):
        subprocess.run(["open", str(ROOT / "sources" / "raw")], check=False)


def shutdown():
    """Кнопка в боковой панели: останавливает сервер после ответа браузеру."""
    if st.button("Выключить приложение", key="quit", help="Останавливает сервер. Запуск — снова значком."):
        st.info("Приложение выключено. Вкладку можно закрыть.")
        threading.Timer(0.7, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
