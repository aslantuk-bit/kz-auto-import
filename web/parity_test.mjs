// Сверка docs/calc.js с Python (out/сценарии.csv) на всех сценариях, допуск 1 тг на округление.
// Запуск: node web/parity_test.mjs
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const root = new URL("..", import.meta.url).pathname;
const { make } = require(root + "docs/calc.js");
const data = JSON.parse(readFileSync(root + "docs/data.json", "utf8"));
const K = make(data.constants);

const lines = readFileSync(root + "out/сценарии.csv", "utf8").replace(/^﻿/, "").trim().split("\n");
const parse = (line) => {            // CSV без кавычек внутри полей, кроме «примечаний»
  const out = []; let cur = "", q = false;
  for (const ch of line) {
    if (ch === '"') q = !q; else if (ch === "," && !q) { out.push(cur); cur = ""; } else cur += ch;
  }
  out.push(cur); return out;
};
const head = parse(lines[0]);
const col = (name) => head.indexOf(name);
const FIELDS = { пошлина: "duty", ЕТП_СТП: "etp", таможенный_сбор: "customs_fee", акциз_объём: "excise_cc",
  акциз_10pct: "excise_lux", НДС: "vat", утильсбор: "util", сбор_первичная_регистрация: "reg_fee",
  СРТС_и_номера: "docs", итого_обязательные: "total", рыночные_оценка: "market", налог_на_транспорт_год: "tax_year",
  доставка_кзт: "delivery", итого_с_рыночными: "total_market", таможенная_стоимость_кзт: "customs_value",
  пошлина_там: "duty_abroad", НДС_там: "vat_abroad", сборы_там: "fees_abroad", за_рубежом: "abroad" };

let bad = 0;
for (const line of lines.slice(1)) {
  const r = parse(line);
  const c = { price_eur: +r[col("стоимость_eur")], fuel: r[col("тип")], cc: +r[col("объём")], age: +r[col("возраст")],
    mode: r[col("режим")], origin: r[col("происхождение")], age_reg: null, delivery_eur: +r[col("доставка_eur")] };
  const js = K.calc(c);
  for (const [py, key] of Object.entries(FIELDS)) {
    if (Math.abs(+r[col(py)] - js[key]) > 1) {
      if (bad++ < 10) console.log("расхождение", JSON.stringify(c), py, r[col(py)], js[key]);
    }
  }
  if ((r[col("ставка_пошлины")] || "—") !== js.duty_basis && bad++ < 10) console.log("основание", JSON.stringify(c));
}
console.log(`${lines.length - 1} сценариев, расхождений: ${bad}`);
process.exit(bad ? 1 : 0);
