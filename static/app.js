const fields = ["os", "contanti", "bonifici", "paypal", "altri"];
const labels = {
  os: "OS",
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
const template = document.querySelector("#entryTemplate");
const grandTotalEl = document.querySelector("#grandTotal");
const todayTotalEl = document.querySelector("#todayTotal");

let entries = [];
let password = localStorage.getItem("incassiPassword") || "";

const eur = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
});

function today() {
  return new Date().toISOString().slice(0, 10);
}

function readableDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function numberValue(id) {
  return Number.parseFloat(document.querySelector(`#${id}`).value.replace(",", ".")) || 0;
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

function resetForm() {
  form.reset();
  document.querySelector("#entryId").value = "";
  document.querySelector("#data").value = today();
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

  entries = await response.json();
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
    payload[field] = numberValue(field);
  });

  await fetch("/api/incassi", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });

  resetForm();
  await loadEntries();
}

async function deleteEntry(id) {
  await fetch(`/api/incassi/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  await loadEntries();
}

function editEntry(entry) {
  document.querySelector("#entryId").value = entry.id;
  document.querySelector("#data").value = entry.data;
  document.querySelector("#note").value = entry.note || "";
  fields.forEach((field) => {
    document.querySelector(`#${field}`).value = entry[field] || "";
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function render() {
  const grandTotal = entries.reduce((sum, entry) => sum + entry.totale, 0);
  const todayEntry = entries.find((entry) => entry.data === today());

  grandTotalEl.textContent = eur.format(grandTotal);
  todayTotalEl.textContent = eur.format(todayEntry?.totale || 0);
  entriesEl.innerHTML = "";

  if (entries.length === 0) {
    entriesEl.innerHTML = '<div class="empty">Nessun incasso inserito.</div>';
    return;
  }

  entries.forEach((entry) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector("h3").textContent = readableDate(entry.data);
    node.querySelector("p").textContent = entry.note || "Nessuna nota";
    node.querySelector("strong").textContent = eur.format(entry.totale);

    const methods = node.querySelector(".methods");
    fields.forEach((field) => {
      const item = document.createElement("div");
      item.innerHTML = `<dt>${labels[field]}</dt><dd>${eur.format(entry[field] || 0)}</dd>`;
      methods.appendChild(item);
    });

    node.querySelector(".edit").addEventListener("click", () => editEntry(entry));
    node.querySelector(".delete").addEventListener("click", () => deleteEntry(entry.id));
    entriesEl.appendChild(node);
  });
}

form.addEventListener("submit", saveEntry);
loginForm.addEventListener("submit", login);
document.querySelector("#resetButton").addEventListener("click", resetForm);
document.querySelector("#refreshButton").addEventListener("click", loadEntries);
document.querySelector("#logoutButton").addEventListener("click", logout);

resetForm();
loadEntries();
