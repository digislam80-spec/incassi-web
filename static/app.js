const fields = ["os", "contanti", "bonifici", "paypal", "altri"];
const labels = {
  os: "POS",
  contanti: "Contanti",
  bonifici: "Bonifici",
  paypal: "PayPal",
  altri: "Altri metodi",
};

const form = document.querySelector("#entryForm");
const loginView = document.querySelector("#loginView");
const loginForm = document.querySelector("#loginForm");
const loginError = document.querySelector("#loginError");
const entriesEl = document.querySelector("#entries");
const overviewMonth = document.querySelector("#overviewMonth");
const monthTotalEl = document.querySelector("#monthTotal");
const monthTrendEl = document.querySelector("#monthTrend");
const monthBreakdownEl = document.querySelector("#monthBreakdown");
const todayTotalEl = document.querySelector("#todayTotal");
const appError = document.querySelector("#appError");
const statsMode = document.querySelector("#statsMode");
const statsDay = document.querySelector("#statsDay");
const statsWeek = document.querySelector("#statsWeek");
const statsMonth = document.querySelector("#statsMonth");
const statsYear = document.querySelector("#statsYear");
const statsFrom = document.querySelector("#statsFrom");
const statsTo = document.querySelector("#statsTo");
const periodTotalEl = document.querySelector("#periodTotal");
const periodDaysEl = document.querySelector("#periodDays");
const periodAverageEl = document.querySelector("#periodAverage");
const methodStatsEl = document.querySelector("#methodStats");
const methodChart = document.querySelector("#methodChart");
const methodLegend = document.querySelector("#methodLegend");
const dailyChart = document.querySelector("#dailyChart");
const importFile = document.querySelector("#importFile");
const importButton = document.querySelector("#importButton");
const exportButton = document.querySelector("#exportButton");
const importResult = document.querySelector("#importResult");
const transferList = document.querySelector("#transferList");
const addTransferButton = document.querySelector("#addTransferButton");
const transferTotalEl = document.querySelector("#transferTotal");
const historyAddButton = document.querySelector("#historyAddButton");
const closeFormButton = document.querySelector("#closeFormButton");
const deleteCurrentButton = document.querySelector("#deleteCurrentButton");
const yesterdayButton = document.querySelector("#yesterdayButton");
const todayButton = document.querySelector("#todayButton");
const formTitle = document.querySelector("#formTitle");
const backButton = document.querySelector("#backButton");
const screenButtons = document.querySelectorAll("[data-screen-button]");
const screens = document.querySelectorAll("[data-screen]");

let entries = [];
let password = localStorage.getItem("incassiPassword") || "";
let currentScreen = "history";
let screenStack = ["history"];

const eur = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
});
const chartColors = ["#0f766e", "#2563eb", "#9333ea", "#c2410c", "#64748b"];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(value, days) {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function currentMonth() {
  return today().slice(0, 7);
}

function previousMonth(value) {
  const date = new Date(`${value || currentMonth()}-01T12:00:00`);
  date.setMonth(date.getMonth() - 1);
  return date.toISOString().slice(0, 7);
}

function currentWeek() {
  const date = new Date(`${today()}T12:00:00`);
  const day = date.getDay() || 7;
  date.setDate(date.getDate() + 4 - day);
  const yearStart = new Date(date.getFullYear(), 0, 1);
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return `${date.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function weekRange(value) {
  const [yearRaw, weekRaw] = String(value || currentWeek()).split("-W");
  const year = Number(yearRaw);
  const week = Number(weekRaw);
  const jan4 = new Date(year, 0, 4);
  const jan4Day = jan4.getDay() || 7;
  const monday = new Date(jan4);
  monday.setDate(jan4.getDate() - jan4Day + 1 + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return {
    from: monday.toISOString().slice(0, 10),
    to: sunday.toISOString().slice(0, 10),
  };
}

function readableDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function readableMonth(value) {
  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}-01T12:00:00`));
}

function numberValue(id) {
  return Number.parseFloat(document.querySelector(`#${id}`).value.replace(",", ".")) || 0;
}

function parseNumber(value) {
  return Number.parseFloat(String(value || "0").replace(",", ".")) || 0;
}

