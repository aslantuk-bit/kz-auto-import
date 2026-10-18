"""Советы по экономии для конкретной машины из калькулятора.

for_car() возвращает:
  general — список советов {id, kind, text, saving}, отсортированный по выгоде (saving, тг);
            kind: «сейчас» (можно сделать с этой машиной), «выбор» (другая машина или код), «внимание»;
  routes  — короткий совет к строке маршрута в сравнении {route_id: текст};
  lines   — совет к строке разбивки {route_id: {платёж: текст}}.
Тот же алгоритм — в docs/tips.js; совпадение текстов проверяет web/parity_test.mjs.
"""
import math

import calc
from calc import EUR, Car

ROUTES = (("dt", "ДТ", "третьи"), ("ptd", "ПТД", "третьи"), ("kg_ul", "ЕАЭС_ЮЛ", "третьи"),
          ("kg_fl", "ЕАЭС_ФЛ", "третьи"), ("ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ"), ("ru_fl", "ЕАЭС_ФЛ", "РФ_РБ"))
MRP_NEXT, MRP_NEXT_YEAR = 4693, 2027   # проект закона о бюджете на 2027–2029 годы (блок G)


def _r(x):
    """Округление «половина вверх» — так же, как Math.round в tips.js."""
    return math.floor(x + 0.5)


def _num(x):
    return f"{_r(x):,}".replace(",", " ")


def tg(x):
    return _num(x) + " тг"


def mln(x):
    t = _r(abs(x) / 1e5)
    return f"{t // 10},{t % 10} млн тг"


def money(x):
    """Сумма без знака: до миллиона — в тенге, дальше — в миллионах."""
    return tg(abs(x)) if abs(x) < 1e6 else mln(x)


def eur(x):
    return _num(x) + " €"


def _blocked(r):
    return any(b in r["примечания"] for b in calc.BLOCKING.split("|"))


