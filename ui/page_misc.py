"""Спорные вопросы, актуализация базы и выключение приложения."""
import importlib
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime

import pandas as pd
import streamlit as st

import actualize
from ui.common import OUT, ROOT, as_of_line, load_table


def questions():
    st.title("Спорные вопросы")
    st.caption("Что не подтверждено первоисточником или трактуется по-разному, и как это учтено в расчётах.")
    q = load_table("спорные")
    for i, r in q.iterrows():
        with st.expander(f"{i + 1}. {r['вопрос']}"):
            st.markdown(f"**В чём неясность.** {r['неясность']}")
            st.markdown(f"**Как учтено.** {r['как_учтено']}")


ICON = {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "change": "🔄", "fail": "❌"}
STATUS = {"ok": "в порядке", "info": "к сведению", "warn": "нужна проверка", "change": "найдено новое значение",
          "fail": "ошибка"}


def _after_change():
    st.cache_data.clear()
    for m in ("calc", "glossary", "savings"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])


def _run(offline):
    with st.status("Актуализация…", expanded=True) as box:
        data = actualize.run(offline=offline, progress=lambda t: box.write(f"· {t}"))
        s = data["итог"]
        bad = s["fail"] or s["warn"] or s["change"]
        box.update(label="Готово: " + ("есть пункты для проверки" if bad else "всё сверено"),
                   state="error" if s["fail"] else "complete", expanded=False)
    _after_change()


def _report(data):
    s = data["итог"]
    c = st.columns(5)
    for col, key in zip(c, ("ok", "change", "warn", "fail", "info")):
        col.metric(f"{ICON[key]} {STATUS[key]}", s[key])
    st.caption(f"Проверка {datetime.fromisoformat(data['конец']):%d.%m.%Y %H:%M}. Ставки сверены "
               f"{datetime.fromisoformat(data['as_of']):%d.%m.%Y}: дата сдвигается, только когда все акты и ставки "
               "совпали с текстами.")
    todo = [i for i in data["пункты"] if i.get("действие")]
    if todo:
        st.subheader("Что нужно решить")
        for n, i in enumerate(todo):
            with st.container(border=True):
                st.markdown(f"{ICON[i['статус']]} **{i['что']}** — {i['подробно']}"
                            + (f" · [текст акта]({i['ссылка']})" if i.get("ссылка") else ""))
                a = i["действие"]
                label = (f"Применить новое значение и пересобрать" if a["type"] == "param"
                         else "Я проверил ставки — отметить редакцию проверенной")
                if st.button(label, key=f"act_{n}"):
                    actualize.apply(a)
                    if a["type"] == "param":
                        _run(offline=True)
                    st.rerun()
    st.subheader("Все проверки")
    st.dataframe(pd.DataFrame([{"": ICON[i["статус"]], "Этап": i["этап"], "Что": i["что"], "Результат": i["подробно"],
                                "Источник": i.get("ссылка")} for i in data["пункты"]]),
                 hide_index=True, use_container_width=True,
                 column_config={"Источник": st.column_config.LinkColumn(display_text="открыть")})


def update():
    st.title("Актуализация")
    st.markdown(
        "Одна кнопка проверяет базу и пересобирает всё:\n"
        "1. **курсы НБРК** на сегодня — применяются сразу;\n"
        "2. **редакции актов** — НК, Кодекс о таможенном регулировании, ПП № 171, решения ЕЭК № 59 и № 107, "
        "методика утильсбора, закон об ОГПО, ЕТТ гр. 87 — по зеркалу ИЗПИ и сайту ЕЭК;\n"
        "3. **ставки в текстах** — НДС, МРП, таможенный сбор, порог акциза 10%: найденное значение сверяется с "
        "расчётом и **не применяется без вашего подтверждения**;\n"
        "4. **пересборка** — база ставок, сценарии, «Как сэкономить», Excel, данные сайта;\n"
        "5. **самопроверка** — нормы калькулятора, сверка констант с базой, сетка сценариев.")
    st.caption(f"Сейчас: {as_of_line()}. Папка данных: {ROOT}")
    c1, c2 = st.columns([1, 1])
    if c1.button("Проверить и актуализировать", type="primary", key="upd_run", use_container_width=True):
        _run(offline=False)
    if c2.button("Только пересобрать (без интернета)", key="upd_offline", use_container_width=True):
        _run(offline=True)
    data = actualize.last_report()
    if data:
        _report(data)
    else:
        st.info("Проверок ещё не было — нажмите «Проверить и актуализировать».")

    with st.expander("Задать параметры вручную — например, МРП нового года"):
        p = actualize.load(actualize.PARAMS)
        a, b, c, d = st.columns(4)
        mrp = a.number_input("МРП, тг", value=int(p["MRP"]), step=1, key="pm_mrp")
        year = b.number_input("Год МРП", value=int(p["MRP_year"]), step=1, key="pm_year")
        vat = c.number_input("НДС, %", value=float(p["VAT"] * 100), step=1.0, key="pm_vat")
        fee = d.number_input("Таможенный сбор, МРП", value=int(p["CUSTOMS_FEE_MRP"]), step=1, key="pm_fee")
        st.caption("Меняйте только по тексту закона. Ставки пошлин, утильсбора и сборов за регистрацию — в "
                   "sources/raw и calc.py (в собранном приложении — новой сборкой).")
        if st.button("Сохранить и пересобрать", key="pm_save"):
            actualize.set_params(MRP=int(mrp), MRP_year=int(year), VAT=round(vat / 100, 4), CUSTOMS_FEE_MRP=int(fee))
            _run(offline=True)
            st.rerun()

    st.subheader("Сайт")
    st.markdown("Сайт aslantuk-bit.github.io/kz-auto-import берёт ставки, курсы и тексты из одного файла "
                "`data.json`. Кнопка заливает свежий файл в репозиторий — сайт обновится через 1–2 минуты.")
    if st.button("Обновить сайт", key="upd_site"):
        try:
            url = actualize.publish_site()
            st.success(f"Данные сайта обновлены: [коммит]({url}).")
        except Exception as e:
            st.error(f"Не получилось: {e}")

    if actualize.JOURNAL.exists():
        with st.expander("Журнал проверок"):
            st.dataframe(pd.read_csv(actualize.JOURNAL).tail(20).iloc[::-1], hide_index=True,
                         use_container_width=True)
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
