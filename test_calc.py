"""Проверки калькулятора: ручные расчёты по нормам и сверка констант с out/ставки.csv.

Запуск: .venv/bin/python test_calc.py (после build.py).
"""
import pandas as pd

import calc
from paths import OUT
from calc import Car, MRP, EUR

SRTS_PLATES = 4.05 * MRP


def close(a, b, tol=2):
    assert abs(a - b) <= tol, (a, b)


def test_petrol_2000_5y_dt():
    r = calc.calc(Car(15000, "бензин", 2000, 5, "ДТ"))
    v = 15000 * EUR
    assert r["ставка_пошлины"].startswith("ВТО")
    close(r["пошлина"], 0.15 * v)                     # ВТО 15% < ЕТТ 20%
    close(r["НДС"], 0.16 * (v + 0.15 * v))
    close(r["утильсбор"], 3.5 * 50 * MRP)
    close(r["сбор_первичная_регистрация"], 500 * MRP)
    close(r["итого_обязательные"], 0.15 * v + 6 * MRP + 0.16 * 1.15 * v
          + 3.5 * 50 * MRP + 500 * MRP + SRTS_PLATES)


def test_petrol_2000_5y_ptd():
    r = calc.calc(Car(15000, "бензин", 2000, 5, "ПТД"))
    close(r["ЕТП_СТП"], 2.7 * 2000 * EUR)             # 3–5 лет, 1800–2300 см³
    assert r["НДС"] == 0 and r["таможенный_сбор"] == 0


def test_new_ptd_value_bands():
    r = calc.calc(Car(30000, "бензин", 2000, 1, "ПТД"))
    close(r["ЕТП_СТП"], max(0.48 * 30000, 5.5 * 2000) * EUR)
    r = calc.calc(Car(8000, "бензин", 1500, 1, "ПТД"))
    close(r["ЕТП_СТП"], max(0.54 * 8000, 2.5 * 1500) * EUR)


def test_ev_new_dt():
    r = calc.calc(Car(30000, "электро", 0, 0, "ДТ"))
    v = 30000 * EUR
    assert r["пошлина"] == 0 and r["утильсбор"] == 0
    close(r["НДС"], 0.16 * v)
    close(r["сбор_первичная_регистрация"], 0.25 * MRP)


def test_new_ice_uses_ett():
    r = calc.calc(Car(25000, "бензин", 2000, 1, "ДТ"))
    assert r["ставка_пошлины"].startswith("ЕТТ")
    close(r["пошлина"], 0.15 * 25000 * EUR)
    r = calc.calc(Car(25000, "бензин", 2900, 1, "ДТ"))
    close(r["пошлина"], 0.125 * 25000 * EUR)


def test_old_petrol_wto_cap():
    # старше 7 лет, 2000 см³: 0,5 €/см³ = 1000 € → в коридоре 15–18% от 5000 € = 750…900 → 900
    r = calc.calc(Car(5000, "бензин", 2000, 10, "ДТ"))
    close(r["пошлина"], 0.18 * 5000 * EUR)


def test_russia_util_and_no_vat_for_individual():
    r = calc.calc(Car(15000, "бензин", 1600, 4, "ЕАЭС_ФЛ", "РФ_РБ"))
    close(r["утильсбор"], 136 * 50 * MRP)
    assert r["НДС"] == 0 and r["пошлина"] == 0
    r = calc.calc(Car(15000, "бензин", 1600, 4, "ЕАЭС_ЮЛ", "РФ_РБ"))
    close(r["НДС"], 0.16 * 15000 * EUR)


def test_excise_and_luxury():
    v_eur = 200000
    r = calc.calc(Car(v_eur, "бензин", 4400, 1, "ДТ"))
    v = v_eur * EUR
    close(r["акциз_объём"], 100 * 4400)
    assert v >= 18000 * MRP
    close(r["акциз_10pct"], 0.10 * v - 100 * 4400)


