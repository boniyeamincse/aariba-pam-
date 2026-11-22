const form = document.querySelector("#sign-in-form");
const signIn = document.querySelector("#sign-in");
const submit = document.querySelector("#submit");
const signOut = document.querySelector("#sign-out");
const refresh = document.querySelector("#refresh");
const catalog = document.querySelector("#catalog");
const identity = document.querySelector("#identity");
const assets = document.querySelector("#assets");
const status = document.querySelector("#status");

let accessToken = "";
let pendingCatalog = null;

class ApiError extends Error {
  constructor(statusCode) {
    super("Ariba PAM request failed");
    this.statusCode = statusCode;
  }
}

async function api(path, options = {}) {
  const { body, token, signal } = options;
  const headers = { Accept: "application/json" };

  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = "Bearer " + token;

  const response = await fetch("/api/v1" + path, {
    method: body ? "POST" : "GET",
    headers,
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!response.ok) throw new ApiError(response.status);
  return response.json();
}

function message(text, error = false) {
  status.textContent = text;
  status.dataset.error = String(error);
}

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function renderAssets(records) {
  assets.replaceChildren();
  for (const asset of records) {
    const card = document.createElement("li");
    card.className = "asset";
    card.append(
      element("h3", asset.name),
      element("p", [asset.environment, asset.team].filter(Boolean).join(" · ")),
    );
    if (asset.accounts.length) {
      const accounts = document.createElement("ul");
      accounts.setAttribute("aria-label", "Target accounts");
      for (const account of asset.accounts) {
        const label = account.username + (account.requires_ticket ? " · Ticket required" : "");
        accounts.append(element("li", label));
      }
      card.append(accounts);
    } else {
      card.append(element("p", "No active target accounts."));
    }
    assets.append(card);
  }
}

async function loadCatalog() {
  const request = new AbortController();
  pendingCatalog = request;
  refresh.disabled = true;
  catalog.setAttribute("aria-busy", "true");
  assets.replaceChildren();
  message("Loading permitted assets…");

  try {
    const records = await api("/assets", { token: accessToken, signal: request.signal });
    if (pendingCatalog !== request) return;
    renderAssets(records);
    if (records.length === 0) {
      message("No assets are assigned to your identity.");
    } else {
      message(records.length === 1 ? "1 permitted asset." : records.length + " permitted assets.");
    }
  } catch (error) {
    if (pendingCatalog !== request) return;
    if (error.statusCode === 401) {
      endSession("Your lab session expired. Sign in again.", true);
    } else if (error.statusCode === 403) {
      message("Your identity does not have permission to browse the catalog.", true);
    } else {
      message("The catalog is unavailable. Use Refresh catalog to retry.", true);
    }
  } finally {
    if (pendingCatalog === request) {
      pendingCatalog = null;
      catalog.removeAttribute("aria-busy");
      refresh.disabled = false;
    }
  }
}

function endSession(text, error = false) {
  pendingCatalog?.abort();
  pendingCatalog = null;
  accessToken = "";
  identity.textContent = "";
  assets.replaceChildren();
  catalog.removeAttribute("aria-busy");
  catalog.hidden = true;
  signOut.hidden = true;
  signIn.hidden = false;
  message(text, error);
  form.elements.email.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  submit.disabled = true;
  message("Signing in…");

  try {
    const session = await api("/auth/login", {
      body: {
        email: form.elements.email.value.trim(),
        idp_subject: form.elements.subject.value.trim(),
      },
    });
    const me = await api("/me", { token: session.access_token });
    accessToken = session.access_token;
    identity.textContent = me.full_name || me.email;
    form.reset();
    signIn.hidden = true;
    catalog.hidden = false;
    signOut.hidden = false;
    signOut.focus();
    await loadCatalog();
  } catch (error) {
    message(
      error.statusCode === 401 || error.statusCode === 403
        ? "Lab sign-in denied. Check the synthetic identity."
        : "Sign-in is unavailable. Try again.",
      true,
    );
  } finally {
    submit.disabled = false;
  }
});

refresh.addEventListener("click", loadCatalog);
signOut.addEventListener("click", () => endSession("Signed out."));