function sumEntries(items) {
  return items.reduce((sum, entry) => sum + Number(entry.totale || 0), 0);
}

function authHeaders(extra = {}) {
  return {
    ...extra,
    "X-App-Password": password,
  };
}

function showLogin(message = "") {
  loginView.hidden = false;
  loginError.textContent = message;
}

function hideLogin() {
  loginView.hidden = true;
  loginError.textContent = "";
}

function showAppError(message = "") {
  appError.textContent = message;
  appError.hidden = !message;
}

async function login(event) {
  event.preventDefault();
  const typedPassword = document.querySelector("#password").value;
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: typedPassword }),
  });

  if (!response.ok) {
    showLogin("Password non corretta.");
    return;
  }

  password = typedPassword;
  localStorage.setItem("incassiPassword", password);
  hideLogin();
  await loadEntries();
}

function logout() {
  password = "";
  localStorage.removeItem("incassiPassword");
  entries = [];
  render();
  showLogin();
}

function showScreen(name, push = true, options = {}) {
  currentScreen = name;
  screens.forEach((screen) => {
    screen.hidden = screen.dataset.screen !== name;
  });
  screenButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.screenButton === name);
  });

  if (push && screenStack[screenStack.length - 1] !== name) {
    screenStack.push(name);
  }

  backButton.hidden = screenStack.length <= 1;
  window.scrollTo({ top: 0, behavior: options.instant ? "auto" : "smooth" });
}

function goBack() {
  if (screenStack.length <= 1) return;
  screenStack.pop();
  showScreen(screenStack[screenStack.length - 1], false);
}

function openForm(entry = null) {
  resetForm(entry);
  showScreen("form", true, { instant: true });
  focusFormStart();
}

function closeForm() {
  resetForm();
  screenStack = ["history"];
  showScreen("history", false);
}

function resetForm(entry = null) {
  form.reset();
  document.querySelector("#entryId").value = entry?.id || "";
  document.querySelector("#data").value = entry?.data || today();
  document.querySelector("#note").value = entry?.note || "";
  formTitle.textContent = entry ? "Modifica incasso" : "Aggiungi nuovo incasso";
  deleteCurrentButton.hidden = !entry;

  fields.forEach((field) => {
    const input = document.querySelector(`#${field}`);
    if (input) input.value = entry?.[field] || "";
  });

  transferList.innerHTML = "";
  const details = entry?.bonifici_dettagli?.length
    ? entry.bonifici_dettagli
    : [{ nome: "", importo: entry?.bonifici || "" }];
  details.forEach((item) => addTransferRow(item));
  updateTransferTotal();
}

function focusFormStart() {
  requestAnimationFrame(() => {
    form.scrollIntoView({ block: "start", behavior: "auto" });
    document.querySelector("#data").focus({ preventScroll: true });
  });
}

function resetStatsDefaults() {
  overviewMonth.value = currentMonth();
  statsDay.value = today();
  statsWeek.value = currentWeek();
  statsMonth.value = currentMonth();
  statsYear.value = new Date().getFullYear();
  statsFrom.value = today();
  statsTo.value = today();
}

async function loadEntries() {
  if (!password) {
    showLogin();
    return;
  }

  const response = await fetch("/api/incassi", {
    headers: authHeaders(),
  });

  if (response.status === 401) {
    logout();
    showLogin("Inserisci la password.");
    return;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAppError(error.message || "Errore nel caricamento degli incassi.");
    return;
  }

  entries = await response.json();
  showAppError();
  hideLogin();
  render();
}

async function saveEntry(event) {
  event.preventDefault();

  const payload = {
    id: document.querySelector("#entryId").value,
    data: document.querySelector("#data").value,
    note: document.querySelector("#note").value,
  };

  fields.forEach((field) => {
    payload[field] = field === "bonifici" ? transferTotal() : numberValue(field);
  });
  payload.bonifici_dettagli = transferRows();

  const response = await fetch("/api/incassi", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAppError(error.message || "Errore nel salvataggio.");
    return;
  }

  resetForm();
  screenStack = ["history"];
  showScreen("history", false);
  await loadEntries();
  screenStack = ["history"];
  showScreen("history", false);
}

