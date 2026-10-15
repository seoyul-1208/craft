(() => {
  "use strict";
  const D = window.MC_DATA;
  const $ = (s) => document.querySelector(s);
  const ITEMS = D.items;
  const RECIPES = D.recipes;
  const DEFAULT_RAW = new Set(D.raw);
  const STORAGE = D.storage; // 재료 -> 9개짜리 블록
  const STACK = 64, SHULKER = 27, CHEST = 54;
  const KIND = { craft: "제작대", smelt: "화로", cut: "석재 절단기", smith: "대장장이 작업대", water: "물에 닿게 하기",
    dye: "제작대 (양털 염색)", mud: "흙에 물병 사용", drip: "뾰족한 점적석 위에 두고 말리기", break: "부수기",
    build: "구리 블록 위에 조각한 호박 올리기", statue: "구리 골렘이 완전히 산화되면 동상이 됨", scrape: "도끼로 녹 벗기기" };

  const byResult = {};
  RECIPES.forEach((r, i) => (byResult[r.r] ||= []).push(i));

  // ---------- 저장되는 사용자 설정 ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  let overrides = store.get("mc.overrides", { raw: {}, recipe: {} });
  const saveOverrides = () => store.set("mc.overrides", overrides);

  const name = (id) => (ITEMS[id] ? ITEMS[id].ko : id);
  function icon(id, cls = "ic") {
    const it = ITEMS[id];
    if (it && it.i) return `<img class="${cls}${it.s ? ` shape-${it.s}` : ""}" src="icons/${it.i}" alt="" loading="lazy">`;
    return `<span class="${cls} none">${esc(name(id).slice(0, 1))}</span>`;
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- 수량 표기 ----------
  function fmtQty(n) {
    if (n < STACK) return `${n}개`;
    const sets = Math.floor(n / STACK), rem = n % STACK;
    const chests = Math.floor(sets / CHEST), shulkers = Math.floor((sets % CHEST) / SHULKER), s = sets % SHULKER;
    if (!chests && !shulkers) return `${n}개(${sets}세트${rem ? ` ${rem}개` : ""})`;
    const parts = [];
    if (chests) parts.push(`${chests}큰상자`);
    if (shulkers) parts.push(`${shulkers}셜커`);
    if (s) parts.push(`${s}세트`);
    if (rem) parts.push(`${rem}개`);
    return `${n}개(${parts.join(", ")})`;
  }
  function storageText(id, n) {
    const block = STORAGE[id];
    if (!block || n < 9) return "";
    const b = Math.floor(n / 9), r = n % 9;
    return `= ${name(block)} ${fmtQty(b)}${r ? ` + ${r}개` : ""}`;
  }

  // ---------- 레시피 선택 (원재료 개수 기준으로 가장 적게 드는 쪽) ----------
  const isForcedRaw = (id) => overrides.raw[id] === true || (overrides.raw[id] !== false && DEFAULT_RAW.has(id));

  function solve() {
    const cost = {}, depth = {}, choice = {};
    const get = (id) => (cost[id] === undefined ? Infinity : cost[id]);
    // 지정된 원재료와 레시피가 없는 아이템(원목, 조약돌 등)은 원재료 1개로 센다
    for (const id of Object.keys(ITEMS)) if (isForcedRaw(id) || !byResult[id]) { cost[id] = 1; depth[id] = 0; }

    const evalRecipe = (ri) => {
      const r = RECIPES[ri];
      let total = 0, dep = 0;
      const picks = [];
      for (let i = 0; i < r.s.length; i++) {
        let best = null;
        for (const a of r.s[i]) {
          const c = get(a);
          if (c === Infinity) continue;
          if (!best || c < get(best) - 1e-9 || (Math.abs(c - get(best)) < 1e-9 && depth[a] < depth[best])) best = a;
        }
        if (!best) return null;
        picks.push(best);
        total += (r.n[i] * get(best)) / r.c;
        dep = Math.max(dep, depth[best] + 1);
      }
      return { ri, picks, cost: total, depth: dep, out: r.c };
    };

    for (let round = 0; round < 200; round++) {
      let changed = false;
      for (const id in byResult) {
        if (isForcedRaw(id)) continue;
        const forced = overrides.recipe[id];
        const list = forced !== undefined && byResult[id].includes(forced) ? [forced] : byResult[id];
        for (const ri of list) {
          const e = evalRecipe(ri);
          if (!e) continue;
          const cur = get(id);
          // 원재료가 적게 드는 쪽 → 단계가 적은 쪽 → 한 번에 적게 나와 남는 게 적은 쪽
          const same = Math.abs(e.cost - cur) < 1e-9;
          if (e.cost < cur - 1e-9 || (same && e.depth < depth[id]) ||
              (same && e.depth === depth[id] && choice[id] && e.out < choice[id].out)) {
            cost[id] = e.cost; depth[id] = e.depth; choice[id] = e; changed = true;
          }
        }
      }
      if (!changed) {
        // 순환 레시피만 있어서 만들 수 없는 아이템은 원재료로 보고 한 번 더 계산한다
        // 한 번에 하나씩만 원재료로 바꿔야 그 아이템으로 만드는 것들은 정상 계산된다
        const stuck = Object.keys(byResult).find((id) => get(id) === Infinity);
        if (stuck === undefined) break;
        cost[stuck] = 1; depth[stuck] = 0;
      }
    }
    return { cost, choice, evalRecipe };
  }

  // ---------- 수량 계산 ----------
  function calculate(requests) {
    const sol = solve();
    const broken = new Set();
    const isRaw = (id) => !sol.choice[id] || broken.has(id);
    const order = [], state = {};
    const visit = (id) => {
      if (state[id] === 2) return;
      if (state[id] === 1) { broken.add(id); return; } // 순환 방지
      state[id] = 1;
      if (!isRaw(id)) for (const p of sol.choice[id].picks) visit(p);
      state[id] = 2;
      order.push(id);
    };
    requests.forEach((r) => visit(r.id));
    order.reverse(); // 완성품 → 재료 순서

    const demand = {}, direct = {}, uses = {}, crafts = {};
    const woolDye = {}, dyeOf = {}; // 양털 염색에 드는 염료는 따로 모아 양털 아래에 보여준다
    for (const r of requests) {
      demand[r.id] = (demand[r.id] || 0) + r.qty;
      direct[r.id] = (direct[r.id] || 0) + r.qty;
    }
    for (const id of order) {
      const d = demand[id] || 0;
      if (!d || isRaw(id)) continue;
      const ch = sol.choice[id], r = RECIPES[ch.ri];
      const times = Math.ceil(d / r.c);
      crafts[id] = { times, made: times * r.c };
      ch.picks.forEach((p, i) => {
        const amt = times * r.n[i];
        if (r.t === "dye" && p !== "white_wool") {
          woolDye[p] = (woolDye[p] || 0) + amt;
          dyeOf[id] = { id: p, amt };
          return;
        }
        demand[p] = (demand[p] || 0) + amt;
        (uses[p] ||= {})[id] = (uses[p][id] || 0) + amt;
      });
    }

    // 입력 순서: 그 아이템을 거쳐 가는 요청 중 가장 먼저 입력된 것
    const reqIndex = {};
    requests.forEach((r, i) => (reqIndex[r.id] ??= i));
    const firstMemo = {};
    const first = (id) => {
      if (id in firstMemo) return firstMemo[id];
      firstMemo[id] = Infinity;
      let m = reqIndex[id] ?? Infinity;
      for (const k in uses[id] || {}) m = Math.min(m, first(k));
      return (firstMemo[id] = m);
    };
    for (const w in dyeOf) {
      const dy = dyeOf[w].id;
      firstMemo[dy] = Math.min(firstMemo[dy] ?? Infinity, first(w));
    }

    const roots = Object.keys(demand).filter(isRaw);
    const R = { sol, demand, direct, uses, crafts, roots, isRaw, first, dyeOf, woolDye };
    R.dye = decompose(woolDye, sol, isRaw);
    return R;
  }

  // 섞은 염료를 기본 염료까지 분해 (청록색 염료 16개 → 파란색 8개 + 초록색 8개)
  function decompose(ledger, sol, isRaw) {
    const order = [], seen = {};
    const visit = (id) => {
      if (seen[id]) return;
      seen[id] = 1;
      if (!isRaw(id)) sol.choice[id].picks.forEach(visit);
      order.push(id);
    };
    Object.keys(ledger).forEach(visit);
    order.reverse();
    const demand = { ...ledger }, crafts = {}, parts = {};
    for (const id of order) {
      const d = demand[id] || 0;
      if (!d || isRaw(id)) continue;
      const ch = sol.choice[id], r = RECIPES[ch.ri];
      const times = Math.ceil(d / r.c);
      crafts[id] = { times, made: times * r.c };
      parts[id] = ch.picks.map((p, i) => {
        demand[p] = (demand[p] || 0) + times * r.n[i];
        return [p, times * r.n[i]];
      });
    }
    const base = order.filter((id) => isRaw(id) && demand[id]);
    return { sol, demand, crafts, parts, isRaw, top: Object.keys(ledger), base };
  }

  // ---------- 입력 해석 ----------
  const norm = (s) => s.toLowerCase().replace(/[\s_]/g, "");
  const index = Object.entries(ITEMS).map(([id, it]) => ({ id, ko: norm(it.ko), en: norm(it.en), idn: norm(id) }));
  const exact = new Map();
  for (const e of index) for (const k of [e.idn, e.en, e.ko]) exact.set(k, e.id);

  const UNIT = { "큰상자": STACK * CHEST, "상자": STACK * CHEST, "셜커": STACK * SHULKER, "세트": STACK, "개": 1 };
  const QTY_RE = /(\d+)\s*(큰상자|상자|셜커|세트|개)?/g;

  function splitLine(line) {
    let qty = 0, found = false;
    const qtyParts = [];
    const rest = line.replace(QTY_RE, (m, n, u) => {
      found = true; qty += Number(n) * UNIT[u || "개"]; qtyParts.push(m.trim()); return " ";
    }).replace(/[x×*:=,\-]/gi, " ").trim();
    return { name: rest, qty: found ? qty : 1, qtyText: qtyParts.join(" ") };
  }
  function candidates(q, limit = 12) {
    const n = norm(q);
    if (!n) return [];
    const out = [];
    for (const e of index) {
      const i = Math.min(...[e.ko, e.en, e.idn].map((s) => { const p = s.indexOf(n); return p < 0 ? 1e9 : p; }));
      if (i < 1e9) out.push({ id: e.id, score: (exact.get(n) === e.id ? -1000 : 0) + e.ko.length + i * 3 + (byResult[e.id] ? 0 : 50) });
    }
    return out.sort((a, b) => a.score - b.score).slice(0, limit).map((x) => x.id);
  }
  function resolve(q) {
    const n = norm(q);
    if (exact.has(n)) return { id: exact.get(n) };
    const c = candidates(q, 50);
    if (c.length === 1) return { id: c[0] };
    return { options: c.slice(0, 12) };
  }

  function parseInput(text) {
    const reqs = [], errors = [];
    text.split("\n").forEach((line, li) => {
      if (!line.trim()) return;
      const { name: q, qty } = splitLine(line);
      if (!q) { errors.push({ li, msg: `"${line.trim()}": 아이템 이름이 없어요.` }); return; }
      if (qty <= 0) return;
      const r = resolve(q);
      if (r.id) reqs.push({ id: r.id, qty });
      else if (r.options.length) errors.push({ li, msg: `"${q}"에 해당하는 아이템이 여러 개예요. 골라 주세요:`, options: r.options });
      else errors.push({ li, msg: `"${q}"을(를) 찾지 못했어요.` });
    });
    return { reqs, errors };
  }

  // ---------- 화면 ----------
  const ta = $("#req");
  let last = null;
  let sortMode = store.get("mc.sort", "input");
  const collapsed = new Set(store.get("mc.collapsed", []));

  function replaceLine(li, id) {
    const lines = ta.value.split("\n");
    const { qtyText } = splitLine(lines[li] || "");
    lines[li] = `${name(id)} ${qtyText}`.trimEnd() + (qtyText ? "" : " ");
    ta.value = lines.join("\n");
    store.set("mc.input", ta.value);
    return lines.slice(0, li + 1).join("\n").length;
  }

  function run() {
    store.set("mc.input", ta.value);
    const { reqs, errors } = parseInput(ta.value);
    $("#errors").innerHTML = errors.map((e) =>
      `<div class="err">${esc(e.msg)}${e.options ? `<div>${e.options.map((id) =>
        `<button class="chip" type="button" data-li="${e.li}" data-id="${id}">${icon(id)}${esc(name(id))}</button>`).join("")}</div>` : ""}</div>`).join("");
    const merged = {};
    reqs.forEach((r) => (merged[r.id] = (merged[r.id] || 0) + r.qty));
    const list = Object.entries(merged).map(([id, qty]) => ({ id, qty }));
    if (!list.length) {
      last = null;
      $("#tree").innerHTML = `<p class="empty">왼쪽에 아이템을 입력하고 Enter를 누르세요.</p>`;
      return;
    }
    last = calculate(list);
    renderTree();
  }

  // 재료순: 최상위는 나무 → 돌 → 흙 → 기타 블록 → 아이템 그룹으로 나누고, 그 안과 하위 폴더는 하위 폴더가 많은 것 → 수량이 많은 것
  const group = (id) => (ITEMS[id] ? ITEMS[id].g : 4);
  function sortIds(ids, R, qtyOf = (id) => R.demand[id], isRoot = false) {
    const byName = (a, b) => name(a).localeCompare(name(b), "ko");
    const kidCount = (id) => Object.keys(R.uses?.[id] || R.parts?.[id] || {}).length + (id === "white_wool" && R.woolDye && Object.keys(R.woolDye).length ? 1 : 0);
    const cmp = {
      name: byName,
      input: (a, b) => (last.first(a) - last.first(b)) || byName(a, b),
      material: (a, b) => (isRoot ? group(a) - group(b) : 0) || (kidCount(b) - kidCount(a)) || (qtyOf(b) - qtyOf(a)) || byName(a, b),
    }[sortMode] || byName;
    return [...ids].sort(cmp);
  }

  function rowHtml(id, qty, o) {
    const sub = o.sub || [];
    return `<div class="node${o.root ? " root" : ""}${collapsed.has(o.key) ? " collapsed" : ""}" data-key="${esc(o.key)}">` +
      `<div class="row"${id ? ` data-id="${id}"` : ""}${o.ctx ? ` data-ctx="${o.ctx}"` : ""}>` +
      `<span class="caret${o.hasKids ? "" : " leaf"}">▼</span>${o.iconHtml ?? icon(id)}` +
      `<span class="name">${esc(o.label ?? name(id))}</span>` +
      (qty != null ? `<span class="qty">${fmtQty(qty)}</span>` : "") +
      (o.tag ? `<span class="tag">${esc(o.tag)}</span>` : "") +
      (sub.length ? `<span class="sub">${esc(sub.join(" · "))}</span>` : "") +
      (o.acts ? `<span class="acts">${o.acts}</span>` : "") +
      `</div><div class="children">`;
  }

  function actsHtml(id, R, isRoot) {
    const canSwitch = (byResult[id] || []).length > 1 && !R.isRaw(id);
    const hasRecipe = !!byResult[id];
    return (canSwitch ? `<button type="button" data-act="recipe" data-id="${id}" title="다른 레시피 고르기">⇄ 레시피</button>` : "") +
      (hasRecipe && !R.isRaw(id) ? `<button type="button" data-act="stop" data-id="${id}" title="이 아이템을 원재료로 취급합니다">여기서 멈추기</button>` : "") +
      (hasRecipe && R.isRaw(id) && isRoot ? `<button type="button" data-act="split" data-id="${id}" title="이 아이템을 레시피대로 더 분해합니다">더 분해하기</button>` : "");
  }

  function renderTree() {
    const R = last;
    const html = [];
    const dyeKeys = Object.keys(R.woolDye);

    // 양털 아래의 염료 폴더
    const dyeFolder = (path) => {
      const D2 = R.dye;
      const key = [...path, "#염료"].join(">");
      const baseSum = sortIds(D2.base, D2).map((b) => `${name(b)} ${D2.demand[b]}개`).join(", ");
      html.push(rowHtml(null, null, { key, hasKids: true, label: "염료", iconHtml: `<span class="ic none">🎨</span>`,
        sub: baseSum ? [`기본 염료 합계: ${baseSum}`] : [] }));
      const walkDye = (id, p, amt) => {
        const k = [...p, id].join(">");
        const parts = D2.parts[id] || [];
        const c = D2.crafts[id];
        const sub = c && c.made > D2.demand[id] ? [`${c.made}개 제작, ${c.made - D2.demand[id]}개 남음`] : [];
        html.push(rowHtml(id, amt, { key: k, hasKids: parts.length > 0, ctx: "dye", sub, acts: actsHtml(id, D2, false) }));
        parts.forEach(([pid, a]) => walkDye(pid, [...p, id], a));
        html.push(`</div></div>`);
      };
      sortIds(D2.top, D2, (id) => R.woolDye[id]).forEach((id) => walkDye(id, [...path, "#염료"], R.woolDye[id]));
      html.push(`</div></div>`);
    };

    const walk = (id, path, isRoot, seen) => {
      const key = path.join(">");
      const kids = sortIds(Object.keys(R.uses[id] || {}).filter((k) => !seen.has(k)), R);
      const withDye = id === "white_wool" && dyeKeys.length > 0;
      const qty = R.demand[id];
      const c = R.crafts[id];
      const sub = [];
      if (R.isRaw(id)) { const s = storageText(id, qty); if (s) sub.push(s); }
      if (R.dyeOf[id]) sub.push(`${name(R.dyeOf[id].id)} ${R.dyeOf[id].amt}개로 염색`);
      if (c && c.made > qty) sub.push(`${c.made}개 제작, ${c.made - qty}개 남음`);
      html.push(rowHtml(id, qty, {
        key, root: isRoot, hasKids: kids.length > 0 || withDye, sub,
        label: withDye ? "양털" : undefined,
        tag: R.direct[id] && (kids.length || withDye) ? `요청 ${R.direct[id]}개` : "",
        acts: actsHtml(id, R, isRoot),
      }));
      if (withDye) dyeFolder(path);
      const next = new Set(seen).add(id);
      kids.forEach((k) => walk(k, [...path, k], false, next));
      html.push(`</div></div>`);
    };
    sortIds(R.roots, R, undefined, true).forEach((id) => walk(id, [id], true, new Set()));
    $("#tree").innerHTML = html.join("");
  }

  // ---------- 조합법 툴팁 ----------
  // times: 제작 횟수. 칸마다 그 재료가 times개씩 필요하므로 칸 오른쪽 아래에 적는다
  function recipeGrid(ri, picks, times) {
    const r = RECIPES[ri];
    const pick = (slot) => (picks ? picks[slot] : r.s[slot][0]);
    let cells = r.g, w = r.w;
    if (r.t === "craft" || r.t === "dye") {
      // 제작대는 항상 3x3. 모양 있는 레시피는 폭 2면 오른쪽 두 열(문: 2,3,5,6,8,9번), 폭·높이 1이면 가운데에 놓는다
      const grid3 = Array(9).fill(-1);
      if (w) {
        const h = cells.length / w, dx = w === 3 ? 0 : 1, dy = h === 1 ? 1 : 0;
        cells.forEach((s, i) => (grid3[(Math.floor(i / w) + dy) * 3 + (i % w) + dx] = s));
      } else cells.forEach((s, i) => (grid3[i] = s));
      cells = grid3; w = 3;
    } else if (!w) w = r.g.length;
    const need = times > 1 ? `<span class="cnt need">${times}</span>` : "";
    const grid = cells.map((s) => `<div class="slot">${s >= 0 ? icon(pick(s)) + need : ""}</div>`).join("");
    const out = times ? times * r.c : r.c;
    return `<div class="craft"><div class="grid" style="grid-template-columns:repeat(${w},36px)">${grid}</div>` +
      `<span class="arrow">➜</span><div class="slot out">${icon(r.r)}${out > 1 ? `<span class="cnt">${out}</span>` : ""}</div></div>`;
  }

  function tipHtml(id, ctx) {
    const R = ctx === "dye" ? last.dye : last;
    let h = `<h3>${esc(name(id))}</h3>`;
    if (R.isRaw(id)) {
      h += `<div class="kind">원재료</div><div>필요: ${fmtQty(R.demand[id])}</div>`;
      const s = storageText(id, R.demand[id]);
      if (s) h += `<div class="muted">${esc(s)}</div>`;
      if (byResult[id]) h += `<div class="muted" style="margin-top:6px">레시피가 있는 아이템이에요. ‘더 분해하기’로 재료까지 계산할 수 있어요.</div>`;
      return h;
    }
    const ch = R.sol.choice[id], r = RECIPES[ch.ri], c = R.crafts[id];
    h += `<div class="kind">${KIND[r.t]}</div>` + recipeGrid(ch.ri, ch.picks, c && c.times);
    if (c) {
      h += `<div>제작 ${c.times}회 → ${c.made}개${c.made > R.demand[id] ? ` (${c.made - R.demand[id]}개 남음)` : ""}</div><ul>`;
      ch.picks.forEach((p, i) => (h += `<li>${esc(name(p))} ${fmtQty(c.times * r.n[i])}</li>`));
      h += `</ul>`;
    }
    const alt = r.s.some((s) => s.length > 1);
    if (alt) h += `<div class="muted" style="margin-top:6px">같은 종류의 다른 재료(예: 다른 나무)로도 만들 수 있어요.</div>`;
    return h;
  }

  const tip = $("#tip");
  function placeFloating(el, x, y) {
    const pad = 14, vw = innerWidth, vh = innerHeight;
    const r = el.getBoundingClientRect();
    let left = x + pad, top = y + pad;
    if (left + r.width > vw - 8) left = Math.max(8, x - r.width - pad);
    if (top + r.height > vh - 8) top = Math.max(8, vh - r.height - 8);
    el.style.left = left + "px"; el.style.top = top + "px";
  }
  let tipId = null;
  $("#tree").addEventListener("mousemove", (e) => {
    // 아이템 이름이나 아이콘 위에 있을 때만 조합법을 보여준다
    const row = e.target.closest(".row .name, .row .ic")?.closest(".row");
    if (!row || !last || !$("#menu").hidden) { tip.hidden = true; tipId = null; return; }
    const id = row.dataset.id;
    if (!id) { tip.hidden = true; tipId = null; return; }
    const tk = id + (row.dataset.ctx || "");
    if (tk !== tipId) { tip.innerHTML = tipHtml(id, row.dataset.ctx); tipId = tk; }
    tip.hidden = false;
    placeFloating(tip, e.clientX, e.clientY);
  });
  $("#tree").addEventListener("mouseleave", () => { tip.hidden = true; tipId = null; });

  // ---------- 레시피 고르기 메뉴 ----------
  const menu = $("#menu");
  function openMenu(id, btn) {
    const sol = last.sol;
    const cur = sol.choice[id] && sol.choice[id].ri;
    const forced = overrides.recipe[id];
    const rows = byResult[id].map((ri) => {
      const e = sol.evalRecipe(ri);
      if (!e) return "";
      const r = RECIPES[ri];
      const ings = e.picks.map((p, i) => `<span class="mi">${icon(p)}${esc(name(p))}×${r.n[i]}</span>`).join(" ");
      return `<button type="button" data-ri="${ri}" class="${ri === cur ? "on" : ""}"><b>${KIND[r.t]}</b> ${ings} → ${r.c}개</button>`;
    }).join("");
    menu.innerHTML = `<button type="button" data-ri="auto" class="${forced === undefined ? "on" : ""}"><b>자동</b> 원재료가 가장 적게 드는 레시피</button>` + rows;
    menu.hidden = false;
    menu.dataset.id = id;
    tip.hidden = true;
    const b = btn.getBoundingClientRect();
    placeFloating(menu, b.left - 14, b.bottom - 10);
  }
  menu.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const id = menu.dataset.id;
    if (b.dataset.ri === "auto") delete overrides.recipe[id];
    else overrides.recipe[id] = Number(b.dataset.ri);
    saveOverrides();
    menu.hidden = true;
    run();
  });
  document.addEventListener("click", (e) => {
    if (!menu.hidden && !menu.contains(e.target) && !e.target.closest("[data-act=recipe]")) menu.hidden = true;
  });

  // ---------- 트리 조작 ----------
  $("#tree").addEventListener("click", (e) => {
    const act = e.target.closest("[data-act]");
    if (act) {
      const id = act.dataset.id;
      if (act.dataset.act === "recipe") return openMenu(id, act);
      if (act.dataset.act === "stop") overrides.raw[id] = true;
      if (act.dataset.act === "split") {
        if (DEFAULT_RAW.has(id)) overrides.raw[id] = false; else delete overrides.raw[id];
      }
      saveOverrides();
      tip.hidden = true;
      return run();
    }
    const row = e.target.closest(".row");
    if (!row) return;
    const node = row.parentElement;
    if (!node.querySelector(":scope > .children > .node")) return;
    node.classList.toggle("collapsed");
    const key = node.dataset.key;
    node.classList.contains("collapsed") ? collapsed.add(key) : collapsed.delete(key);
    store.set("mc.collapsed", [...collapsed]);
  });
  $("#expandAll").addEventListener("click", () => {
    collapsed.clear(); store.set("mc.collapsed", []);
    document.querySelectorAll(".node.collapsed").forEach((n) => n.classList.remove("collapsed"));
  });
  $("#collapseAll").addEventListener("click", () => {
    document.querySelectorAll(".node").forEach((n) => {
      if (n.querySelector(":scope > .children > .node")) { n.classList.add("collapsed"); collapsed.add(n.dataset.key); }
    });
    store.set("mc.collapsed", [...collapsed]);
  });
  function syncSort() {
    document.querySelectorAll("#sort button").forEach((b) => b.classList.toggle("on", b.dataset.sort === sortMode));
  }
  $("#sort").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sort]");
    if (!b) return;
    sortMode = b.dataset.sort; store.set("mc.sort", sortMode); syncSort();
    if (last) renderTree();
  });
  syncSort();
  $("#resetOverrides").addEventListener("click", () => {
    overrides = { raw: {}, recipe: {} }; saveOverrides(); run();
  });

  // ---------- 입력창: 자동완성과 Enter ----------
  const suggest = $("#suggest");
  let sugg = [];
  function currentLine() {
    const pos = ta.selectionStart;
    const before = ta.value.slice(0, pos);
    return before.split("\n").length - 1;
  }
  function updateSuggest() {
    const li = currentLine();
    const line = ta.value.split("\n")[li] || "";
    const q = splitLine(line).name;
    sugg = q && !exact.has(norm(q)) ? candidates(q, 10) : [];
    suggest.innerHTML = sugg.map((id, i) =>
      `<button class="chip${i === 0 ? " first" : ""}" type="button" data-id="${id}">${icon(id)}${esc(name(id))}</button>`).join("");
  }
  function pick(id, li = currentLine()) {
    const end = replaceLine(li, id);
    ta.focus();
    ta.setSelectionRange(end, end);
    sugg = []; suggest.innerHTML = "";
  }
  suggest.addEventListener("mousedown", (e) => e.preventDefault());
  suggest.addEventListener("click", (e) => { const b = e.target.closest("[data-id]"); if (b) pick(b.dataset.id); });
  $("#errors").addEventListener("click", (e) => {
    const b = e.target.closest("[data-id]");
    if (b) { pick(b.dataset.id, Number(b.dataset.li)); run(); }
  });
  ta.addEventListener("input", () => { updateSuggest(); store.set("mc.input", ta.value); });
  ta.addEventListener("click", updateSuggest);
  let enterAfterCompose = false;
  ta.addEventListener("compositionend", () => {
    if (enterAfterCompose) { enterAfterCompose = false; setTimeout(run, 0); }
  });
  ta.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) { // 한글 입력 조합 중: 조합이 끝나면 계산
      if (e.key === "Enter" && !e.shiftKey) enterAfterCompose = true;
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); suggest.innerHTML = ""; sugg = []; run(); }
    else if (e.key === "Tab" && sugg.length) { e.preventDefault(); pick(sugg[0]); }
  });

  $("#ver").textContent = `Java Edition ${D.version} 기준`;
  ta.value = store.get("mc.input", "참나무 문 3\n참나무 다락문 3");
  run();
})();