def for_car(price_eur, deliv_eur, fuel, cc, age, age_reg, year, month, today_year, today_month):
    """year, month — выпуск машины; today_* — текущая дата (для «до 31 декабря» и «до 3-летия»)."""
    def run(mode="ДТ", origin="третьи", **over):
        a = dict(price=price_eur, fuel=fuel, cc=cc, age=age, age_reg=age_reg, deliv=deliv_eur)
        a.update(over)
        return calc.calc(Car(a["price"], a["fuel"], a["cc"], a["age"], mode, origin, a["age_reg"], a["deliv"]))

    rows = {rid: run(mode, origin) for rid, mode, origin in ROUTES}
    # лучший из маршрутов с той же ценой покупки (третьи страны): у России и Беларуси цена — их рынка
    best_id = min((rid for rid in ("dt", "ptd") if not _blocked(rows[rid])), key=lambda k: rows[k]["итого_обязательные"])
    best = rows[best_id]["итого_обязательные"]
    dt, ptd = rows["dt"], rows["ptd"]
    general, routes, lines = [], {}, {rid: {} for rid, _, _ in ROUTES}

    def tip(id_, kind, text, saving=0):
        general.append({"id": id_, "kind": kind, "text": text, "saving": _r(saving)})

    # 1. Сбор за регистрацию: календарный возраст растёт 1 января
    reg_now = calc.reg_fee(Car(1, fuel, cc, age, возраст_рег=age_reg))
    reg_next = calc.reg_fee(Car(1, fuel, cc, age, возраст_рег=age_reg + 1))
    if reg_next > reg_now:
        d = reg_next - reg_now
        text = (f"Зарегистрируйте до 31.12.{today_year}: с 1 января сбор станет {tg(reg_next)} "
                f"(+{money(d)}), машина для сбора — на год старше")
        tip("reg_year_end", "сейчас", text, d)
        for rid in lines:
            lines[rid]["сбор_первичная_регистрация"] = text
    elif age_reg >= 3:
        younger = calc.reg_fee(Car(1, fuel, cc, 2, возраст_рег=2))
        text = (f"Ставка максимальная: у машины {today_year - 2} года выпуска сбор {tg(younger)}, "
                f"у {today_year - 1}–{today_year} — {tg(calc.reg_fee(Car(1, fuel, cc, 1, возраст_рег=1)))}")
        tip("reg_younger", "выбор", f"Машина {today_year - 2} года выпуска или моложе: сбор за регистрацию "
                                    f"{tg(younger)} вместо {tg(reg_now)}", reg_now - younger)
        for rid in lines:
            lines[rid]["сбор_первичная_регистрация"] = text

    # 2. Объём: границы утильсбора и акциза
    if fuel != "электро" and cc > 2000:
        alt = 3000 if cc > 3000 else 2000
        d = dt["итого_обязательные"] - run(cc=alt)["итого_обязательные"]
        if d > 0:
            what = "без акциза за объём, утильсбор " if cc > 3000 else "утильсбор "
            alt_util = calc.util(Car(1, fuel, alt, age))
            text = f"С объёмом до {_num(alt)} см³ — {what}{tg(alt_util)}: дешевле на {money(d)}"
            tip("volume", "выбор", f"Машина с объёмом до {_num(alt)} см³: дешевле на {money(d)}", d)
            for rid in ("dt", "ptd", "kg_ul", "kg_fl"):
                lines[rid]["утильсбор"] = text
                if cc > 3000:
                    lines[rid]["акциз"] = text
    for rid in ("ru_ul", "ru_fl"):
        third = calc.util(Car(1, fuel, cc, age))
        lines[rid]["утильсбор"] = (f"Коэффициент 2 для России и Беларуси: из третьих стран утильсбор "
                                   f"{tg(third)} вместо {tg(rows[rid]['утильсбор'])}")

    # 3. Порог акциза 10%: по ДТ — от цены с доставкой
    base = dt["таможенная_стоимость_кзт"]
    lim = calc.LUX_THRESHOLD
    if dt["акциз_10pct"] > 0:
        over = (base - lim) / EUR
        d = dt["итого_обязательные"] - run(price=price_eur - over - 1)["итого_обязательные"]
        text = (f"Цена с доставкой выше порога акциза ({mln(lim)}) на {eur(over)}: ниже порога акциз 10% "
                f"не платится — около {money(d)} меньше")
        tip("lux", "выбор", text, d)
        lines["dt"]["акциз"] = text
    elif base > 0.9 * lim:
        tip("lux_near", "внимание", f"До порога акциза 10% осталось {eur((lim - base) / EUR)} с учётом доставки: "
                                    "его превышение добавит 10% стоимости и НДС с этой суммы")

    # 4. ДТ или ПТД
    ptd_ok = not _blocked(ptd)
    if ptd_ok and ptd["итого_обязательные"] < dt["итого_обязательные"]:
        d = dt["итого_обязательные"] - ptd["итого_обязательные"]
        routes["dt"] = f"По ПТД дешевле на {money(d)}"
        routes["ptd"] = f"Дешевле ДТ на {money(d)}: доставка в базу не входит"
        tip("ptd", "сейчас", f"Физлицу — оформить по ПТД: дешевле ДТ на {money(d)} (одна машина для себя, "
                             "один СБКТС в год)", d)
    elif ptd_ok:
        d = ptd["итого_обязательные"] - dt["итого_обязательные"]
        routes["ptd"] = f"Дороже ДТ на {money(d)}"
        be = _breakeven(run, ptd["итого_обязательные"])
        if be is not None and be > deliv_eur:
            routes["dt"] = f"ПТД станет выгоднее при доставке больше {eur(be)}"
    elif age > 5:
        routes["ptd"] = "Старше 5 лет: ЭПТС по ПТД не оформят — только ДТ"

    # 4а. ПТД и дни рождения машины
    if age <= 5:
        if age < 3:
            by, bm = year + 3, month
            later = run("ПТД", age=3, age_reg=by - year)
            text_age = f"С {bm:02d}.{by} машине 3 года: единая ставка {tg(later['ЕТП_СТП'])} вместо {tg(ptd['ЕТП_СТП'])}"
            lines["ptd"]["ЕТП_СТП"] = text_age
            if later["итого_обязательные"] < best and (by, bm) > (today_year, today_month):
                tip("ptd_wait", "сейчас", f"Подождать до {bm:02d}.{by} и оформить по ПТД: всего {money(later['итого_обязательные'])} "
                                          f"вместо {money(best)} сейчас (вместе со сбором за регистрацию)",
                    best - later["итого_обязательные"])
        elif age <= 5:
            lines["ptd"]["ЕТП_СТП"] = (f"ПТД — пока машине не больше 5 полных лет, до {month:02d}.{year + 6}: потом "
                                       "ЭПТС по ПТД не оформят")
            tip("ptd_deadline", "внимание", f"ПТД доступен до {month:02d}.{year + 6}, пока машине не больше 5 полных лет: "
                                            "потом ЭПТС по ПТД не оформят")

    # 5. Доставка в таможенной стоимости
    if deliv_eur > 0:
        d = dt["итого_обязательные"] - run(deliv=0)["итого_обязательные"]
        if d > 0:
            text = (f"Из них {money(d)} — с доставки: участок по ЕАЭС выделите в счёте отдельно, он в базу не входит")
            lines["dt"]["НДС"] = text
            tip("delivery", "сейчас", f"Разделить счёт за доставку: до границы ЕАЭС и дальше. Доставка добавляет к "
                                      f"платежам по ДТ {money(d)}, участок по ЕАЭС в базу не входит", 0)

    # 6. Гибрид: код ТН ВЭД по тому, что мощнее
    if fuel == "гибрид_двс":
        d = dt["итого_обязательные"] - run(fuel="гибрид_эл")["итого_обязательные"]
        if d > 0:
            text = f"Если у гибрида мощнее электромотор, пошлина по ВТО 0%: дешевле на {money(d)}"
            tip("hybrid", "выбор", text, d)
            lines["dt"]["пошлина"] = text

    # 7. НДС для бизнеса
    if dt["НДС"] > 0:
        lines["dt"].setdefault("НДС", f"Юрлицу — плательщику НДС эти {tg(dt['НДС'])} вернутся зачётом")
        lines["kg_ul"]["НДС"] = f"Плательщику НДС эти {tg(rows['kg_ul']['НДС'])} вернутся зачётом"

    # 8. Кыргызстан, Россия
    for rid in ("kg_ul", "kg_fl"):
        d = rows[rid]["итого_обязательные"] - dt["итого_обязательные"]
        word = "дороже" if d > 0 else "дешевле"
        routes[rid] = f"Регистрация в РК не подтверждена; по платежам {word} ДТ на {money(d)}"
    lines["kg_fl"]["за_рубежом"] = "Пошлина по ЕТТ, без казахстанских ставок ВТО, и НДС Кыргызстана 12%"
    lines["kg_ul"]["за_рубежом"] = "Пошлина по ЕТТ, без казахстанских ставок ВТО; НДС Кыргызстана продавец возвращает"
    for rid in ("ru_ul", "ru_fl"):
        d = rows[rid]["итого_обязательные"] - best
        routes[rid] = f"{'Выше' if d > 0 else 'Ниже'} лучшего маршрута на {money(d)}: утильсбор ×2 (цена — рынка РФ/РБ)"

    # 9. Рост МРП с 1 января (пока следующий МРП — проект)
    if today_month >= 9 and calc.MRP_YEAR == today_year and MRP_NEXT_YEAR == today_year + 1:
        r = rows[best_id]
        mrp_part = r["утильсбор"] + r["сбор_первичная_регистрация"] + r["СРТС_и_номера"] + r["таможенный_сбор"]
        d = mrp_part * (MRP_NEXT / calc.MRP - 1)
        if d > 0:
            tip("mrp_next", "сейчас", f"До конца года: с 1 января МРП по проекту бюджета {_num(MRP_NEXT)} тг — "
                                      f"утильсбор и сборы для этой машины вырастут на {money(d)}", d)

    general.sort(key=lambda t: (-t["saving"], t["id"]))
    return {"general": general, "routes": routes, "lines": lines, "best": best_id}