def test_delivery_in_dt_base_only():
    # ДТ: доставка до границы ЕАЭС входит в таможенную стоимость (ТК ЕАЭС ст. 40)
    r = calc.calc(Car(15000, "бензин", 2000, 5, "ДТ", доставка_eur=2000))
    base = 17000 * EUR
    close(r["пошлина"], 0.15 * base)
    close(r["НДС"], 0.16 * 1.15 * base)
    close(r["таможенная_стоимость_кзт"], base)
    close(r["доля_обязательных_pct"], 100 * r["итого_обязательные"] / (15000 * EUR), 1)
    # ПТД: база — цена покупки без перевозки (Кодекс РК ст. 350)
    a = calc.calc(Car(30000, "бензин", 2000, 1, "ПТД", доставка_eur=5000))
    b = calc.calc(Car(30000, "бензин", 2000, 1, "ПТД"))
    assert a["итого_обязательные"] == b["итого_обязательные"]
    close(a["итого_с_рыночными"] - b["итого_с_рыночными"], 5000 * EUR)
    # машина с рынка РФ/РБ: доставка из третьих стран не учитывается
    e = calc.calc(Car(15000, "бензин", 2000, 5, "ЕАЭС_ЮЛ", "РФ_РБ", доставка_eur=2000))
    assert e["доставка_кзт"] == 0
    close(e["НДС"], 0.16 * 15000 * EUR)
    # порог акциза 10% считается от таможенной стоимости с доставкой
    lim = calc.LUX_THRESHOLD / EUR
    r = calc.calc(Car(lim - 1000, "бензин", 2000, 1, "ДТ", доставка_eur=2000))
    assert r["акциз_10pct"] > 0
    assert calc.calc(Car(lim - 1000, "бензин", 2000, 1, "ДТ"))["акциз_10pct"] == 0


def test_chain_through_kyrgyzstan_and_armenia():
    base = 17000 * EUR                                    # цена 15 000 € + доставка 2 000 € до границы КР
    # физлицо через КР, новая машина: ЕТТ 15%, НДС КР 12%, сбор 0,4%; в РК НДС нет
    r = calc.calc(Car(15000, "бензин", 2000, 1, "ЕАЭС_ФЛ", доставка_eur=2000, страна="КГ"))
    close(r["пошлина_там"], 0.15 * base)
    close(r["НДС_там"], 0.12 * 1.15 * base)
    close(r["сборы_там"], 0.004 * base)
    assert r["НДС"] == 0 and r["пошлина"] == 0 and "не подтверждена" in r["примечания"]
    close(r["итого_обязательные"], r["за_рубежом"] + 3.5 * 50 * MRP + 0.25 * MRP + SRTS_PLATES)
    # юрлицо через КР, б/у 5 лет: ЕТТ 20% (ВТО там нет), НДС КР возвращён, в РК НДС 16% с цены покупки в КР
    r = calc.calc(Car(15000, "бензин", 2000, 5, "ЕАЭС_ЮЛ", доставка_eur=2000, страна="КГ"))
    duty = max(0.20 * base, 0.36 * 2000 * EUR)
    close(r["пошлина_там"], duty)
    assert r["НДС_там"] == 0
    close(r["НДС"], 0.16 * (base + duty + 0.004 * base))
    # физлицо через РА, 8 лет: ЕТТ 2,2 €/см³ (1 800–2 300 см³), НДС РА 20%, экологический налог 2%
    r = calc.calc(Car(8000, "бензин", 2000, 8, "ЕАЭС_ФЛ", доставка_eur=2000, страна="АМ"))
    b = 10000 * EUR
    close(r["пошлина_там"], 2.2 * 2000 * EUR)
    close(r["НДС_там"], 0.20 * (b + 2.2 * 2000 * EUR))
    close(r["сборы_там"], 0.02 * b)
    # электромобиль до 5 лет: в КР без НДС, пошлина по ЕТТ 15%
    r = calc.calc(Car(30000, "электро", 0, 1, "ЕАЭС_ФЛ", доставка_eur=2000, страна="КГ"))
    assert r["НДС_там"] == 0
    close(r["пошлина_там"], 0.15 * 32000 * EUR)


def test_constants_match_rates_table():
    t = pd.read_csv(OUT / "ставки.csv")
    u = t[(t["блок"] == "Утилизационный платёж") & (t["актуальна"] == "да")
          & t["категория_ЕЭК"].fillna("").str.startswith("M1")]
    k1 = sorted(u[u["происхождение"].str.contains("коэффициент 1")]["коэффициент"])
    k2 = sorted(u[u["происхождение"].str.contains("коэффициент 2")]["коэффициент"])
    assert k1 == sorted((0,) + calc.UTIL_K1), k1
    assert k2 == sorted((calc.UTIL_EV["РФ_РБ"],) + calc.UTIL_K2), k2
    reg = t[(t["блок"] == "Сборы за регистрацию") & t["вид_платежа"].str.contains("первичн")
            & t["категория_ТС"].str.startswith("М1")]
    assert set(reg["ставка_МРП"]) == {0.25, 25, 50, 250, 500}, set(reg["ставка_МРП"])
    ptd = t[t["режим"].fillna("").str.startswith("ПТД") & t["стоимость_до"].notna()]
    assert sorted(ptd["стоимость_до"]) == [b[0] for b in calc.PTD_NEW[:-1]]


def run_all():
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} проверок пройдено")


if __name__ == "__main__":
    run_all()
