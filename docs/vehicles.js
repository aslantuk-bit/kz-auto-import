/* Грузовики, тягачи, спецмашины, мотоциклы и самоходная техника — перенос vehicles.py.
   Константы (МРП, курс, НДС, сбор) — из data.json; сверка с Python: node web/parity_test.mjs */
(function (root) {
  "use strict";
  const HP_PER_KW = 1.35962;
  const KINDS = {
    truck_diesel: ["Грузовик, дизель (8704 21–23)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    truck_petrol: ["Грузовик, бензин (8704 31–32)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    truck_ev: ["Электрогрузовик (8704 60)", "Грузовики и спецмашины", "МВД", ["mass", "payload"]],
    dumper: ["Карьерный самосвал (8704 10)", "Грузовики и спецмашины", "МВД", ["mass", "payload"]],
    tractor_unit: ["Седельный тягач (8701 21–29)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "eco4"]],
    crane: ["Автокран (8705 10)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    drill: ["Буровая установка на шасси (8705 20)", "Грузовики и спецмашины", "МВД", ["mass", "payload"]],
    fire: ["Пожарная машина (8705 30)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    mixer: ["Бетономешалка (8705 40)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    pump: ["Бетононасос (8705 90)", "Грузовики и спецмашины", "МВД", ["mass", "payload"]],
    tow: ["Эвакуатор, аварийная машина (8705 90)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    special_other: ["Прочая спецмашина на шасси (8705 90)", "Грузовики и спецмашины", "МВД", ["mass", "cc", "payload"]],
    moto: ["Мотоцикл (8711)", "Мотоциклы", "МВД", ["cc", "kw", "electric"]],
    farm_tractor: ["Трактор колёсный (8701 91–95)", "Самоходная техника", "МИО", ["kw"]],
    crawler: ["Трактор гусеничный (8701 30)", "Самоходная техника", "МИО", ["kw"]],
    combine: ["Комбайн зерноуборочный (8433 51)", "Самоходная техника", "МИО", ["kw"]],
    forklift: ["Вилочный погрузчик с ДВС (8427 20)", "Самоходная техника", "МИО", ["kw"]],
    forklift_el: ["Электропогрузчик (8427 10)", "Самоходная техника", "МИО", ["kw"]],
    loader: ["Фронтальный погрузчик (8429 51)", "Самоходная техника", "МИО", ["kw"]],
    excavator: ["Экскаватор полноповоротный (8429 52)", "Самоходная техника", "МИО", ["kw"]],
    bulldozer: ["Бульдозер (8429 11/19)", "Самоходная техника", "МИО", ["kw"]],
    grader: ["Грейдер (8429 20)", "Самоходная техника", "МИО", ["kw"]],
    roller: ["Каток дорожный (8429 40)", "Самоходная техника", "МИО", ["kw"]],
  };
  const SELF = new Set(Object.keys(KINDS).filter((k) => KINDS[k][1] === "Самоходная техника"));
  const VAT_OFFSET = new Set(["forklift", "forklift_el", "loader", "excavator", "bulldozer", "grader", "roller"]);
  const SPEC_8705 = { crane: [0.10, 0.28, 0.08], drill: [0.075, null, null], fire: [0.05, 0.6, "used5"],
    mixer: [0.15, 0.5, 0.10], pump: [0.10, null, 0.05], tow: [0.13, 0.6, 0.05], special_other: [0.05, 0.04, "used5"] };
  const FLAT = { crawler: [0.075, 0.0], combine: [0.05, null], forklift: [0.05, null], forklift_el: [0.0, null],
    loader: [0.05, 0.0], excavator: [0.05, 0.0], bulldozer: [0.05, 0.0], grader: [0.03, 0.0], roller: [0.05, 0.0], dumper: [0.05, 0.0] };
  const ROUTES = [["dt", "ДТ", "третьи"], ["ptd", "ПТД", "третьи"], ["ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ"], ["ru_fl", "ЕАЭС_ФЛ", "РФ_РБ"]];
  const MARKET = { "брокер": 100000, "СВХ": 45000, "СВХ_техника": 60000, "СВХ_мото": 30000, "СБКТС": 250000,
    "СБКТС_мото": 120000, "ЭПТС": 30000, "сертификат": 300000 };
  const OGPO = { N1: 2.09, N: 3.98, moto: 1.0 };
  const r0 = (x) => Math.floor(x + 0.5);

  function make(K) {
    const EUR = K.EUR, MRP = K.MRP;
    const regAge = (m) => (m.age_reg == null ? m.age : m.age_reg);
    const ptdAllowed = (m) => m.kind === "moto" || ((m.kind === "truck_diesel" || m.kind === "truck_petrol") && m.mass <= 5);

    function dutyEtt(m, base) {
      const k = m.kind, a = m.age, cc = m.cc, spec = (e) => e * cc * EUR;
      if (k === "truck_diesel") {
        if (a >= 7) return spec(1.0);
        if (m.mass <= 5) return a >= 5 && a < 7 && cc <= 2500 ? Math.max(0.10 * base, spec(0.13)) : 0.10 * base;
        if (m.mass <= 20) { if (a < 3) return 0.15 * base; return a >= 5 ? Math.max(0.10 * base, spec(0.18)) : 0.10 * base; }
        return a < 3 ? 0.05 * base : 0.10 * base;
      }
      if (k === "truck_petrol") { if (a >= 7) return spec(1.0); if (m.mass <= 5 && a < 3 && cc > 2800) return 0.125 * base; return 0.15 * base; }
      if (k === "truck_ev") return 0.15 * base;
      if (k === "tractor_unit") { if (a >= 7) return spec(1.0); return a < 3 ? (m.eco4 ? 0.05 : 0.10) * base : 0.10 * base; }
      if (k in SPEC_8705) { const [rate, mn] = SPEC_8705[k]; return a >= 3 && mn ? Math.max(rate * base, spec(mn)) : rate * base; }
      if (k === "moto") { if (m.electric || cc <= 250) return 0.14 * base; return cc <= 800 ? 0.15 * base : 0.10 * base; }
      if (k === "farm_tractor") return m.kw <= 18 ? (a < 3 ? 0.05 : 0.10) * base : 0.10 * base;
      return FLAT[k][0] * base;
    }

    function dutyWto(m, base) {
      const k = m.kind, a = m.age;
      if (k === "truck_diesel") {
        if (m.mass <= 5) return a >= 7 || (a >= 5 && a < 7 && m.cc <= 2500) ? 0.10 * base : null;
        if (m.mass <= 20) return a < 3 || a >= 5 ? 0.10 * base : null;
        return a >= 7 ? 0.10 * base : null;
      }
      if (k === "truck_petrol") {
        if (m.mass <= 5) return a >= 7 && m.cc <= 2800 ? 0.15 * base : 0.10 * base;
        return a < 3 ? 0.10 * base : a >= 7 ? 0.15 * base : null;
      }
      if (k === "tractor_unit") return a >= 7 ? 0.10 * base : null;
      if (k in SPEC_8705) { const w = SPEC_8705[k][2]; if (w === "used5") return a >= 3 ? 0.05 * base : null; return w == null ? null : w * base; }
      if (k === "farm_tractor") return m.kw > 75 && a < 3 ? 0.05 * base : 0.0;
      if (k in FLAT) return FLAT[k][1] == null ? null : FLAT[k][1] * base;
      return null;
    }

    const band = (v, bands) => { for (const [top, val] of bands) if (top === null || v <= top) return val; return bands[bands.length - 1][1]; };

    function utilCoef(m) {
      const ru = m.origin === "РФ_РБ";
      if (m.kind === "moto" || VAT_OFFSET.has(m.kind) || m.kind === "crawler") return 0.0;
      if (m.kind === "farm_tractor" || m.kind === "combine") {
        if (ru) return 250.0;
        const hp = m.kw * HP_PER_KW;
        return band(hp, m.kind === "farm_tractor" ? [[60, 2], [130, 5.5], [220, 17], [340, 29], [380, 29], [null, 40]]
          : [[160, 9], [220, 23], [255, 32], [325, 38], [400, 38], [null, 45]]);
      }
      if (m.kind === "truck_ev") return ru ? 60.0 : 0.0;
      if (m.mass > 50) return 0.0;
      if (m.kind === "tractor_unit" && m.mass >= 12) return ru ? 164.0 : 11.0;
      if (ru) return 164.0;
      return band(m.mass, [[2.5, 3.5], [3.5, 7.5], [5, 7.5], [8, 8], [12, 9.5], [20, 10.5], [50, 20.5]]);
    }

    function regFee(m) {
      if (SELF.has(m.kind) || m.kind === "moto") return 0.25 * MRP;
      const a = regAge(m);
      if (a < 2) return 0.25 * MRP;
      if (a < 3) return 240 * MRP;
      if (m.kind === "tractor_unit") return (a < 7 ? 350 : 2500) * MRP;
      return (a < 5 ? 350 : 2500) * MRP;
    }
    const docsFee = (m) => (SELF.has(m.kind) ? 1.5 * MRP : (1.25 + (m.kind === "moto" ? 1.4 : 2.8)) * MRP);
    function transportTax(m) {
      if (SELF.has(m.kind)) return 3 * MRP;
      if (m.kind === "moto") return (m.kw <= 55 ? 1 : 10) * MRP;
      if (m.kind === "dumper" && m.mass >= 40) return 0;
      return band(m.payload, [[1, 3], [1.5, 5], [5, 7], [null, 9]]) * MRP;
    }
    function market(m) {
      if (SELF.has(m.kind)) return MARKET["брокер"] + MARKET["СВХ_техника"] + MARKET["сертификат"];
      if (m.kind === "moto") return MARKET["брокер"] + MARKET["СВХ_мото"] + MARKET["СБКТС_мото"] + MARKET["ЭПТС"] + 1.9 * MRP * OGPO.moto;
      const ogpo = 1.9 * MRP * (m.mass <= 3.5 ? OGPO.N1 : OGPO.N);
      return MARKET["брокер"] + MARKET["СВХ"] + MARKET["СБКТС"] + MARKET["ЭПТС"] + ogpo;
    }

    function calcMachine(m) {
      const v = m.price_eur * EUR, third = m.origin === "третьи";
      const deliv = third ? m.delivery_eur * EUR : 0, base = v + (m.mode === "ДТ" ? deliv : 0);
      const r = { "пошлина": 0, "ставка_пошлины": "—", "ЕТП_СТП": 0, "таможенный_сбор": 0, "акциз": 0, "НДС": 0 };
      const flags = [];
      if (m.mode === "ДТ") {
        const ett = dutyEtt(m, base), wto = dutyWto(m, base);
        if (wto !== null && wto <= ett) { r["пошлина"] = wto; r["ставка_пошлины"] = "ВТО (Решение № 59)"; flags.push("условный выпуск: обращение только в РК"); }
        else { r["пошлина"] = ett; r["ставка_пошлины"] = "ЕТТ (Решение № 80)"; }
        r["таможенный_сбор"] = K.CUSTOMS_FEE_MRP * MRP;
        r["НДС"] = K.VAT * (base + r["пошлина"]);
        if (VAT_OFFSET.has(m.kind)) flags.push("НДС можно уплатить методом зачёта — фактически 0, если держать технику 5 лет (ПП № 1199)");
      } else if (m.mode === "ПТД") {
        const duty = dutyEtt(m, v);
        r["ЕТП_СТП"] = duty + K.VAT * (v + duty);
        r["ставка_пошлины"] = "СТП (ЕТТ + НДС)";
        if (!ptdAllowed(m)) flags.push("ПТД нельзя: не товар для личного пользования (Решение № 107, прил. 6) — регистрация невозможна");
      } else if (m.mode === "ЕАЭС_ЮЛ") {
        r["НДС"] = K.VAT * v;
      }
      if (m.origin === "РФ_РБ" && utilCoef(m) > 0) flags.push("утильсбор по коэффициенту 2 для ввоза из России и Беларуси");
      r["утильсбор"] = 50 * MRP * utilCoef(m);
      r["сбор_первичная_регистрация"] = regFee(m);
      r["СРТС_и_номера"] = docsFee(m);
      r["итого_обязательные"] = r["пошлина"] + r["ЕТП_СТП"] + r["таможенный_сбор"] + r["НДС"] + r["утильсбор"] + r["сбор_первичная_регистрация"] + r["СРТС_и_номера"];
      r["рыночные_оценка"] = third ? market(m) : SELF.has(m.kind) ? 0 : 1.9 * MRP * OGPO.N;
      r["доставка_кзт"] = deliv;
      r["итого_с_рыночными"] = r["итого_обязательные"] + r["рыночные_оценка"] + deliv;
      r["стоимость_кзт"] = v;
      r["таможенная_стоимость_кзт"] = m.mode === "ДТ" ? base : m.mode === "ПТД" ? v : 0;
      r["налог_на_транспорт_год"] = transportTax(m);
      r["регистрирует"] = SELF.has(m.kind) ? "МИО (гостехинспекция)" : "МВД (спецЦОН)";
      if (m.kind === "tractor_unit" && regAge(m) < 7) flags.push("международному перевозчику тягач до 7 лет регистрируется без сбора до 01.01.2028 (НК ст. 830)");
      if (SELF.has(m.kind)) flags.push("ОГПО для машин, которые регистрирует МИО, не требуется");
      r["примечания"] = flags.join("; ");
      for (const k in r) if (typeof r[k] === "number") r[k] = r0(r[k]);
      return r;
    }
    const routesFor = (m) => ROUTES.filter(([, mode]) => mode !== "ПТД" || ptdAllowed(m));
    const TRUCKS = new Set(Object.keys(KINDS).filter((k) => KINDS[k][1] === "Грузовики и спецмашины"));
    const money = (x) => { x = Math.abs(x); if (x < 1e6) return String(r0(x)).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " тг"; const t = r0(x / 1e5); return `${Math.floor(t / 10)},${t % 10} млн тг`; };

    function tips(m, todayYear) {   // перенос vehicles.tips
      const out = [], dt = calcMachine({ ...m, mode: "ДТ", origin: "третьи" });
      const now = regFee(m), nxt = regFee({ ...m, age_reg: regAge(m) + 1 });
      if (nxt > now) out.push({ id: "reg_year_end", saving: r0(nxt - now), text: `Зарегистрируйте до 31.12.${todayYear}: с 1 января сбор за регистрацию станет ${money(nxt)} (+${money(nxt - now)})` });
      if (TRUCKS.has(m.kind) && now >= 2500 * MRP) {
        const lim = m.kind === "tractor_unit" ? 7 : 5;
        out.push({ id: "reg_younger", saving: r0(now - 350 * MRP), text: `Сбор 2 500 МРП — у машин ${lim} лет и старше по году выпуска; машина моложе платит 350 МРП: дешевле на ${money(now - 350 * MRP)}` });
      }
      if (ptdAllowed(m)) {
        const ptd = calcMachine({ ...m, mode: "ПТД", origin: "третьи" });
        if (ptd["итого_обязательные"] < dt["итого_обязательные"]) { const d = dt["итого_обязательные"] - ptd["итого_обязательные"]; out.push({ id: "ptd", saving: d, text: `Физлицу — оформить по ПТД: дешевле ДТ на ${money(d)}` }); }
      }
      if (VAT_OFFSET.has(m.kind) && dt["НДС"] > 0) out.push({ id: "vat_offset", saving: dt["НДС"], text: `НДС ${money(dt["НДС"])} можно уплатить методом зачёта (ПП № 1199): фактически 0, если технику не продавать и не вывозить 5 лет` });
      if (utilCoef({ ...m, origin: "РФ_РБ" }) > 0) {
        const ru = calcMachine({ ...m, mode: "ЕАЭС_ФЛ", origin: "РФ_РБ" }), d = ru["утильсбор"] - dt["утильсбор"];
        if (d > 0) out.push({ id: "ru", saving: 0, text: `Не везите с рынка России и Беларуси: утильсбор там по коэффициенту 2 — больше на ${money(d)}` });
      }
      if (dt["ставка_пошлины"].startsWith("ВТО")) out.push({ id: "wto", saving: 0, text: "Пошлина по ставке РК по ВТО ниже ЕТТ, но выпуск условный: продать технику за пределы РК можно только с доплатой до ЕТТ" });
      out.sort((p, q) => q.saving - p.saving || (p.id < q.id ? -1 : p.id > q.id ? 1 : 0));
      return out;
    }
    return { calcMachine, routesFor, ptdAllowed, tips };
  }

  const api = { make, KINDS, ROUTES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KZVehicles = api;
})(typeof window !== "undefined" ? window : globalThis);
