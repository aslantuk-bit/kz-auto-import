/* Советы по экономии для конкретной машины — перенос tips.py (тексты совпадают, проверка: node web/parity_test.mjs).
   forCar(K, C, args) → { general: [{id, kind, text, saving}], routes: {id: текст}, lines: {id: {платёж: текст}}, best } */
(function (root) {
  "use strict";
  const ROUTES = [["dt", "ДТ", "третьи"], ["ptd", "ПТД", "третьи"], ["kg_ul", "ЕАЭС_ЮЛ", "третьи"],
    ["kg_fl", "ЕАЭС_ФЛ", "третьи"], ["ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ"], ["ru_fl", "ЕАЭС_ФЛ", "РФ_РБ"]];
  const MRP_NEXT = 4693, MRP_NEXT_YEAR = 2027;   // проект закона о бюджете на 2027–2029 годы

  const r0 = (x) => Math.floor(x + 0.5);
  const num = (x) => String(r0(x)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const tg = (x) => num(x) + " тг";
  const mln = (x) => { const t = r0(Math.abs(x) / 1e5); return `${Math.floor(t / 10)},${t % 10} млн тг`; };
  const money = (x) => (Math.abs(x) < 1e6 ? tg(Math.abs(x)) : mln(x));
  const eur = (x) => num(x) + " €";
  const pad = (m) => String(m).padStart(2, "0");

  // результат calc.js → имена полей calc.py, которые использует алгоритм
  // числа округляются, как в calc.py (round в конце расчёта)
  const rnd = (r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, typeof v === "number" ? Math.round(v) : v]));
  const py = (r0_) => { const r = rnd(r0_); return { ...r, "итого_обязательные": r.total, "ЕТП_СТП": r.etp, "НДС": r.vat, "утильсбор": r.util,
    "сбор_первичная_регистрация": r.reg_fee, "СРТС_и_номера": r.docs, "таможенный_сбор": r.customs_fee,
    "акциз_10pct": r.excise_lux, "таможенная_стоимость_кзт": r.customs_value }; };

  function forCar(K, C, a) {
    const { price_eur, deliv_eur, fuel, cc, age, age_reg, year, month, today_year, today_month } = a;
    const run = (mode = "ДТ", origin = "третьи", over = {}) => {
      const x = { price: price_eur, fuel, cc, age, age_reg, deliv: deliv_eur, ...over };
      return py(K.calc({ price_eur: x.price, fuel: x.fuel, cc: x.cc, age: x.age, mode, origin, age_reg: x.age_reg, delivery_eur: x.deliv }));
    };
    const reg = (f, c, ag, ar) => K.regFee({ fuel: f, cc: c, age: ag, age_reg: ar });
    const util = (f, c, ag, origin = "третьи") => K.util({ fuel: f, cc: c, age: ag, origin });
    const rows = Object.fromEntries(ROUTES.map(([id, mode, origin]) => [id, run(mode, origin)]));
    const bestId = ["dt", "ptd"].filter((id) => !rows[id].blocked).reduce((p, q) => (rows[q]["итого_обязательные"] < rows[p]["итого_обязательные"] ? q : p));
    const best = rows[bestId]["итого_обязательные"];
    const dt = rows.dt, ptd = rows.ptd;
    const general = [], routes = {}, lines = Object.fromEntries(ROUTES.map(([id]) => [id, {}]));
    const tip = (id, kind, text, saving = 0) => general.push({ id, kind, text, saving: r0(saving) });

    // 1. Сбор за регистрацию
    const regNow = reg(fuel, cc, age, age_reg), regNext = reg(fuel, cc, age, age_reg + 1);
    if (regNext > regNow) {
      const d = regNext - regNow;
      const text = `Зарегистрируйте до 31.12.${today_year}: с 1 января сбор станет ${tg(regNext)} (+${money(d)}), машина для сбора — на год старше`;
      tip("reg_year_end", "сейчас", text, d);
      for (const id in lines) lines[id]["сбор_первичная_регистрация"] = text;
    } else if (age_reg >= 3) {
      const younger = reg(fuel, cc, 2, 2);
      const text = `Ставка максимальная: у машины ${today_year - 2} года выпуска сбор ${tg(younger)}, у ${today_year - 1}–${today_year} — ${tg(reg(fuel, cc, 1, 1))}`;
      tip("reg_younger", "выбор", `Машина ${today_year - 2} года выпуска или моложе: сбор за регистрацию ${tg(younger)} вместо ${tg(regNow)}`, regNow - younger);
      for (const id in lines) lines[id]["сбор_первичная_регистрация"] = text;
    }

    // 2. Объём
    if (fuel !== "электро" && cc > 2000) {
      const alt = cc > 3000 ? 3000 : 2000;
      const d = dt["итого_обязательные"] - run("ДТ", "третьи", { cc: alt })["итого_обязательные"];
      if (d > 0) {
        const what = cc > 3000 ? "без акциза за объём, утильсбор " : "утильсбор ";
        const text = `С объёмом до ${num(alt)} см³ — ${what}${tg(util(fuel, alt, age))}: дешевле на ${money(d)}`;
        tip("volume", "выбор", `Машина с объёмом до ${num(alt)} см³: дешевле на ${money(d)}`, d);
        for (const id of ["dt", "ptd", "kg_ul", "kg_fl"]) { lines[id]["утильсбор"] = text; if (cc > 3000) lines[id]["акциз"] = text; }
      }
    }
    for (const id of ["ru_ul", "ru_fl"])
      lines[id]["утильсбор"] = `Коэффициент 2 для России и Беларуси: из третьих стран утильсбор ${tg(util(fuel, cc, age))} вместо ${tg(rows[id]["утильсбор"])}`;

    // 3. Порог акциза 10%
    const base = dt["таможенная_стоимость_кзт"], lim = C.LUX_THRESHOLD;
    if (dt["акциз_10pct"] > 0) {
      const over = (base - lim) / C.EUR;
      const d = dt["итого_обязательные"] - run("ДТ", "третьи", { price: price_eur - over - 1 })["итого_обязательные"];
      const text = `Цена с доставкой выше порога акциза (${mln(lim)}) на ${eur(over)}: ниже порога акциз 10% не платится — около ${money(d)} меньше`;
      tip("lux", "выбор", text, d);
      lines.dt["акциз"] = text;
    } else if (base > 0.9 * lim) {
      tip("lux_near", "внимание", `До порога акциза 10% осталось ${eur((lim - base) / C.EUR)} с учётом доставки: его превышение добавит 10% стоимости и НДС с этой суммы`);
    }

    // 4. ДТ или ПТД
    const ptdOk = !ptd.blocked;
    if (ptdOk && ptd["итого_обязательные"] < dt["итого_обязательные"]) {
      const d = dt["итого_обязательные"] - ptd["итого_обязательные"];
      routes.dt = `По ПТД дешевле на ${money(d)}`;
      routes.ptd = `Дешевле ДТ на ${money(d)}: доставка в базу не входит`;
      tip("ptd", "сейчас", `Физлицу — оформить по ПТД: дешевле ДТ на ${money(d)} (одна машина для себя, один СБКТС в год)`, d);
    } else if (ptdOk) {
      routes.ptd = `Дороже ДТ на ${money(ptd["итого_обязательные"] - dt["итого_обязательные"])}`;
      const be = breakeven(run, ptd["итого_обязательные"]);
      if (be !== null && be > deliv_eur) routes.dt = `ПТД станет выгоднее при доставке больше ${eur(be)}`;
    } else if (age > 5) {
      routes.ptd = "Старше 5 лет: ЭПТС по ПТД не оформят — только ДТ";
    }

    // 4а. ПТД и дни рождения машины
    if (age <= 5) {
      if (age < 3) {
        const by = year + 3, bm = month;
        const later = run("ПТД", "третьи", { age: 3, age_reg: by - year });
        lines.ptd["ЕТП_СТП"] = `С ${pad(bm)}.${by} машине 3 года: единая ставка ${tg(later["ЕТП_СТП"])} вместо ${tg(ptd["ЕТП_СТП"])}`;
        if (later["итого_обязательные"] < best && (by > today_year || (by === today_year && bm > today_month)))
          tip("ptd_wait", "сейчас", `Подождать до ${pad(bm)}.${by} и оформить по ПТД: всего ${money(later["итого_обязательные"])} вместо ${money(best)} сейчас (вместе со сбором за регистрацию)`, best - later["итого_обязательные"]);
      } else {
        lines.ptd["ЕТП_СТП"] = `ПТД — пока машине не больше 5 полных лет, до ${pad(month)}.${year + 6}: потом ЭПТС по ПТД не оформят`;
        tip("ptd_deadline", "внимание", `ПТД доступен до ${pad(month)}.${year + 6}, пока машине не больше 5 полных лет: потом ЭПТС по ПТД не оформят`);
      }
    }

    // 5. Доставка
    if (deliv_eur > 0) {
      const d = dt["итого_обязательные"] - run("ДТ", "третьи", { deliv: 0 })["итого_обязательные"];
      if (d > 0) {
        lines.dt["НДС"] = `Из них ${money(d)} — с доставки: участок по ЕАЭС выделите в счёте отдельно, он в базу не входит`;
        tip("delivery", "сейчас", `Разделить счёт за доставку: до границы ЕАЭС и дальше. Доставка добавляет к платежам по ДТ ${money(d)}, участок по ЕАЭС в базу не входит`, 0);
      }
    }

    // 6. Гибрид
    if (fuel === "гибрид_двс") {
      const d = dt["итого_обязательные"] - run("ДТ", "третьи", { fuel: "гибрид_эл" })["итого_обязательные"];
      if (d > 0) {
        const text = `Если у гибрида мощнее электромотор, пошлина по ВТО 0%: дешевле на ${money(d)}`;
        tip("hybrid", "выбор", text, d);
        lines.dt["пошлина"] = text;
      }
    }

    // 7. НДС для бизнеса
    if (dt["НДС"] > 0) {
      if (!("НДС" in lines.dt)) lines.dt["НДС"] = `Юрлицу — плательщику НДС эти ${tg(dt["НДС"])} вернутся зачётом`;
      lines.kg_ul["НДС"] = `Плательщику НДС эти ${tg(rows.kg_ul["НДС"])} вернутся зачётом`;
    }

    // 8. Кыргызстан, Россия
    for (const id of ["kg_ul", "kg_fl"]) {
      const d = rows[id]["итого_обязательные"] - dt["итого_обязательные"];
      routes[id] = `Регистрация в РК не подтверждена; по платежам ${d > 0 ? "дороже" : "дешевле"} ДТ на ${money(d)}`;
    }
    lines.kg_fl["за_рубежом"] = "Пошлина по ЕТТ, без казахстанских ставок ВТО, и НДС Кыргызстана 12%";
    lines.kg_ul["за_рубежом"] = "Пошлина по ЕТТ, без казахстанских ставок ВТО; НДС Кыргызстана продавец возвращает";
    for (const id of ["ru_ul", "ru_fl"]) {
      const d = rows[id]["итого_обязательные"] - best;
      routes[id] = `${d > 0 ? "Выше" : "Ниже"} лучшего маршрута на ${money(d)}: утильсбор ×2 (цена — рынка РФ/РБ)`;
    }

    // 9. Рост МРП с 1 января
    if (today_month >= 9 && C.MRP_YEAR === today_year && MRP_NEXT_YEAR === today_year + 1) {
      const r = rows[bestId];
      const part = r["утильсбор"] + r["сбор_первичная_регистрация"] + r["СРТС_и_номера"] + r["таможенный_сбор"];
      const d = part * (MRP_NEXT / C.MRP - 1);
      if (d > 0) tip("mrp_next", "сейчас", `До конца года: с 1 января МРП по проекту бюджета ${num(MRP_NEXT)} тг — утильсбор и сборы для этой машины вырастут на ${money(d)}`, d);
    }

    general.sort((p, q) => q.saving - p.saving || (p.id < q.id ? -1 : p.id > q.id ? 1 : 0));
    return { general, routes, lines, best: bestId };
  }

  function breakeven(run, ptdTotal) {
    let lo = 0, hi = 100000;
    if (run("ДТ", "третьи", { deliv: hi })["итого_обязательные"] < ptdTotal) return null;
    for (let i = 0; i < 40; i++) {
      const mid = (lo + hi) / 2;
      if (run("ДТ", "третьи", { deliv: mid })["итого_обязательные"] < ptdTotal) lo = mid; else hi = mid;
    }
    return Math.round(lo / 10) * 10;
  }

  const api = { forCar };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KZTips = api;
})(typeof window !== "undefined" ? window : globalThis);
