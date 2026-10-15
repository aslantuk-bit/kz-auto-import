/* Калькулятор платежей при ввозе легкового автомобиля в РК — перенос calc.py.
   Константы приходят из data.json (их источник — calc.py), здесь только логика.
   Сверка с Python на всех сценариях: node web/parity_test.mjs */
(function (root) {
  "use strict";

  function make(K) {
    const band = (v, edges) => { for (let i = 0; i < edges.length; i++) if (v <= edges[i]) return i; return edges.length; };
    const isEl = (t) => t === "гибрид_эл" || t === "электро";

    function dutyEtt(c) {
      const v = c.price_eur * K.EUR;
      if (isEl(c.fuel)) return 0.15 * v;
      const ice = c.fuel === "дизель" ? "дизель" : "бензин";
      if (c.age < 3) return ice === "бензин" && c.cc > 2800 ? 0.125 * v : 0.15 * v;
      let mn, over7;
      if (ice === "бензин") { const b = band(c.cc, K.ETT_PETROL_EDGES); mn = K.ETT_PETROL_MIN_3_7[b]; over7 = K.ETT_PETROL_OVER7[b]; }
      else { const b = band(c.cc, K.ETT_DIESEL_EDGES); mn = K.ETT_DIESEL_MIN_3_7[b]; over7 = K.ETT_DIESEL_OVER7[b]; }
      if (c.age <= 7) return Math.max(0.20 * v, mn * c.cc * K.EUR);
      return over7 * c.cc * K.EUR;
    }

    function dutyWto(c) {   // null — позиции нет в перечне ВТО, применяется ЕТТ
      const v = c.price_eur * K.EUR;
      if (isEl(c.fuel)) return 0;
      if (c.age < 3) return null;
      if (c.age <= 7) return 0.15 * v;
      if ((c.fuel === "бензин" || c.fuel === "гибрид_двс") && c.cc > 1500 && c.cc <= 3000)
        return Math.min(Math.max(0.5 * c.cc * K.EUR, 0.15 * v), 0.18 * v);
      return Math.max(0.15 * v, 0.6 * c.cc * K.EUR);
    }

    function etp(c) {
      if (c.fuel === "электро") { const duty = 0.15 * c.price_eur * K.EUR; return duty + K.VAT * (c.price_eur * K.EUR + duty); }
      if (c.age < 3) {
        for (const [limit, pct, mn] of K.PTD_NEW)
          if (limit === null || c.price_eur <= limit) return Math.max(pct * c.price_eur, mn * c.cc) * K.EUR;
      }
      const b = band(c.cc, K.PTD_EDGES);
      return (c.age <= 5 ? K.PTD_3_5[b] : K.PTD_OVER5[b]) * c.cc * K.EUR;
    }

    function util(c) {
      if (c.fuel === "электро") return 50 * K.MRP * K.UTIL_EV[c.origin];
      const k = c.origin === "третьи" ? K.UTIL_K1 : K.UTIL_K2;
      return 50 * K.MRP * k[band(c.cc, K.UTIL_EDGES)];
    }

    const regAge = (c) => (c.age_reg == null ? c.age : c.age_reg);

    function regFee(c) {   // НК ст. 615 п. 3; происхождение не влияет
      const ev = c.fuel === "электро", a = regAge(c);
      if (a < 2) return 0.25 * K.MRP;
      if (a < 3) return (ev ? 25 : 50) * K.MRP;
      return (ev ? 250 : 500) * K.MRP;
    }

    function transportTax(c) {   // НК ст. 565, легковые
      if (c.fuel === "электро") return 0;
      const steps = [[1100, 1, null], [1500, 2, null], [2000, 3, 1500], [2500, 6, 2000],
                     [3000, 9, 2500], [4000, 15, 3000], [Infinity, 117, 4000]];
      let tax = 0;
      for (const [top, mrp, base] of steps) if (c.cc <= top) { tax = mrp * K.MRP + (base ? 7 * (c.cc - base) : 0); break; }
      const a = regAge(c);
      if (a > 20) tax *= 0.5; else if (a > 10) tax *= 0.7;
      return tax;
    }

    function calc(c) {
      const v = c.price_eur * K.EUR;
      const r = { duty: 0, duty_basis: "—", etp: 0, customs_fee: 0, excise_cc: 0, excise_lux: 0, vat: 0 };
      const exciseCc = c.fuel !== "электро" && c.cc > 3000 ? 100 * c.cc : 0;
      const lux = v >= K.LUX_THRESHOLD ? Math.max(0.10 * v - exciseCc, 0) : 0;
      if (c.mode === "ДТ") {
        const ett = dutyEtt(c), wto = dutyWto(c);
        if (wto !== null && wto <= ett) { r.duty = wto; r.duty_basis = "ВТО (Решение № 59)"; }
        else { r.duty = ett; r.duty_basis = "ЕТТ (Решение № 80)"; }
        r.customs_fee = K.CUSTOMS_FEE_MRP * K.MRP;
        r.excise_cc = exciseCc; r.excise_lux = lux;
        r.vat = K.VAT * (v + r.duty + exciseCc + lux);
      } else if (c.mode === "ПТД") {
        r.etp = etp(c);
        r.duty_basis = c.fuel === "электро" ? "СТП (ЕТТ + НДС)" : "ЕТП (Решение № 107)";
        r.excise_lux = lux;
      } else if (c.mode === "ЕАЭС_ЮЛ") {
        r.excise_cc = exciseCc; r.excise_lux = lux; r.vat = K.VAT * (v + exciseCc + lux);
      } else if (c.mode === "ЕАЭС_ФЛ") {
        r.excise_lux = lux;
      } else throw new Error("режим " + c.mode);
      r.util = util(c);
      r.reg_fee = regFee(c);
      r.docs = (1.25 + 2.8) * K.MRP;
      r.excise = r.excise_cc + r.excise_lux;
      r.total = r.duty + r.etp + r.customs_fee + r.excise_cc + r.excise_lux + r.vat + r.util + r.reg_fee + r.docs;
      let market = K.MARKET["ОГПО_год"] + (c.mode === "ДТ" || c.mode === "ПТД" ? K.MARKET["брокер"] + K.MARKET["СВХ"] : 0);
      if (c.mode === "ДТ" || c.mode === "ПТД") market += K.MARKET["СБКТС"] + (c.mode === "ПТД" ? K.MARKET["ЭПТС"] : 0);
      r.market = market;
      r.total_market = r.total + market;
      r.value_kzt = v;
      r.share_pct = 100 * r.total / v;
      r.tax_year = transportTax(c);
      const flags = [];
      if (c.mode === "ПТД" && c.age > 5) flags.push("ЭПТС по ПТД только до 5 лет (приказ МПС № 474, с 26.09.2026, по СМИ) — регистрация невозможна");
      if (r.duty_basis.startsWith("ВТО")) flags.push("условный выпуск: обращение только в РК");
      if (c.mode.startsWith("ЕАЭС") && c.fuel === "электро" && c.origin === "третьи")
        flags.push("электромобиль, ввезённый в КГ/АМ по льготе ЕАЭС, нельзя передавать резидентам РК (Решение Совета ЕЭК № 111); расчёт верен только для машины, растаможенной там по ЕТТ");
      if (c.mode === "ПТД" && lux) flags.push("акциз 10% при ПТД — спорно");
      r.flags = flags;
      r.blocked = flags.some((f) => /регистрация невозможна|нельзя передавать/.test(f));
      return r;
    }

    return { calc, dutyEtt, dutyWto, etp, util, regFee, transportTax };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { make };
  else root.KZCalc = { make };
})(typeof window !== "undefined" ? window : globalThis);
