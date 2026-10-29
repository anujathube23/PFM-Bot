// Dashboard logic: fetch data, render it, and request AI insights asynchronously.
// All dynamic text goes through textContent to avoid HTML injection.
const $ = (id) => document.getElementById(id);
const state = { userId: null, user: null, kind: "expenses" };

// Form definitions per record type: [name, label, input type, extra attrs]
const FORMS = {
  expenses: { label: "Expense", fields: [["category", "Category (e.g. Rent)", "text"], ["amount", "Amount", "number"], ["description", "Note", "text"], ["date", "Date", "date"]], check: ["is_essential", "Essential"] },
  incomes: { label: "Income", fields: [["source", "Source (employer / client)", "text"], ["amount", "Amount", "number"], ["date", "Date", "date"]] },
  goals: { label: "Savings goal", fields: [["name", "Goal name", "text"], ["target_amount", "Target", "number"], ["saved_amount", "Saved so far", "number"], ["deadline", "Deadline", "date"]] },
  budgets: { label: "Category limit", fields: [["category", "Category", "text"], ["monthly_limit", "Monthly limit", "number"]] },
};

const money = (n) => new Intl.NumberFormat(undefined, { style: "currency", currency: state.user?.currency || "INR", maximumFractionDigits: 0 }).format(n || 0);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };

async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function loadUsers(selectId) {
  const users = await api("/api/users");
  const sel = $("userSelect");
  sel.replaceChildren(...users.map((u) => { const o = el("option", `${u.name} (${u.persona})`); o.value = u.id; return o; }));
  if (users.length) { sel.value = selectId || users[0].id; state.userId = +sel.value; state.user = users.find((u) => u.id === state.userId); await refresh(); }
}

async function refresh() {
  if (!state.userId) return;
  const s = await api(`/api/users/${state.userId}/summary?month=${$("month").value}`);
  renderStats(s); renderCategories(s);
  $("insights").replaceChildren(el("p", "Run the analysis to get a budget plan and saving suggestions.", "msg"));
}

function renderStats(s) {
  const rate = s.savings_rate_pct === null ? "n/a" : `${s.savings_rate_pct}%`;
  const items = [["Income", money(s.total_income)], ["Expenses", money(s.total_expenses)],
    ["Surplus", money(s.surplus), s.surplus >= 0 ? "pos" : "neg"], ["Savings rate", rate]];
  $("stats").replaceChildren(...items.map(([label, val, cls]) => { const d = el("div", undefined, "stat"); d.append(el("span", label), el("b", val, cls)); return d; }));
}

function renderCategories(s) {
  const wrap = $("categories");
  const cats = Object.entries(s.category_breakdown);
  if (!cats.length) { wrap.replaceChildren(el("p", "No expenses this month yet.", "msg")); return; }
  const max = Math.max(...cats.map(([, v]) => v));
  const over = Object.fromEntries(s.budget_overruns.map((o) => [o.category, o]));
  wrap.replaceChildren(...cats.map(([name, val]) => {
    const row = el("div", undefined, "bar"), track = el("div", undefined, "track"), fill = el("div", undefined, "fill" + (over[name] ? " over" : ""));
    fill.style.width = `${(val / max) * 100}%`; track.append(fill);
    row.append(el("span", name), track, el("span", over[name] ? `${money(val)} ⚠` : money(val)));
    if (over[name]) row.title = `Over limit by ${money(over[name].over_by)}`;
    return row;
  }));
}

function renderForm() {
  const f = FORMS[state.kind], form = $("recordForm");
  form.replaceChildren(...f.fields.map(([name, ph, type]) => {
    const i = el("input"); i.name = name; i.type = type; i.placeholder = ph; i.setAttribute("aria-label", ph);
    if (type === "number") { i.step = "0.01"; i.min = "0"; }
    if (type === "date" && name === "date") i.valueAsDate = new Date();
    if (["category", "source", "name"].includes(name)) i.required = true;
    if (["amount", "target_amount", "monthly_limit"].includes(name)) i.required = true;
    return i;
  }));
  if (f.check) { const l = el("label", undefined, "check wide"), c = el("input"); c.type = "checkbox"; c.name = f.check[0]; c.checked = true; l.append(c, f.check[1]); form.append(l); }
  const btn = el("button", `Save ${f.label.toLowerCase()}`, "wide"); btn.type = "submit"; form.append(btn);
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.kind === state.kind));
}

$("recordForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {};
  new FormData(e.target).forEach((v, k) => { if (v !== "") body[k] = v; });
  const chk = e.target.querySelector("input[type=checkbox]"); if (chk) body[chk.name] = chk.checked;
  try {
    await api(`/api/users/${state.userId}/${state.kind}`, { method: "POST", body: JSON.stringify(body) });
    $("formMsg").className = "msg"; $("formMsg").textContent = `${FORMS[state.kind].label} saved.`;
    renderForm(); await refresh();
  } catch (err) { $("formMsg").className = "err"; $("formMsg").textContent = err.message; }
});

$("analyzeBtn").addEventListener("click", async () => {
  const btn = $("analyzeBtn"), box = $("insights");
  if (!state.userId) return;
  btn.disabled = true; btn.textContent = "Analyzing…"; box.replaceChildren(el("p", "Asking the advisor…", "msg"));
  try {
    const r = await api(`/api/analyze/${state.userId}?month=${$("month").value}`);
    const list = el("ul"); r.saving_suggestions.forEach((t) => list.append(el("li", t)));
    box.replaceChildren(el("h3", "Monthly summary"), el("p", r.monthly_summary), el("h3", "Budget plan"), el("p", r.budget_plan), el("h3", "Saving suggestions"), list);
  } catch (err) { box.replaceChildren(el("p", err.message, "err")); }
  finally { btn.disabled = false; btn.textContent = "Analyze my month"; }
});

$("newUserBtn").addEventListener("click", async () => {
  const name = prompt("Profile name?"); if (!name) return;
  const persona = prompt("Type: salaried, student, freelancer, or household", "salaried");
  try { const u = await api("/api/users", { method: "POST", body: JSON.stringify({ name, persona }) }); await loadUsers(u.id); }
  catch (err) { alert(err.message); }
});

$("userSelect").addEventListener("change", (e) => { state.userId = +e.target.value; loadUsers(state.userId); });
$("month").addEventListener("change", refresh);

// Init
$("month").value = new Date().toISOString().slice(0, 7);
$("tabs").replaceChildren(...Object.entries(FORMS).map(([k, f]) => { const b = el("button", f.label); b.type = "button"; b.dataset.kind = k; b.setAttribute("role", "tab"); b.onclick = () => { state.kind = k; $("formMsg").textContent = ""; renderForm(); }; return b; }));
renderForm(); loadUsers();
