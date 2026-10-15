/* Ввоз авто в Казахстан — веб-версия. Данные: data.json, расчёт: calc.js (перенос calc.py). */
(async function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n == null || isNaN(n) ? "—" : Math.round(n).toLocaleString("ru-RU"));
  const mln = (n) => (n / 1e6).toFixed(1).replace(".", ",") + " млн";
  const pct = (n, d = 0) => n.toFixed(d).replace(".", ",") + "%";
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const data = await (await fetch("data.json?v=1.1.1")).json();
  const K = KZCalc.make(data.constants);
  const C = data.constants;
  const TODAY = { y: 2026, m: 10 };

  const COMPONENTS = [
    ["duty", "Пошлина", "ЕТТ ЕАЭС (Решение № 80) или ставки РК по ВТО (Решение № 59)", "--s1"],
    ["etp", "Единая ставка физлица", "Решение Совета ЕЭК № 107, прил. 2, табл. 2", "--s2"],
    ["customs_fee", "Таможенный сбор", "ПП РК № 171: 6 МРП за декларацию", "--s3"],
    ["excise", "Акциз", "НК ст. 537: 100 тг/см³ свыше 3 000 см³; 10% от 18 000 МРП", "--s4"],
    ["vat", "НДС 16%", "НК ст. 503 (третьи страны — ст. 466, ЕАЭС — ст. 518)", "--s5"],
    ["util", "Утильсбор", "Приказ МЭПР № 54 от 20.03.2026, прил. 4", "--s6"],
    ["reg_fee", "Сбор за регистрацию", "НК ст. 615 п. 3", "--s7"],
    ["docs", "Техпаспорт и номера", "НК ст. 667: 1,25 + 2,8 МРП", "--s8"],
  ];
  const ROUTES = [
    ["dt", "ДТ", "третьи", "Третьи страны · ДТ", "Юрлицо или физлицо, декларация на товары", "--s1"],
    ["ptd", "ПТД", "третьи", "Третьи страны · ПТД", "Физлицо, личное пользование, единая ставка", "--s2"],
    ["kg_ul", "ЕАЭС_ЮЛ", "третьи", "Кыргызстан/Армения · ЮЛ", "НДС и акциз через налоговую (ФНО 328.00)", "--s3"],
    ["kg_fl", "ЕАЭС_ФЛ", "третьи", "Кыргызстан/Армения · ФЛ", "Физлицо не для бизнеса: НДС не взимается", "--s4"],
    ["ru_ul", "ЕАЭС_ЮЛ", "РФ_РБ", "Россия/Беларусь · ЮЛ", "Утильсбор по коэффициенту 2", "--s5"],
    ["ru_fl", "ЕАЭС_ФЛ", "РФ_РБ", "Россия/Беларусь · ФЛ", "Утильсбор по коэффициенту 2", "--s6"],
  ].map(([id, mode, origin, label, who, color]) => ({ id, mode, origin, label, who, color }));
  const isRu = (r) => r.origin === "РФ_РБ";
  const FUEL = { "бензин": "Бензин", "дизель": "Дизель", "гибрид_двс": "Гибрид (мощнее ДВС)", "гибрид_эл": "Гибрид (мощнее электромотор)", "электро": "Электромобиль" };
  const engineLabel = (f, cc) => FUEL[f] + (f === "электро" ? "" : " " + (cc / 1000).toFixed(1).replace(".", ",") + " л");

  /* ---------- подсказка ---------- */
  const tip = $("#tip");
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest?.("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.innerHTML = t.getAttribute("data-tip");
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - w - 8) + "px";
    tip.style.top = (e.clientY + 16 + h > innerHeight ? e.clientY - h - 10 : e.clientY + 16) + "px";
  });
  const tipHtml = (title, lines) => `<div class="t">${esc(title)}</div>` + lines.map((l) => `<div>${l}</div>`).join("");

  /* ---------- графики ---------- */
  const ctx = document.createElement("canvas").getContext("2d");
  const textW = (s, size = 12) => { ctx.font = `${size}px ${getComputedStyle(document.body).fontFamily}`; return ctx.measureText(s).width; };
  const niceTicks = (max, n = 5) => {
    const raw = max / n, mag = 10 ** Math.floor(Math.log10(raw || 1)), step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const out = []; for (let v = 0; ; v += step) { out.push(+v.toFixed(6)); if (v >= max - 1e-9) break; } return out;
  };
  const tickLbl = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1).replace(".", ","));

  function stackedBars(el, rows, legendEl, unit = "млн тг") {
    const W = Math.max(el.clientWidth, 280), compact = W < 560, barH = 20, top = 4, axisH = 30;
    const rowH = compact ? 50 : 36;   // на узком экране подпись над баром
    const labW = compact ? 0 : Math.min(Math.max(...rows.map((r) => textW(r.label))) + 12, W * 0.42);
    const endW = Math.max(...rows.map((r) => textW(mln(r.total) + " тг"))) + 22;
    const plotW = W - labW - endW;
    const maxM = Math.max(...rows.map((r) => r.total)) / 1e6 || 1;
    const ticks = niceTicks(maxM), xmax = ticks[ticks.length - 1];
    const x = (m) => labW + (m / xmax) * plotW;
    const H = top + rows.length * rowH + axisH;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    s += ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${top + rows.length * rowH}" stroke="var(--grid)"/><text x="${x(t)}" y="${H - 12}" text-anchor="middle">${tickLbl(t)}</text>`).join("");
    s += `<text x="${labW + plotW / 2}" y="${H}" text-anchor="middle" style="fill:var(--ink-3)">${unit}</text>`;
    rows.forEach((r, i) => {
      const y = top + i * rowH + (compact ? rowH - barH - 6 : (rowH - barH) / 2);
      let acc = 0;
      s += compact
        ? `<text x="0" y="${y - 6}" class="lbl-strong">${esc(r.label)}</text>`
        : `<text x="${labW - 10}" y="${y + barH / 2 + 4}" text-anchor="end" class="lbl-strong">${esc(r.label)}</text>`;
      const parts = r.parts.filter((p) => p.value > 0);
      parts.forEach((p, j) => {
        const x0 = x(acc / 1e6), x1 = x((acc + p.value) / 1e6);
        acc += p.value;
        const w = Math.max(x1 - x0 - (j < parts.length - 1 ? 2 : 0), 1);
        const rx = j === parts.length - 1 ? 4 : 0;
        s += `<rect class="bar" x="${x0}" y="${y}" width="${w}" height="${barH}" rx="${rx}" fill="var(${p.color})" data-tip="${esc(tipHtml(r.label, [`${esc(p.label)}: <b>${fmt(p.value)} тг</b>`]))}"/>`;
        if (rx && w > 8) s += `<rect x="${x0}" y="${y}" width="${Math.min(w, 6)}" height="${barH}" fill="var(${p.color})" pointer-events="none"/>`;
      });
      s += `<text x="${x(acc / 1e6) + 6}" y="${y + barH / 2 + 4}">${mln(r.total)} тг</text>`;
    });
    el.innerHTML = s + "</svg>";
    if (legendEl) {
      const used = new Set(rows.flatMap((r) => r.parts.filter((p) => p.value > 0).map((p) => p.label)));
      legendEl.innerHTML = rows[0].parts.filter((p) => used.has(p.label)).map((p) => `<span><i style="background:var(${p.color})"></i>${esc(p.label)}</span>`).join("");
    }
  }

  function lineChart(el, xs, series, { yFmt = tickLbl, yTitle = "", rule = null, tipFmt = (v) => v } = {}, legendEl) {
    const W = Math.max(el.clientWidth, 300), H = 260, top = 18, bottom = 34;
    const all = series.flatMap((s) => s.values);
    const ticks = niceTicks(Math.max(...all) || 1), ymax = ticks[ticks.length - 1];
    const left = Math.max(...ticks.map((t) => textW(yFmt(t)))) + 12, right = Math.max(10, textW(String(xs[xs.length - 1])) / 2 + 4);
    const pw = W - left - right, ph = H - top - bottom;
    const x = (i) => left + (xs.length === 1 ? pw / 2 : (i / (xs.length - 1)) * pw);
    const y = (v) => top + ph - (v / ymax) * ph;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    s += ticks.map((t) => `<line x1="${left}" x2="${W - right}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${left - 8}" y="${y(t) + 4}" text-anchor="end">${yFmt(t)}</text>`).join("");
    const every = Math.ceil((xs.length * Math.max(...xs.map((v) => textW(String(v)))) + xs.length * 10) / pw);
    s += xs.map((v, i) => (i % every ? "" : `<text x="${x(i)}" y="${H - bottom + 18}" text-anchor="middle">${esc(v)}</text>`)).join("");
    if (yTitle) s += `<text x="${left}" y="10" style="fill:var(--ink-3)">${esc(yTitle)}</text>`;
    if (rule) s += `<line x1="${x(rule.index)}" x2="${x(rule.index)}" y1="${top}" y2="${top + ph}" stroke="var(--ink-3)" stroke-dasharray="4 4"/><text x="${x(rule.index) + 5}" y="${top + 10}" style="fill:var(--ink-3)">${esc(rule.label)}</text>`;
    series.forEach((se) => {
      s += `<polyline fill="none" stroke="var(${se.color})" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${se.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}"/>`;
    });
    series.forEach((se) => {
      s += se.values.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="var(${se.color})" stroke="var(--panel)" stroke-width="1.5"/><circle cx="${x(i)}" cy="${y(v)}" r="11" fill="transparent" data-tip="${esc(tipHtml(se.name, [`${esc(xs[i])}: <b>${tipFmt(v)}</b>`]))}"/>`).join("");
    });
    el.innerHTML = s + "</svg>";
    if (legendEl) legendEl.innerHTML = series.map((se) => `<span><i style="background:var(${se.color})"></i>${esc(se.name)}</span>`).join("");
  }

  function groupedBars(el, cats, series, legendEl) {
    const W = Math.max(el.clientWidth, 300), barH = 13, gap = 3, groupH = series.length * (barH + gap) + 12, axisH = 30;
    const labW = Math.max(...cats.map((c) => textW(c))) + 12;
    const endW = textW("00,0 млн") + 22, pw = W - labW - endW;
    const max = Math.max(...series.flatMap((s) => s.values)) / 1e6;
    const ticks = niceTicks(max), xmax = ticks[ticks.length - 1];
    const x = (m) => labW + (m / xmax) * pw;
    const H = cats.length * groupH + axisH;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    s += ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="0" y2="${cats.length * groupH}" stroke="var(--grid)"/><text x="${x(t)}" y="${H - 12}" text-anchor="middle">${tickLbl(t)}</text>`).join("");
    s += `<text x="${labW + pw / 2}" y="${H}" text-anchor="middle" style="fill:var(--ink-3)">млн тг</text>`;
    cats.forEach((c, i) => {
      const y0 = i * groupH + 6;
      s += `<text x="${labW - 10}" y="${y0 + (series.length * (barH + gap)) / 2 + 3}" text-anchor="end" class="lbl-strong">${esc(c)}</text>`;
      series.forEach((se, j) => {
        const v = se.values[i], y = y0 + j * (barH + gap), w = Math.max(x(v / 1e6) - labW, v > 0 ? 2 : 0);
        s += `<rect x="${labW}" y="${y}" width="${w}" height="${barH}" rx="3" fill="var(${se.color})" data-tip="${esc(tipHtml(c, [`${esc(se.name)}: <b>${fmt(v)} тг</b>`]))}"/>`;
        s += `<text x="${labW + w + 5}" y="${y + barH - 2}">${mln(v)}</text>`;
      });
    });
    el.innerHTML = s + "</svg>";
    legendEl.innerHTML = series.map((se) => `<span><i style="background:var(${se.color})"></i>${esc(se.name)}</span>`).join("");
  }

  const partsOf = (r, withMarket = false) => {
    const p = COMPONENTS.map(([k, label, , color]) => ({ key: k, label, color, value: r[k] }));
    if (withMarket) p.push({ key: "market", label: "Рыночные расходы (оценка)", color: "--ink-3", value: r.market });
    return p;
  };

  /* ---------- вкладки ---------- */
  const tabs = [...document.querySelectorAll("nav.tabs button")];
  function showTab(name, push = true) {
    if (!tabs.some((b) => b.dataset.tab === name)) name = "calc";
    tabs.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll("main section").forEach((s) => (s.hidden = s.id !== name));
    if (push && location.hash.split("?")[0] !== "#" + name) history.replaceState(null, "", "#" + name);
    render[name]?.();
  }
  tabs.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  addEventListener("hashchange", () => showTab(location.hash.slice(1).split("?")[0] || "calc", false));

  /* ---------- калькулятор ---------- */
  const yearSel = $("#year"), monthSel = $("#month");
  for (let y = TODAY.y; y >= 1995; y--) yearSel.add(new Option(y, y));
  for (let m = 1; m <= 12; m++) monthSel.add(new Option(m, m));
  yearSel.value = 2022; monthSel.value = 6;
  let selectedRoute = null;

  // Ссылка на расчёт: #calc?p=15000&c=EUR&f=бензин&v=2000&y=2022&m=6&mk=1
  const [hashTab, hashQuery] = location.hash.slice(1).split("?");
  if (hashQuery) {
    const q = new URLSearchParams(hashQuery);
    const set = (id, v) => v != null && ($("#" + id).value = v);
    set("price", q.get("p")); set("cur", q.get("c")); set("fuel", q.get("f")); set("cc", q.get("v"));
    set("year", q.get("y")); set("month", q.get("m")); $("#market").checked = q.get("mk") === "1";
  }

  function readCar() {
    const price = Math.max(+$("#price").value || 0, 0), cur = $("#cur").value, fuel = $("#fuel").value;
    const ev = fuel === "электро";
    $("#cc").disabled = ev;
    const cc = ev ? 0 : Math.max(Math.round(+$("#cc").value || 0), 0);
    const y = +yearSel.value, m = +monthSel.value;
    const months = (TODAY.y - y) * 12 + (TODAY.m - m);
    return { priceEur: (price * data.fx[cur]) / data.fx.EUR, price, cur, fuel, cc, age: Math.max(Math.floor(months / 12), 0), ageReg: TODAY.y - y, y, m };
  }

  function renderCalc() {
    const car = readCar(), market = $("#market").checked, key = market ? "total_market" : "total";
    const rows = ROUTES.map((r) => ({ ...r, ...K.calc({ price_eur: car.priceEur, fuel: car.fuel, cc: car.cc, age: car.age, mode: r.mode, origin: r.origin, age_reg: car.ageReg }) }));
    const ok = rows.filter((r) => !r.blocked);
    const best = ok.reduce((a, b) => (b[key] < a[key] ? b : a), ok[0]);
    if (!selectedRoute || !rows.some((r) => r.id === selectedRoute)) selectedRoute = best.id;
    $("#best").innerHTML = `Дешевле всего: <b>${esc(best.label)}</b> — ${esc(best.who[0].toLowerCase() + best.who.slice(1))}.`;
    $("#best-total").innerHTML = `${fmt(best[key])}<small>тг</small>`;
    $("#best-share").textContent = pct((100 * best[key]) / best.value_kzt);
    $("#ages").textContent = `Стоимость ${fmt(best.value_kzt)} тг (${fmt(car.priceEur)} €). Для таможни машине ${car.age} полных лет, для сбора за регистрацию — ${car.ageReg} (считается «включая год выпуска»).`;

    const showRu = $("#show-ru").checked;
    const plot = rows.filter((r) => showRu || !isRu(r));
    stackedBars($("#cmp-chart"), plot.map((r) => ({ label: r.label, total: r[key], parts: partsOf(r, market) })), $("#cmp-legend"));
    $("#ru-note").textContent = showRu ? "" : "Россия/Беларусь: " + rows.filter(isRu).map((r) => `${r.label.split(" · ")[1]} — ${mln(r[key])} тг`).join("; ") + ". Утильсбор по коэффициенту 2 сжимает остальные бары, поэтому скрыт.";

    const head = ["Маршрут", "Итого, тг", "От стоимости", "Пошлина / ЕТП", "НДС", "Акциз", "Утильсбор", "Сбор за регистрацию", "Налог на транспорт в год", "Ограничения"];
    $("#cmp-table").innerHTML = `<thead><tr>${head.map((h, i) => `<th class="${i && i < 9 ? "num" : ""}">${h}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((r) => `<tr class="${r.blocked ? "blocked" : ""} ${r.id === best.id ? "is-best" : ""}"><td>${esc(r.label)}</td><td class="num"><b>${fmt(r[key])}</b></td><td class="num">${pct((100 * r[key]) / r.value_kzt)}</td><td class="num">${fmt(r.duty + r.etp)}</td><td class="num">${fmt(r.vat)}</td><td class="num">${fmt(r.excise)}</td><td class="num">${fmt(r.util)}</td><td class="num">${fmt(r.reg_fee)}</td><td class="num">${fmt(r.tax_year)}</td><td>${esc(r.flags.map((f) => f.split(" (")[0].split(":")[0]).join("; "))}</td></tr>`).join("") + "</tbody>";

    $("#route-seg").innerHTML = rows.map((r) => `<button type="button" data-route="${r.id}" aria-pressed="${r.id === selectedRoute}">${esc(r.label)}</button>`).join("");
    const r = rows.find((x) => x.id === selectedRoute);
    $("#route-who").textContent = r.who + (r.duty_basis !== "—" ? ` · ставка пошлины: ${r.duty_basis}` : "");
    const lines = COMPONENTS.filter(([k]) => r[k] > 0).map(([k, label, norm]) => `<tr><td>${label}</td><td class="num">${fmt(r[k])}</td><td>${esc(norm)}</td></tr>`);
    lines.push(`<tr class="total"><td>Итого обязательные</td><td class="num">${fmt(r.total)}</td><td></td></tr>`);
    if (market) lines.push(`<tr><td>Рыночные расходы (оценка)</td><td class="num">${fmt(r.market)}</td><td>ОГПО, брокер, СВХ, СБКТС, ЭПТС — рыночные диапазоны</td></tr>`);
    $("#route-table").innerHTML = `<thead><tr><th>Платёж</th><th class="num">Сумма, тг</th><th>Норма</th></tr></thead><tbody>${lines.join("")}</tbody>`;
    $("#route-flags").innerHTML = r.flags.map((f) => `<div class="flag">${esc(f)}</div>`).join("");
    $("#route-tax").textContent = `После регистрации — налог на транспорт около ${fmt(r.tax_year)} тг в год (НК ст. 565).`;
  }
  $("#route-seg").addEventListener("click", (e) => { const b = e.target.closest("button[data-route]"); if (b) { selectedRoute = b.dataset.route; renderCalc(); } });
  $("#car").addEventListener("input", renderCalc);
  $("#show-ru").addEventListener("change", renderCalc);
  $("#share").addEventListener("click", async () => {
    const c = readCar();
    const q = new URLSearchParams({ p: c.price, c: c.cur, f: c.fuel, v: c.cc, y: c.y, m: c.m, mk: $("#market").checked ? 1 : 0 });
    const url = location.origin + location.pathname + "#calc?" + q.toString();
    history.replaceState(null, "", "#calc?" + q.toString());
    try { await navigator.clipboard.writeText(url); $("#share-status").textContent = "Ссылка скопирована — по ней откроется этот же расчёт."; }
    catch { $("#share-status").textContent = url; }
  });


  /* ---------- как сэкономить ---------- */
  function renderSavings() {
    const d = data.savings, m = (v) => mln(v) + " тг", ev = d.ev.example, a = d.age, v = d.volume, t = d.ptd_dt;
    const card = (title, body) => `<div class="card stack"><h2 class="section-title">${title}</h2>${body}</div>`;
    const figs = (items) => `<div class="figures">${items.map(([l, val]) => `<div class="figure"><div class="label">${l}</div><div class="value" style="font-size:clamp(20px,3vw,26px)">${val}</div></div>`).join("")}</div>`;
    const ageWord = (n) => (n === 1 ? "год" : n >= 2 && n <= 4 ? "года" : "лет");
    const ptdRows = Object.keys(t.rows).map((age) => `<tr><td>${age} ${ageWord(+age)}</td>${t.rows[age].map((x) => {
      const val = x / 1e6, s = (val >= 0 ? "+" : "") + val.toFixed(1).replace(".", ",");
      return `<td class="num" style="color:${val < 0 ? "var(--div-neg)" : "var(--ink-2)"};font-weight:${val < 0 ? 600 : 400}">${s}</td>`; }).join("")}</tr>`).join("");
    $("#sv").innerHTML = [
      card("Самый выгодный профиль", `<p style="margin:0;font-size:16px">Электромобиль или машина с ДВС до 2 000 см³, не старше 2 лет по году выпуска, дешевле ${fmt(Math.floor(d.lux.eur / 100) * 100)} €, ввоз из Китая, Кореи или Японии по ДТ. Для дорогой машины 3–5 лет — ПТД.</p>
        <p class="note">Посчитано тем же калькулятором по ${fmt(d.configs)} машинам × 6 маршрутов: 9 двигателей, возраст 0–15 лет, 12 цен от 5 до 150 тыс. €. Варианты, которые нельзя поставить на учёт, исключены.</p>`),
      card("Не ввозить через Россию и Беларусь", `<p style="margin:0">В лучшем случае дороже лучшего маршрута на <b>${m(d.ru.min)}</b>, в среднем — на <b>${m(d.ru.median)}</b>. Причина — утильсбор по коэффициенту 2 (приказ МЭПР № 54).</p>`),
      card("Электромобиль — из третьих стран по ДТ", `<p style="margin:0">Выигрывает в ${d.ev.wins} из ${d.ev.n} вариантов: пошлина 0% по перечню ВТО, утильсбора нет, остаются НДС 16% и сборы. Так же оформляется гибрид, у которого мощнее электромотор.</p>
        ${figs([["Электромобиль", m(ev["электро"])], ["Гибрид (мощнее электромотор)", m(ev["гибрид_эл"])], ["Бензин 2,0 л", m(ev["бензин"])]])}
        <p class="note">Машина за ${fmt(d.ev.example_price)} €, 1 год, третьи страны · ДТ.</p>`),
      card("Возраст: граница — 3 года по году выпуска", `${figs([["2 года вместо 1", "+" + m(a.dt_1_2)], ["3 года вместо 2", "+" + m(a.dt_2_3)], ["ПТД: 6 лет вместо 5", "+" + m(a.ptd_5_6)]])}
        <p style="margin:0">Сбор за регистрацию считает возраст «включая год выпуска»: машина декабря 2023 года в 2026-м — уже «3 года и старше», января 2024-го — ещё нет. Разница до 2 млн тг может решаться месяцем выпуска.</p>
        <p class="note">Бензин 2,0 л, ${fmt(a.price)} €, третьи страны · ДТ. Скачок на 3 годах — сбор 500 МРП вместо 50; на 6 годах по ПТД — повышенная единая ставка.</p>`),
      card("Объём: до 3 000 см³, лучше до 2 000", `<div class="table-wrap"><table><thead><tr><th>Граница</th><th>Что меняется</th><th class="num">Цена перехода</th></tr></thead><tbody>
        <tr><td>2 000 → 2 100 см³</td><td>утильсбор 3,5 → 5</td><td class="num">+${m(v.v2000_2100)}</td></tr>
        <tr><td>3 000 → 3 100 см³</td><td>акциз 100 тг за каждый см³ всего объёма, утильсбор 11,5</td><td class="num">+${m(v.v3000_3100)}</td></tr></tbody></table></div>
        <p style="margin:0">Парадокс ЕТТ: новая бензиновая машина 2,8–3,0 л платит пошлину 12,5% вместо 15%, поэтому новая 2,9 л (${fmt(v.new_2900)} тг) дешевле новой 2,0 л (${fmt(v.new_2000)} тг) той же цены.</p>
        <p class="note">Машина за ${fmt(v.price)} €; переходы — для 4 лет, сравнение 2,9 и 2,0 л — для 1 года.</p>`),
      card("ПТД или ДТ для физлица", `<p class="note" style="margin:0">ПТД минус ДТ, млн тг, бензин 2,0 л. Минус (выделен) — ПТД дешевле.</p>
        <div class="table-wrap"><table><thead><tr><th>Возраст</th>${t.prices.map((p) => `<th class="num">${fmt(p)} €</th>`).join("")}</tr></thead><tbody>${ptdRows}</tbody></table></div>
        <p style="margin:0">Новые машины выгоднее по ДТ всегда. Для б/у 3–5 лет единая ставка считается от объёма, а не от цены, поэтому с 20 тыс. € ПТД выигрывает всё сильнее. Старше 5 лет — только ДТ: ЭПТС по ПТД не оформят. Минус ДТ — условный выпуск: машина обращается только в РК.</p>`),
      card("Кыргызстан и Армения: дёшево на бумаге", `<p style="margin:0">По платежам в РК физлицо из Кыргызстана или Армении выигрывает в <b>${Math.round(d.eaeu.by_kz.kg_fl || 0)}%</b> вариантов: пошлины нет, НДС с физлица не берут. Если прибавить пошлину ЕТТ, уже заложенную в цену машины там, — в <b>${Math.round(d.eaeu.by_landed.kg_fl || 0)}%</b>. Это оценка сверху: местный НДС, сборы и маржа перепродавца не учтены.</p>
        <p style="margin:0">Правило: маршрут выгоден, только если машина там стоит не дороже той же машины в Китае или Корее плюс 15–20%. Регулярный ввоз могут признать предпринимательским — тогда НДС 16%. Электромобили, ввезённые туда по льготе ЕАЭС, резидентам РК передавать нельзя.</p>`),
      card("Цена и статус ввозящего", `<ul class="findings">
        <li>Держаться ниже <b>${fmt(Math.floor(d.lux.eur / 100) * 100)} €</b> (${m(d.lux.kzt)}): с этого порога акциз 10%.</li>
        <li>У машины за ${fmt(d.cheap.price)} € фиксированные платежи составляют ${Math.round(d.cheap.share_min)}–${Math.round(d.cheap.share_max)}% её стоимости.</li>
        <li>Юрлицо — плательщик НДС берёт ввозной НДС в зачёт, поэтому для бизнеса ДТ реально дешевле, чем в расчётах: модель зачёт не учитывает.</li></ul>`),
    ].join("");
  }

  /* ---------- аналитика ---------- */
  let grid = null;
  const S = C.SCENARIO;
  function buildGrid() {
    grid = [];
    for (const r of ROUTES) for (const [fuel, cc] of S.engines) for (const age of S.ages) for (const price of S.prices)
      grid.push({ route: r, engine: engineLabel(fuel, cc), fuel, cc, age, price, ...K.calc({ price_eur: price, fuel, cc, age, mode: r.mode, origin: r.origin, age_reg: null }) });
  }
  const anEngine = $("#an-engine"), anPrice = $("#an-price"), anAge = $("#an-age");
  S.engines.forEach(([f, cc]) => anEngine.add(new Option(engineLabel(f, cc), engineLabel(f, cc))));
  S.prices.forEach((p) => anPrice.add(new Option(fmt(p) + " €", p)));
  S.ages.forEach((a) => anAge.add(new Option(a, a)));
  anEngine.value = "Бензин 2,0 л"; anPrice.value = 15000; anAge.value = 4;

  function renderAnalytics() {
    if (!grid) buildGrid();
    const eng = anEngine.value, price = +anPrice.value, age = +anAge.value, showRu = $("#an-ru").checked;
    const routes = ROUTES.filter((r) => showRu || !isRu(r));
    const pick = (f) => grid.filter(f);
    const cur = pick((g) => g.engine === eng && g.price === price && g.age === age);
    const by = Object.fromEntries(cur.map((g) => [g.route.id, g]));
    const cheap = cur.filter((g) => !isRu(g.route)).reduce((a, b) => (b.total < a.total ? b : a));
    const dtByAge = Object.fromEntries(pick((g) => g.engine === eng && g.price === price && g.route.id === "dt").map((g) => [g.age, g.total]));
    const f = [
      `Дешевле всего — <b>${esc(cheap.route.label)}</b>: ${mln(cheap.total)} тг против ${mln(by.dt.total)} тг по ДТ из третьих стран.`,
      `Из России или Беларуси та же машина обойдётся в <b>${mln(by.ru_fl.total)} тг</b> платежей — в ${Math.round(by.ru_fl.total / cheap.total)} раз больше, почти целиком утильсбор.`,
      `Переход машины из 2 в 3 года добавляет <b>${mln(dtByAge[3] - dtByAge[2])} тг</b> по ДТ: сбор за регистрацию растёт с 50 до 500 МРП, пошлина переходит на ставки для б/у.`,
      `ПТД для физлица здесь ${by.ptd.total < by.dt.total ? "дешевле" : "дороже"} ДТ на ${mln(Math.abs(by.ptd.total - by.dt.total))} тг${age > 5 ? ", но старше 5 лет ЭПТС по ПТД не оформят" : ""}.`,
    ];
    $("#findings").innerHTML = f.map((x) => `<li>${x}</li>`).join("");

    stackedBars($("#an-struct"), routes.map((r) => ({ label: r.label, total: by[r.id].total, parts: partsOf(by[r.id]) })), $("#an-struct-legend"));

    const ages = S.ages;
    lineChart($("#an-age-chart"), ages, routes.map((r) => ({ name: r.label, color: r.color,
      values: ages.map((a) => grid.find((g) => g.route.id === r.id && g.engine === eng && g.price === price && g.age === a).total / 1e6) })),
      { yTitle: "млн тг", rule: { index: ages.indexOf(3), label: "3 года" }, tipFmt: (v) => fmt(v * 1e6) + " тг" }, $("#an-age-legend"));

    const prices = S.prices;
    lineChart($("#an-price-chart"), prices.map((p) => fmt(p) + " €"), routes.map((r) => ({ name: r.label, color: r.color,
      values: prices.map((p) => grid.find((g) => g.route.id === r.id && g.engine === eng && g.price === p && g.age === age).share_pct) })),
      { yTitle: "% от стоимости", yFmt: (v) => v + "%", tipFmt: (v) => pct(v) }, $("#an-price-legend"));

    // тепловая карта ПТД − ДТ
    const neg = cssVar("--div-neg"), neg2 = cssVar("--div-neg-2"), mid = cssVar("--div-mid"), pos2 = cssVar("--div-pos-2"), pos = cssVar("--div-pos");
    const cells = [];
    let lim = 0.001;
    for (const a of ages) for (const p of prices) {
      const pt = grid.find((g) => g.route.id === "ptd" && g.engine === eng && g.price === p && g.age === a);
      const dt = grid.find((g) => g.route.id === "dt" && g.engine === eng && g.price === p && g.age === a);
      const d = (pt.total - dt.total) / 1e6;
      cells.push({ a, p, d, na: a > 5 });
      if (a <= 5) lim = Math.max(lim, Math.abs(d));
    }
    const mix = (c1, c2, t) => { const h = (c) => c.match(/\w\w/g).map((x) => parseInt(x, 16)); const A = h(c1), B = h(c2); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`; };
    const color = (d) => { const t = Math.min(Math.abs(d) / lim, 1); return d < 0 ? (t < .5 ? mix(mid, neg2, t * 2) : mix(neg2, neg, (t - .5) * 2)) : (t < .5 ? mix(mid, pos2, t * 2) : mix(pos2, pos, (t - .5) * 2)); };
    const heat = $("#an-heat");
    heat.style.gridTemplateColumns = `auto repeat(${prices.length}, minmax(64px, 1fr))`;
    heat.innerHTML = `<div class="hdr">возраст</div>` + prices.map((p) => `<div class="hdr">${fmt(p)} €</div>`).join("") +
      ages.map((a) => `<div class="rowh">${a}</div>` + cells.filter((c) => c.a === a).map((c) => c.na
        ? `<div class="cell" style="background:var(--line-2);color:var(--ink-3)" data-tip="${esc(tipHtml(`${a} лет, ${fmt(c.p)} €`, ["ЭПТС по ПТД не оформят — сравнивать не с чем"]))}">нет ЭПТС</div>`
        : `<div class="cell" style="background:${color(c.d)};color:${Math.abs(c.d) > lim * 0.55 ? "#fff" : "var(--ink)"}" data-tip="${esc(tipHtml(`${a} лет, ${fmt(c.p)} €`, [`ПТД минус ДТ: <b>${(c.d >= 0 ? "+" : "") + c.d.toFixed(2).replace(".", ",")} млн тг</b>`]))}">${(c.d >= 0 ? "+" : "") + c.d.toFixed(1).replace(".", ",")}</div>`).join("")).join("");

    const e = pick((g) => g.route.id === "dt" && g.price === price && g.age === age).sort((a, b) => a.total - b.total);
    stackedBars($("#an-engines"), e.map((g) => ({ label: g.engine, total: g.total, parts: partsOf(g) })), $("#an-engines-legend"));

    const base = 50 * C.MRP;
    groupedBars($("#an-util"), ["Электромобиль", "до 1 000 см³", "1 001–2 000 см³", "2 001–3 000 см³", "свыше 3 000 см³"], [
      { name: "Другие страны и сборка РК", color: "--s1", values: [C.UTIL_EV["третьи"], ...C.UTIL_K1].map((k) => k * base) },
      { name: "Россия, Беларусь", color: "--s8", values: [C.UTIL_EV["РФ_РБ"], ...C.UTIL_K2].map((k) => k * base) },
    ], $("#an-util-legend"));
  }
  [anEngine, anPrice, anAge, $("#an-ru")].forEach((el) => el.addEventListener("change", renderAnalytics));

  /* ---------- база ставок ---------- */
  const blocks = [...new Set(data.rates.map((r) => r.block))].sort((a, b) => a.localeCompare(b, "ru"));
  blocks.forEach((b) => $("#r-block").add(new Option(b, b)));
  const range = (a, b, unit) => (a == null && b == null ? "" : a == null ? `до ${fmt(b)}${unit}` : b == null ? `от ${fmt(a)}${unit}` : `${fmt(a)}–${fmt(b)}${unit}`);
  const rateText = (r) => {
    const p = [];
    if (r.pct != null) p.push(pct(r.pct, r.pct % 1 ? 1 : 0));
    if (r.spec != null) p.push(`${String(r.spec).replace(".", ",")} ${r.spec_unit || ""}`.trim());
    if (r.mrp != null && r.block !== "Утилизационный платёж") p.push(`${String(r.mrp).replace(".", ",")} МРП`);
    if (r.coef != null) p.push(`коэфф. ${String(r.coef).replace(".", ",")}`);
    if (!p.length && r.rate_text) p.push(r.rate_text);
    return p.join(" · ");
  };
  let openRate = null;
  function renderRates() {
    const q = $("#r-q").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const block = $("#r-block").value, rel = $("#r-rel").value, cur = $("#r-cur").checked;
    const rows = data.rates.filter((r) => (!block || r.block === block) && (!rel || r.rel === rel) && (!cur || r.current === "да") &&
      (!q.length || q.every((w) => Object.values(r).join(" ").toLowerCase().includes(w))));
    $("#r-count").textContent = `Найдено ${rows.length} из ${data.rates.length}.`;
    const head = ["id", "Блок", "Платёж", "Категория ТС", "Двигатель", "Объём, см³", "Возраст, лет", "Ставка", "тг (2026)", "Дост."];
    $("#r-table").innerHTML = `<thead><tr>${head.map((h, i) => `<th class="${i === 8 ? "num" : ""}">${h}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((r) => {
        let tr = `<tr data-id="${r.id}"><td>${r.id}</td><td>${esc(r.block)}</td><td>${esc(r.kind)}</td><td>${esc(r.category)}</td><td>${esc(r.fuel)}</td><td>${range(r.cc_from, r.cc_to, "")}</td><td>${range(r.age_from, r.age_to, "")}</td><td>${esc(rateText(r))}</td><td class="num">${r.kzt != null && !isNaN(+r.kzt) ? fmt(+r.kzt) : ""}</td><td><span class="chip rel-${esc(r.rel)}">${esc(r.rel)}</span></td></tr>`;
        if (r.id === openRate) {
          const dl = [["Этап", r.stage], ["Код ТН ВЭД", r.hs], ["Категория ЕЭК", r.eec], ["Субъект", r.subject], ["Происхождение", r.origin], ["Режим", r.regime],
            ["Минимум", r.minimum], ["Формула", r.formula], ["Действует", [r.from, r.to].filter(Boolean).join(" — ")], ["Примечание", r.note],
            ["Норма", [r.act, r.article].filter(Boolean).join(", ")]].filter(([, v]) => v);
          tr += `<tr class="detail"><td colspan="10"><dl>${dl.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}${r.url ? `<dt>Источник</dt><dd><a href="${esc(r.url)}" target="_blank" rel="noopener">открыть</a></dd>` : ""}</dl></td></tr>`;
        }
        return tr;
      }).join("") + "</tbody>";
  }
  $("#r-table").addEventListener("click", (e) => {
    if (e.target.closest("a") || e.target.closest("tr.detail")) return;
    const tr = e.target.closest("tr[data-id]"); if (!tr) return;
    openRate = openRate === tr.dataset.id ? null : tr.dataset.id; renderRates();
  });
  ["#r-q", "#r-block", "#r-rel", "#r-cur"].forEach((s) => $(s).addEventListener("input", renderRates));

  /* ---------- спорные и о данных ---------- */
  function renderQuestions() {
    $("#q-list").innerHTML = data.questions.map((q, i) => `<details class="q"><summary>${i + 1}. ${esc(q.q)}</summary><p><b>В чём неясность.</b> ${esc(q.issue)}</p><p><b>Как учтено.</b> ${esc(q.how)}</p></details>`).join("");
  }
  function renderAbout() {
    $("#cond-table").innerHTML = `<thead><tr><th>Условие</th><th>Категория ТС</th><th>Норма</th><th>Дост.</th></tr></thead><tbody>` +
      data.conditions.map((c) => `<tr><td>${esc(c.what)}${c.note ? `<div class="note">${esc(c.note)}</div>` : ""}</td><td>${esc(c.category)}</td><td>${esc([c.act, c.article].filter(Boolean).join(", "))}</td><td><span class="chip rel-${esc(c.rel)}">${esc(c.rel)}</span></td></tr>`).join("") + "</tbody>";
    $("#src-table").innerHTML = `<thead><tr><th>Акт</th><th class="num">Записей</th><th>Блоки</th></tr></thead><tbody>` +
      data.sources.map((s) => `<tr><td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.act)}</a>` : esc(s.act)}</td><td class="num">${s.n}</td><td>${esc(s.blocks)}</td></tr>`).join("") + "</tbody>";
  }

  const render = { calc: renderCalc, savings: renderSavings, analytics: renderAnalytics, rates: renderRates, questions: renderQuestions, about: renderAbout };
  let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => render[tabs.find((b) => b.getAttribute("aria-selected") === "true").dataset.tab]?.(), 150); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => render.analytics && !$("#analytics").hidden && renderAnalytics());
  showTab(hashTab || "calc", false);
  document.fonts?.ready.then(() => render[tabs.find((b) => b.getAttribute("aria-selected") === "true").dataset.tab]?.());
})();
