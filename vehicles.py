"""Калькулятор платежей при ввозе в РК грузовиков, тягачей, спецмашин, мотоциклов и самоходной техники.

Легковые M1 считает calc.py; здесь — остальное. Ставки на дату calc.AS_OF:
  таможня — блок H (sources/raw/H_customs_other*): ЕТТ ЕАЭС (Решение № 80, гр. 84 и 87) и ставки РК по ВТО
            (Решение № 59) — берётся меньшая, ВТО даёт условный выпуск; ПТД — только мотоциклы и грузовики до 5 т
            (совокупный платёж: пошлина по ЕТТ + НДС, Решение № 107, перечень № 74);
  РК      — блок I (НК, методика утильсбора, правила МСХ), утильсбор — блок C.
Маршруты: «dt» — ДТ из третьих стран, «ptd» — ПТД физлица (где разрешено), «ru_ul»/«ru_fl» — машина с рынка
России или Беларуси (утильсбор по коэффициенту 2). Тот же алгоритм — docs/vehicles.js (web/parity_test.mjs).
"""
import math
from dataclasses import dataclass

import calc
from calc import EUR, MRP

HP_PER_KW = 1.35962

# Вид техники: (название, группа, регистрирует, поля ввода)
KINDS = {
    "truck_diesel": ("Грузовик, дизель (8704 21–23)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "truck_petrol": ("Грузовик, бензин (8704 31–32)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "truck_ev": ("Электрогрузовик (8704 60)", "Грузовики и спецмашины", "МВД", ("mass", "payload")),
    "dumper": ("Карьерный самосвал (8704 10)", "Грузовики и спецмашины", "МВД", ("mass", "payload")),
    "tractor_unit": ("Седельный тягач (8701 21–29)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "eco4")),
    "crane": ("Автокран (8705 10)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "drill": ("Буровая установка на шасси (8705 20)", "Грузовики и спецмашины", "МВД", ("mass", "payload")),
    "fire": ("Пожарная машина (8705 30)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "mixer": ("Бетономешалка (8705 40)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "pump": ("Бетононасос (8705 90)", "Грузовики и спецмашины", "МВД", ("mass", "payload")),
    "tow": ("Эвакуатор, аварийная машина (8705 90)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "special_other": ("Прочая спецмашина на шасси (8705 90)", "Грузовики и спецмашины", "МВД", ("mass", "cc", "payload")),
    "moto": ("Мотоцикл (8711)", "Мотоциклы", "МВД", ("cc", "kw", "electric")),
    "farm_tractor": ("Трактор колёсный (8701 91–95)", "Самоходная техника", "МИО", ("kw",)),
    "crawler": ("Трактор гусеничный (8701 30)", "Самоходная техника", "МИО", ("kw",)),
    "combine": ("Комбайн зерноуборочный (8433 51)", "Самоходная техника", "МИО", ("kw",)),
    "forklift": ("Вилочный погрузчик с ДВС (8427 20)", "Самоходная техника", "МИО", ("kw",)),
    "forklift_el": ("Электропогрузчик (8427 10)", "Самоходная техника", "МИО", ("kw",)),
    "loader": ("Фронтальный погрузчик (8429 51)", "Самоходная техника", "МИО", ("kw",)),
    "excavator": ("Экскаватор полноповоротный (8429 52)", "Самоходная техника", "МИО", ("kw",)),
    "bulldozer": ("Бульдозер (8429 11/19)", "Самоходная техника", "МИО", ("kw",)),
    "grader": ("Грейдер (8429 20)", "Самоходная техника", "МИО", ("kw",)),
    "roller": ("Каток дорожный (8429 40)", "Самоходная техника", "МИО", ("kw",)),
}
TRUCKS = {k for k, v in KINDS.items() if v[1] == "Грузовики и спецмашины"}
SELF = {k for k, v in KINDS.items() if v[1] == "Самоходная техника"}
VAT_OFFSET = {"forklift", "forklift_el", "loader", "excavator", "bulldozer", "grader", "roller"}  # ПП № 1199
SPEC_8705 = {"crane": (0.10, 0.28, 0.08), "drill": (0.075, None, None), "fire": (0.05, 0.6, "used5"),
             "mixer": (0.15, 0.5, 0.10), "pump": (0.10, None, 0.05), "tow": (0.13, 0.6, 0.05),
             "special_other": (0.05, 0.04, "used5")}   # ЕТТ адвалор, минимум €/см³ для б/у, ВТО РК
FLAT = {"crawler": (0.075, 0.0), "combine": (0.05, None), "forklift": (0.05, None), "forklift_el": (0.0, None),
        "loader": (0.05, 0.0), "excavator": (0.05, 0.0), "bulldozer": (0.05, 0.0), "grader": (0.03, 0.0),
        "roller": (0.05, 0.0), "dumper": (0.05, 0.0)}

ROUTES = (("dt", "ДТ", "третьи"), ("ptd", "ПТД", "третьи"), ("ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ"), ("ru_fl", "ЕАЭС_ФЛ", "РФ_РБ"))
# Рыночные оценки по опубликованным прайсам (блок J, 18.10.2026): брокер и СВХ — «Г»; СБКТС на грузовик и
# сертификат ТР ТС 010/031 на технику — «Д» (цен в РК не найдено, ориентир по РФ)
MARKET = {"брокер": 100_000, "СВХ": 45_000, "СВХ_техника": 60_000, "СВХ_мото": 30_000, "СБКТС": 250_000,
          "СБКТС_мото": 120_000, "ЭПТС": 30_000, "сертификат": 300_000}
OGPO = {"N1": 2.09, "N": 3.98, "moto": 1.0}   # коэффициент к базовой премии 1,9 МРП (Закон об ОГПО, ст. 19)


@dataclass
class Machine:
    kind: str
    price_eur: float
    age: int = 0                 # полных лет с выпуска (для таможни)
    age_reg: int | None = None   # для сбора за регистрацию — «включая год выпуска»
    delivery_eur: float = 0.0
    mass: float = 0.0            # полная масса, т (грузовики, тягачи, спецмашины)
    payload: float = 0.0         # грузоподъёмность, т (налог на транспорт)
    cc: int = 0                  # объём двигателя, см³
    kw: float = 0.0              # мощность, кВт (тракторы, самоходные, мотоциклы)
    eco4: bool = True            # тягач: экокласс 4 и выше
    electric: bool = False       # мотоцикл электрический
    mode: str = "ДТ"
    origin: str = "третьи"

    @property
    def рег(self):
        return self.age if self.age_reg is None else self.age_reg


def _r(x):
    return math.floor(x + 0.5)


def ptd_allowed(m: Machine):
    return m.kind == "moto" or (m.kind in ("truck_diesel", "truck_petrol") and m.mass <= 5)


def duty_ett(m: Machine, base):
    """Пошлина по ЕТТ, тг. base — таможенная стоимость в тенге."""
    k, a, cc = m.kind, m.age, m.cc
    spec = lambda eur_cc: eur_cc * cc * EUR  # noqa: E731
    if k == "truck_diesel":
        if a >= 7:
            return spec(1.0)
        if m.mass <= 5:
            return max(0.10 * base, spec(0.13)) if 5 <= a < 7 and cc <= 2500 else 0.10 * base
        if m.mass <= 20:
            if a < 3:
                return 0.15 * base
            return max(0.10 * base, spec(0.18)) if a >= 5 else 0.10 * base
        return 0.05 * base if a < 3 else 0.10 * base
    if k == "truck_petrol":
        if a >= 7:
            return spec(1.0)
        if m.mass <= 5 and a < 3 and cc > 2800:
            return 0.125 * base
        return 0.15 * base
    if k == "truck_ev":
        return 0.15 * base
    if k == "tractor_unit":
        if a >= 7:
            return spec(1.0)
        return (0.05 if m.eco4 else 0.10) * base if a < 3 else 0.10 * base
    if k in SPEC_8705:
        rate, mn, _ = SPEC_8705[k]
        return max(rate * base, spec(mn)) if (a >= 3 and mn) else rate * base
    if k == "moto":
        if m.electric or cc <= 250:
            return 0.14 * base
        return 0.15 * base if cc <= 800 else 0.10 * base
    if k == "farm_tractor":
        return (0.05 if a < 3 else 0.10) * base if m.kw <= 18 else 0.10 * base
    return FLAT[k][0] * base


def duty_wto(m: Machine, base):
    """Ставка РК по ВТО (Решение № 59), тг; None — позиции нет в перечне."""
    k, a = m.kind, m.age
    if k == "truck_diesel":
        if m.mass <= 5:
            return 0.10 * base if (a >= 7 or (5 <= a < 7 and m.cc <= 2500)) else None
        if m.mass <= 20:
            return 0.10 * base if (a < 3 or a >= 5) else None
        return 0.10 * base if a >= 7 else None
    if k == "truck_petrol":
        if m.mass <= 5:
            return 0.15 * base if (a >= 7 and m.cc <= 2800) else 0.10 * base
        return 0.10 * base if a < 3 else (0.15 * base if a >= 7 else None)
    if k == "tractor_unit":
        return 0.10 * base if a >= 7 else None
    if k in SPEC_8705:
        w = SPEC_8705[k][2]
        if w == "used5":
            return 0.05 * base if a >= 3 else None
        return None if w is None else w * base
    if k == "farm_tractor":
        return 0.05 * base if (m.kw > 75 and a < 3) else 0.0
    if k in FLAT:
        return None if FLAT[k][1] is None else FLAT[k][1] * base
    return None


def _band(v, bands):
    for top, val in bands:
        if top is None or v <= top:
            return val
    return bands[-1][1]


def util_coef(m: Machine):
    """Коэффициент утильсбора (× 50 МРП), блок C; 0 — не облагается."""
    ru = m.origin == "РФ_РБ"
    if m.kind == "moto" or m.kind in VAT_OFFSET or m.kind == "crawler":
        return 0.0                                   # мото, строительная техника 8426–8430, гусеничные (Д)
    if m.kind in ("farm_tractor", "combine"):
        if ru:
            return 250.0
        hp = m.kw * HP_PER_KW
        bands = (((60, 2), (130, 5.5), (220, 17), (340, 29), (380, 29), (None, 40)) if m.kind == "farm_tractor"
                 else ((160, 9), (220, 23), (255, 32), (325, 38), (400, 38), (None, 45)))
        return _band(hp, bands)
    if m.kind == "truck_ev":
        return 60.0 if ru else 0.0
    if m.mass > 50:
        return 0.0
    if m.kind == "tractor_unit" and m.mass >= 12:
        return 164.0 if ru else 11.0
    if ru:
        return 164.0
    return _band(m.mass, ((2.5, 3.5), (3.5, 7.5), (5, 7.5), (8, 8), (12, 9.5), (20, 10.5), (50, 20.5)))


def reg_fee(m: Machine):
    """Сбор за первичную регистрацию, тг (НК ст. 615 п. 3)."""
    if m.kind in SELF or m.kind == "moto":
        return 0.25 * MRP
    a = m.рег
    if a < 2:
        return 0.25 * MRP
    if a < 3:
        return 240 * MRP
    if m.kind == "tractor_unit":
        return (350 if a < 7 else 2500) * MRP
    return (350 if a < 5 else 2500) * MRP


def docs_fee(m: Machine):
    """Техпаспорт и номера, тг (НК ст. 667): МВД — 1,25 + 2,8 (мото 1,4); МИО — 0,5 + 1."""
    if m.kind in SELF:
        return 1.5 * MRP
    return (1.25 + (1.4 if m.kind == "moto" else 2.8)) * MRP


def transport_tax(m: Machine):
    """Налог на транспорт в год, тг (НК ст. 565)."""
    if m.kind in SELF:
        return 3 * MRP
    if m.kind == "moto":
        return (1 if m.kw <= 55 else 10) * MRP
    if m.kind == "dumper" and m.mass >= 40:
        return 0.0
    return _band(m.payload, ((1, 3), (1.5, 5), (5, 7), (None, 9))) * MRP


def _market(m: Machine):
    if m.kind in SELF:
        return MARKET["брокер"] + MARKET["СВХ_техника"] + MARKET["сертификат"]
    if m.kind == "moto":
        return MARKET["брокер"] + MARKET["СВХ_мото"] + MARKET["СБКТС_мото"] + MARKET["ЭПТС"] + 1.9 * MRP * OGPO["moto"]
    ogpo = 1.9 * MRP * (OGPO["N1"] if m.mass <= 3.5 else OGPO["N"])
    return MARKET["брокер"] + MARKET["СВХ"] + MARKET["СБКТС"] + MARKET["ЭПТС"] + ogpo


def calc_machine(m: Machine) -> dict:
    v = m.price_eur * EUR
    third = m.origin == "третьи"
    deliv = m.delivery_eur * EUR if third else 0.0
    base = v + (deliv if m.mode == "ДТ" else 0.0)
    r = {"пошлина": 0.0, "ставка_пошлины": "—", "ЕТП_СТП": 0.0, "таможенный_сбор": 0.0, "акциз": 0.0, "НДС": 0.0}
    flags = []
    if m.mode == "ДТ":
        ett, wto = duty_ett(m, base), duty_wto(m, base)
        if wto is not None and wto <= ett:
            r["пошлина"], r["ставка_пошлины"] = wto, "ВТО (Решение № 59)"
            flags.append("условный выпуск: обращение только в РК")
        else:
            r["пошлина"], r["ставка_пошлины"] = ett, "ЕТТ (Решение № 80)"
        r["таможенный_сбор"] = calc.CUSTOMS_FEE_MRP * MRP
        r["НДС"] = calc.VAT * (base + r["пошлина"])
        if m.kind in VAT_OFFSET:
            flags.append("НДС можно уплатить методом зачёта — фактически 0, если держать технику 5 лет (ПП № 1199)")
    elif m.mode == "ПТД":
        duty = duty_ett(m, v)            # к совокупному платежу — ЕТТ (ставки ВТО — спорно)
        r["ЕТП_СТП"] = duty + calc.VAT * (v + duty)
        r["ставка_пошлины"] = "СТП (ЕТТ + НДС)"
        if not ptd_allowed(m):
            flags.append("ПТД нельзя: не товар для личного пользования (Решение № 107, прил. 6) — регистрация невозможна")
    elif m.mode == "ЕАЭС_ЮЛ":
        r["НДС"] = calc.VAT * v
    if m.origin == "РФ_РБ" and util_coef(m) > 0:
        flags.append("утильсбор по коэффициенту 2 для ввоза из России и Беларуси")
    r["утильсбор"] = 50 * MRP * util_coef(m)
    r["сбор_первичная_регистрация"] = reg_fee(m)
    r["СРТС_и_номера"] = docs_fee(m)
    gov = ("пошлина", "ЕТП_СТП", "таможенный_сбор", "НДС", "утильсбор", "сбор_первичная_регистрация", "СРТС_и_номера")
    r["итого_обязательные"] = sum(r[k] for k in gov)
    # + банк за перевод продавцу; посредник-закупщик — только при покупке в третьих странах (calc.BANK_PCT, AGENT_KZT)
    r["рыночные_оценка"] = ((_market(m) + calc.AGENT_KZT) if third else (0 if m.kind in SELF else 1.9 * MRP * OGPO["N"])) \
        + calc.BANK_PCT * v
    r["доставка_кзт"] = deliv
    r["итого_с_рыночными"] = r["итого_обязательные"] + r["рыночные_оценка"] + deliv
    r["стоимость_кзт"] = v
    r["таможенная_стоимость_кзт"] = base if m.mode == "ДТ" else (v if m.mode == "ПТД" else 0.0)
    r["налог_на_транспорт_год"] = transport_tax(m)
    r["регистрирует"] = ("МИО (гостехинспекция)" if m.kind in SELF else "МВД (спецЦОН)")
    if m.kind == "tractor_unit" and m.рег < 7:
        flags.append("международному перевозчику тягач до 7 лет регистрируется без сбора до 01.01.2028 (НК ст. 830)")
    if m.kind in SELF:
        flags.append("ОГПО для машин, которые регистрирует МИО, не требуется")
    r["примечания"] = "; ".join(flags)
    return {k: (_r(x) if isinstance(x, float) else x) for k, x in r.items()}


def routes_for(m: Machine):
    """Строки сравнения по маршрутам: [(id, режим, происхождение)] — ПТД только там, где он разрешён."""
    return [(rid, mode, origin) for rid, mode, origin in ROUTES if mode != "ПТД" or ptd_allowed(m)]


def _money(x):
    x = abs(x)
    if x < 1e6:
        return f"{_r(x):,}".replace(",", " ") + " тг"
    t = _r(x / 1e5)
    return f"{t // 10},{t % 10} млн тг"


def tips(m: Machine, today_year):
    """Советы под конкретную машину: [{id, text, saving}] по убыванию выгоды. Тот же алгоритм — vehicles.js."""
    from dataclasses import replace
    out = []
    dt = calc_machine(replace(m, mode="ДТ", origin="третьи"))
    now, nxt = reg_fee(m), reg_fee(replace(m, age_reg=m.рег + 1))
    if nxt > now:
        out.append({"id": "reg_year_end", "saving": _r(nxt - now),
                    "text": f"Зарегистрируйте до 31.12.{today_year}: с 1 января сбор за регистрацию станет "
                            f"{_money(nxt)} (+{_money(nxt - now)})"})
    if m.kind in TRUCKS and now >= 2500 * MRP:
        lim = 7 if m.kind == "tractor_unit" else 5
        out.append({"id": "reg_younger", "saving": _r(now - 350 * MRP),
                    "text": f"Сбор 2 500 МРП — у машин {lim} лет и старше по году выпуска; машина моложе платит 350 МРП: "
                            f"дешевле на {_money(now - 350 * MRP)}"})
    if ptd_allowed(m):
        ptd = calc_machine(replace(m, mode="ПТД", origin="третьи"))
        if ptd["итого_обязательные"] < dt["итого_обязательные"]:
            d = dt["итого_обязательные"] - ptd["итого_обязательные"]
            out.append({"id": "ptd", "saving": d, "text": f"Физлицу — оформить по ПТД: дешевле ДТ на {_money(d)}"})
    if m.kind in VAT_OFFSET and dt["НДС"] > 0:
        out.append({"id": "vat_offset", "saving": dt["НДС"],
                    "text": f"НДС {_money(dt['НДС'])} можно уплатить методом зачёта (ПП № 1199): фактически 0, если "
                            "технику не продавать и не вывозить 5 лет"})
    if util_coef(replace(m, origin="РФ_РБ")) > 0:
        ru = calc_machine(replace(m, mode="ЕАЭС_ФЛ", origin="РФ_РБ"))
        d = ru["утильсбор"] - dt["утильсбор"]
        if d > 0:
            out.append({"id": "ru", "saving": 0, "text": f"Не везите с рынка России и Беларуси: утильсбор там по "
                                                         f"коэффициенту 2 — больше на {_money(d)}"})
    if dt["ставка_пошлины"].startswith("ВТО"):
        out.append({"id": "wto", "saving": 0, "text": "Пошлина по ставке РК по ВТО ниже ЕТТ, но выпуск условный: "
                                                      "продать технику за пределы РК можно только с доплатой до ЕТТ"})
    out.sort(key=lambda t: (-t["saving"], t["id"]))
    return out


def parity_cases():
    """Набор машин для сверки с docs/vehicles.js (out/vehicles_parity.json)."""
    from itertools import product
    out = []
    for kind, price, age, mass, cc, kw in product(KINDS, (8000, 40000, 120000), (0, 4, 6, 9), (3.5, 12, 30),
                                                  (2400, 6700, 12000), (40, 120, 250)):
        for rid, mode, origin in ROUTES:
            m = Machine(kind, price, age, age + 1, 3000, mass, mass * 0.6, cc, kw, age % 2 == 0, kw > 200, mode, origin)
            out.append({"in": m.__dict__, "out": calc_machine(m), "tips": tips(m, 2026)})
    return out


if __name__ == "__main__":
    import json
    from paths import OUT
    cases = parity_cases()
    (OUT / "vehicles_parity.json").write_text(json.dumps(cases, ensure_ascii=False))
    print(len(cases), "расчётов прочей техники для сверки")