async function deleteEntry(id) {
  if (!id) return;

  const response = await fetch(`/api/incassi/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showAppError(error.message || "Errore nell'eliminazione.");
    return;
  }

  await loadEntries();
  resetForm();
  screenStack = ["history"];
  showScreen("history", false);
}

async function importJson() {
  const file = importFile.files?.[0];
  if (!file) {
    importResult.textContent = "Seleziona un file JSON.";
    return;
  }

  let payload;
  try {
    payload = JSON.parse(await file.text());
  } catch {
    importResult.textContent = "JSON non valido.";
    return;
  }

  const response = await fetch("/api/import", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });

  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    importResult.textContent = result.message || "Import non riuscito.";
    return;
  }

  importResult.textContent = `Importati ${result.imported} incassi. Errori: ${result.errors?.length || 0}.`;
  importFile.value = "";
  await loadEntries();
}

function exportBackup() {
  const backup = {
    exported_at: new Date().toISOString(),
    incassi: entries,
  };
  const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `incassi-backup-${today()}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  importResult.textContent = `Backup creato: ${entries.length} incassi.`;
}

function addTransferRow(detail = {}) {
  const row = document.createElement("div");
  row.className = "transfer-row";
  row.innerHTML = `
    <input class="transfer-name" type="text" placeholder="Nome" value="${escapeHtml(detail.nome || "")}">
    <input class="transfer-amount" type="text" inputmode="decimal" placeholder="0,00" value="${detail.importo || ""}">
    <button class="icon-button transfer-remove" type="button" aria-label="Rimuovi bonifico">×</button>
  `;
  row.querySelector(".transfer-amount").addEventListener("input", updateTransferTotal);
  row.querySelector(".transfer-remove").addEventListener("click", () => {
    row.remove();
    if (!transferList.children.length) addTransferRow();
    updateTransferTotal();
  });
  transferList.appendChild(row);
}

function transferRows() {
  return [...transferList.querySelectorAll(".transfer-row")]
    .map((row) => ({
      nome: row.querySelector(".transfer-name").value.trim(),
      importo: parseNumber(row.querySelector(".transfer-amount").value),
    }))
    .filter((item) => item.nome || item.importo);
}

function transferTotal() {
  return transferRows().reduce((sum, item) => sum + item.importo, 0);
}

function updateTransferTotal() {
  transferTotalEl.textContent = eur.format(transferTotal());
}

function render() {
  const todayEntry = entries.find((entry) => entry.data === today());

  todayTotalEl.textContent = eur.format(todayEntry?.totale || 0);
  entriesEl.innerHTML = "";
  renderOverview();
  renderStats();

  if (entries.length === 0) {
    entriesEl.innerHTML = '<div class="empty">Nessun incasso inserito.</div>';
    return;
  }

  renderHistory();
}

function renderOverview() {
  const selectedMonth = overviewMonth.value || currentMonth();
  const previous = previousMonth(selectedMonth);
  const monthEntries = entries.filter((entry) => entry.data?.startsWith(selectedMonth));
  const previousEntries = entries.filter((entry) => entry.data?.startsWith(previous));
  const monthTotal = sumEntries(monthEntries);
  const previousTotal = sumEntries(previousEntries);
  const diff = monthTotal - previousTotal;
  const totals = methodTotals(monthEntries);

  monthTotalEl.textContent = eur.format(monthTotal);
  monthTrendEl.textContent = `${readableMonth(previous)}: ${eur.format(previousTotal)} (${diff >= 0 ? "+" : ""}${eur.format(diff)})`;
  monthBreakdownEl.innerHTML = fields
    .map((field, index) => `
      <div style="border-left-color:${chartColors[index]}">
        <span>${labels[field]}</span>
        <strong>${eur.format(totals[field])}</strong>
      </div>
    `)
    .join("");
}

function renderHistory() {
  const groups = new Map();
  [...entries]
    .sort((a, b) => b.data.localeCompare(a.data))
    .forEach((entry) => {
      const key = entry.data.slice(0, 7);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(entry);
    });

  groups.forEach((items, month) => {
    const section = document.createElement("section");
    section.className = "month-group";
    const monthTotals = methodTotals(items);

    section.innerHTML = `
      <div class="month-head">
        <div>
          <h3>${readableMonth(month)}</h3>
          <p>${items.length} giorni inseriti</p>
        </div>
        <strong>${eur.format(sumEntries(items))}</strong>
      </div>
      <div class="month-totals">
        ${fields.map((field) => `<span>${labels[field]} <strong>${eur.format(monthTotals[field])}</strong></span>`).join("")}
      </div>
      <div class="history-list" aria-label="Incassi ${readableMonth(month)}"></div>
    `;

    const list = section.querySelector(".history-list");
    items.forEach((entry) => {
      const row = document.createElement("button");
      row.className = "history-row";
      row.type = "button";
      row.innerHTML = `
        <span class="row-main">
          <span>
            <span>${readableDate(entry.data)}</span>
          </span>
          <strong class="row-total">${eur.format(entry.totale || 0)}</strong>
        </span>
        <span class="row-body">
          <span class="row-methods">
            ${fields.map((field) => `<span><small>${labels[field]}</small>${eur.format(entry[field] || 0)}</span>`).join("")}
          </span>
          <span class="row-action">
            <em aria-label="Osserva e modifica">✎</em>
          </span>
        </span>
      `;
      row.addEventListener("click", () => openForm(entry));
      list.appendChild(row);
    });

    entriesEl.appendChild(section);
  });
}

function methodTotals(items) {
  return fields.reduce((totals, field) => {
    totals[field] = items.reduce((sum, entry) => sum + Number(entry[field] || 0), 0);
    return totals;
  }, {});
}

function selectedPeriodEntries() {
  const mode = statsMode.value;

  if (mode === "day") {
    const day = statsDay.value || today();
    return entries.filter((entry) => entry.data === day);
  }

  if (mode === "week") {
    const range = weekRange(statsWeek.value);
    return entries.filter((entry) => entry.data >= range.from && entry.data <= range.to);
  }

  if (mode === "month") {
    const month = statsMonth.value || currentMonth();
    return entries.filter((entry) => entry.data?.startsWith(month));
  }

  if (mode === "year") {
    const year = String(statsYear.value || new Date().getFullYear());
    return entries.filter((entry) => entry.data?.startsWith(year));
  }

  const from = statsFrom.value || "0000-01-01";
  const to = statsTo.value || "9999-12-31";
  return entries.filter((entry) => entry.data >= from && entry.data <= to);
}

function updateFilterVisibility() {
  const mode = statsMode.value;
  document.querySelector("#dayFilter").hidden = mode !== "day";
  document.querySelector("#weekFilter").hidden = mode !== "week";
  document.querySelector("#monthFilter").hidden = mode !== "month";
  document.querySelector("#yearFilter").hidden = mode !== "year";
  document.querySelector("#fromFilter").hidden = mode !== "range";
  document.querySelector("#toFilter").hidden = mode !== "range";
}

function renderStats() {
  updateFilterVisibility();

  const periodEntries = selectedPeriodEntries();
  const periodTotal = sumEntries(periodEntries);
  const periodDays = periodEntries.length;
  const totals = methodTotals(periodEntries);

  periodTotalEl.textContent = eur.format(periodTotal);
  periodDaysEl.textContent = String(periodDays);
  periodAverageEl.textContent = eur.format(periodDays ? periodTotal / periodDays : 0);
  methodStatsEl.innerHTML = "";
  methodLegend.innerHTML = "";

  fields.forEach((field, index) => {
    const row = document.createElement("div");
    row.style.borderLeft = `4px solid ${chartColors[index]}`;
    row.innerHTML = `<dt>${labels[field]}</dt><dd>${eur.format(totals[field])}</dd>`;
    methodStatsEl.appendChild(row);

    const legend = document.createElement("span");
    legend.innerHTML = `<i style="background:${chartColors[index]}"></i>${labels[field]}`;
    methodLegend.appendChild(legend);
  });

  renderMethodChart(periodEntries);
  renderDailyChart(periodEntries);
}

function renderMethodChart(periodEntries) {
  if (!methodChart) return;

  const values = fields.map((field) => periodEntries.reduce((sum, entry) => sum + Number(entry[field] || 0), 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  const context = methodChart.getContext("2d");
  const width = methodChart.width;
  const height = methodChart.height;
  const radius = Math.min(width, height) / 2 - 22;
  let start = -Math.PI / 2;

  context.clearRect(0, 0, width, height);
  context.font = "13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.textBaseline = "middle";

  if (!total) {
    drawEmptyChart(context, width, height);
    return;
  }

  values.forEach((value, index) => {
    const angle = (value / total) * Math.PI * 2;
    context.beginPath();
    context.moveTo(width / 2, height / 2);
    context.arc(width / 2, height / 2, radius, start, start + angle);
    context.closePath();
    context.fillStyle = chartColors[index];
    context.fill();
    start += angle;
  });

  context.beginPath();
  context.arc(width / 2, height / 2, radius * 0.55, 0, Math.PI * 2);
  context.fillStyle = "#ffffff";
  context.fill();
  context.fillStyle = "#18211f";
  context.textAlign = "center";
  context.font = "700 16px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.fillText(eur.format(total), width / 2, height / 2);
}

function renderDailyChart(periodEntries) {
  if (!dailyChart) return;

  const byDate = [...periodEntries]
    .sort((a, b) => a.data.localeCompare(b.data))
    .map((entry) => ({ label: entry.data.slice(5), value: Number(entry.totale || 0) }));
  const context = dailyChart.getContext("2d");
  const width = dailyChart.width;
  const height = dailyChart.height;
  const max = Math.max(...byDate.map((item) => item.value), 0);

  context.clearRect(0, 0, width, height);
  context.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";

  if (!max) {
    drawEmptyChart(context, width, height);
    return;
  }

  const padding = 26;
  const gap = 5;
  const barWidth = Math.max(8, (width - padding * 2 - gap * (byDate.length - 1)) / Math.max(byDate.length, 1));

  byDate.forEach((item, index) => {
    const barHeight = ((height - padding * 2) * item.value) / max;
    const x = padding + index * (barWidth + gap);
    const y = height - padding - barHeight;
    context.fillStyle = "#0f766e";
    context.fillRect(x, y, barWidth, barHeight);
    if (barWidth > 18) {
      context.fillStyle = "#64706d";
      context.textAlign = "center";
      context.fillText(item.label, x + barWidth / 2, height - 8);
    }
  });
}

function drawEmptyChart(context, width, height) {
  context.fillStyle = "#64706d";
  context.textAlign = "center";
  context.font = "13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  context.fillText("Nessun dato nel periodo", width / 2, height / 2);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

form.addEventListener("submit", saveEntry);
loginForm.addEventListener("submit", login);
historyAddButton.addEventListener("click", () => openForm());
closeFormButton.addEventListener("click", closeForm);
backButton.addEventListener("click", goBack);
screenButtons.forEach((button) => {
  button.addEventListener("click", () => showScreen(button.dataset.screenButton));
});
document.querySelector("#resetButton").addEventListener("click", () => resetForm());
document.querySelector("#refreshButton").addEventListener("click", loadEntries);
document.querySelector("#logoutButton").addEventListener("click", logout);
addTransferButton.addEventListener("click", () => addTransferRow());
deleteCurrentButton.addEventListener("click", () => deleteEntry(document.querySelector("#entryId").value));
yesterdayButton.addEventListener("click", () => {
  document.querySelector("#data").value = addDays(today(), -1);
});
todayButton.addEventListener("click", () => {
  document.querySelector("#data").value = today();
});
importButton.addEventListener("click", importJson);
exportButton.addEventListener("click", exportBackup);
overviewMonth.addEventListener("input", renderOverview);
overviewMonth.addEventListener("change", renderOverview);
[statsMode, statsDay, statsWeek, statsMonth, statsYear, statsFrom, statsTo].forEach((input) => {
  input.addEventListener("input", renderStats);
  input.addEventListener("change", renderStats);
});

resetStatsDefaults();
resetForm();
showScreen("history", false);
loadEntries();