def _breakeven(run, ptd_total):
    """Доставка, при которой ДТ сравнивается с ПТД; None — ДТ дешевле при любой разумной доставке."""
    lo, hi = 0.0, 100000.0
    if run(deliv=hi)["итого_обязательные"] < ptd_total:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if run(deliv=mid)["итого_обязательные"] < ptd_total else (lo, mid)
    return _r(lo / 10) * 10


def parity_cases():
    """Набор машин для сверки с docs/tips.js (web/parity_test.mjs читает out/tips_parity.json)."""
    from itertools import product
    cases = []
    for (fuel, cc), (year, month), price, deliv in product(
            (("бензин", 1600), ("бензин", 2000), ("бензин", 2500), ("бензин", 3500), ("дизель", 3000),
             ("гибрид_двс", 2000), ("гибрид_эл", 1500), ("электро", 0)),
            ((2026, 3), (2025, 1), (2024, 12), (2023, 6), (2021, 6), (2020, 1), (2015, 5)),
            (8000, 15000, 25000, 60000, 150000), (0, 2000, 6000)):
        today_year, today_month = 2026, 10
        months = (today_year - year) * 12 + (today_month - month)
        args = dict(price_eur=price, deliv_eur=deliv, fuel=fuel, cc=cc, age=max(months // 12, 0),
                    age_reg=today_year - year, year=year, month=month, today_year=today_year, today_month=today_month)
        cases.append({"args": args, "out": for_car(**args)})
    return cases


if __name__ == "__main__":
    import json
    from paths import OUT
    (OUT / "tips_parity.json").write_text(json.dumps(parity_cases(), ensure_ascii=False))
    print(len(parity_cases()), "машин для сверки советов")
