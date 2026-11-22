const form = document.querySelector("#sign-in-form");
const signIn = document.querySelector("#sign-in");
const submit = document.querySelector("#submit");
const signOut = document.querySelector("#sign-out");
const portalWorkspace = document.querySelector("#portal-workspace");

// Navigation Tabs
const tabCatalog = document.querySelector("#tab-catalog");
const tabRequests = document.querySelector("#tab-requests");
const tabApprovals = document.querySelector("#tab-approvals");
const approvalsCount = document.querySelector("#approvals-count");

const catalogPanel = document.querySelector("#catalog");
const requestsPanel = document.querySelector("#requests-panel");
const approvalsPanel = document.querySelector("#approvals-panel");

const refreshCatalogBtn = document.querySelector("#refresh");
const refreshRequestsBtn = document.querySelector("#refresh-requests");
const refreshApprovalsBtn = document.querySelector("#refresh-approvals");

const identity = document.querySelector("#identity");
const assetsList = document.querySelector("#assets");
const requestsList = document.querySelector("#requests-list");
const approvalsList = document.querySelector("#approvals-list");
const staleAlert = document.querySelector("#stale-alert");
const reloadStaleBtn = document.querySelector("#reload-stale-btn");
const status = document.querySelector("#status");

// Dialogs
const requestDialog = document.querySelector("#request-dialog");
const requestForm = document.querySelector("#request-form");
const reqAssetId = document.querySelector("#req-asset-id");
const reqAccountId = document.querySelector("#req-account-id");
const reqAssetName = document.querySelector("#req-asset-name");
const reqAccountName = document.querySelector("#req-account-name");
const reqStart = document.querySelector("#req-start");
const reqEnd = document.querySelector("#req-end");
const reqJustification = document.querySelector("#req-justification");
const reqTicket = document.querySelector("#req-ticket");
const ticketReqLabel = document.querySelector("#ticket-req-label");
const reqCancelBtn = document.querySelector("#req-cancel-btn");

const reviseDialog = document.querySelector("#revise-dialog");
const reviseForm = document.querySelector("#revise-form");
const reviseRequestId = document.querySelector("#revise-request-id");
const reviseExpectedId = document.querySelector("#revise-expected-id");
const reviseStart = document.querySelector("#revise-start");
const reviseEnd = document.querySelector("#revise-end");
const reviseJustification = document.querySelector("#revise-justification");
const reviseTicket = document.querySelector("#revise-ticket");
const reviseCancelBtn = document.querySelector("#revise-cancel-btn");

const launchDialog = document.querySelector("#launch-dialog");
const launchCommand = document.querySelector("#launch-command");
const launchExpiry = document.querySelector("#launch-expiry");
const launchCloseBtn = document.querySelector("#launch-close-btn");

let accessToken = "";
let currentUser = null;
let currentTab = "catalog";
let pendingCatalog = null;
let pendingRequests = null;
let pendingApprovals = null;

class ApiError extends Error {
  constructor(statusCode, errorData = {}) {
    super(errorData.message || "Ariba PAM request failed");
    this.statusCode = statusCode;
    this.code = errorData.code;
    this.details = errorData;
  }
}

function randomId(prefix = "idm") {
  return prefix + "_" + Math.random().toString(36).substring(2, 12);
}

async function api(path, options = {}) {
  const { body, token, signal, headers: customHeaders, method } = options;
  const headers = { Accept: "application/json", ...customHeaders };

  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = "Bearer " + token;

  const httpMethod = method || (body ? "POST" : "GET");
  const response = await fetch("/api/v1" + path, {
    method: httpMethod,
    headers,
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  let data = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, data || {});
  }
  return data;
}

function message(text, error = false) {
  status.textContent = text;
  status.dataset.error = String(error);
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function toLocalDatetimeString(date) {
  const pad = (n) => String(n).padStart(2, "0");
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Tab Switching
function switchTab(tab) {
  currentTab = tab;
  tabCatalog.classList.toggle("active", tab === "catalog");
  tabCatalog.setAttribute("aria-selected", tab === "catalog");
  catalogPanel.hidden = tab !== "catalog";

  tabRequests.classList.toggle("active", tab === "requests");
  tabRequests.setAttribute("aria-selected", tab === "requests");
  requestsPanel.hidden = tab !== "requests";

  tabApprovals.classList.toggle("active", tab === "approvals");
  tabApprovals.setAttribute("aria-selected", tab === "approvals");
  approvalsPanel.hidden = tab !== "approvals";

  if (tab === "catalog") loadCatalog();
  if (tab === "requests") loadRequests();
  if (tab === "approvals") loadApprovals();
}

tabCatalog.addEventListener("click", () => switchTab("catalog"));
tabRequests.addEventListener("click", () => switchTab("requests"));
tabApprovals.addEventListener("click", () => switchTab("approvals"));

// 1. Asset Catalog Rendering
function renderAssets(records) {
  assetsList.replaceChildren();
  for (const asset of records) {
    const card = document.createElement("li");
    card.className = "asset";

    const top = document.createElement("div");
    top.append(
      element("h3", asset.name),
      element("p", [asset.environment, asset.team].filter(Boolean).join(" · ")),
    );
    card.append(top);

    if (asset.accounts.length) {
      const accountsUl = document.createElement("ul");
      accountsUl.setAttribute("aria-label", "Target accounts");
      for (const account of asset.accounts) {
        const item = document.createElement("li");
        item.className = "account-item";

        const label = account.username + (account.requires_ticket ? " · Ticket required" : "");
        const labelSpan = element("span", label);

        const reqBtn = element("button", "Request access", "secondary small-btn");
        reqBtn.type = "button";
        reqBtn.addEventListener("click", () => openRequestDialog(asset, account));

        item.append(labelSpan, reqBtn);
        accountsUl.append(item);
      }
      card.append(accountsUl);
    } else {
      card.append(element("p", "No active target accounts."));
    }
    assetsList.append(card);
  }
}

async function loadCatalog() {
  const request = new AbortController();
  pendingCatalog = request;
  refreshCatalogBtn.disabled = true;
  catalogPanel.setAttribute("aria-busy", "true");
  assetsList.replaceChildren();
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
      catalogPanel.removeAttribute("aria-busy");
      refreshCatalogBtn.disabled = false;
    }
  }
}

// 2. Requester Flow: Submit and Revise Requests
function openRequestDialog(asset, account) {
  reqAssetId.value = asset.id;
  reqAccountId.value = account.id;
  reqAssetName.textContent = `${asset.name} (${asset.environment})`;
  reqAccountName.textContent = account.username;

  const now = new Date();
  const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
  reqStart.value = toLocalDatetimeString(now);
  reqEnd.value = toLocalDatetimeString(oneHourLater);
  reqJustification.value = "";
  reqTicket.value = "";
  if (account.requires_ticket) {
    reqTicket.required = true;
    ticketReqLabel.textContent = "(required)";
  } else {
    reqTicket.required = false;
    ticketReqLabel.textContent = "(optional)";
  }

  requestDialog.showModal();
}

reqCancelBtn.addEventListener("click", () => requestDialog.close());

requestForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const submitBtn = document.querySelector("#req-submit-btn");
  submitBtn.disabled = true;
  message("Submitting access request…");

  try {
    const startIso = new Date(reqStart.value).toISOString();
    const endIso = new Date(reqEnd.value).toISOString();

    const payload = {
      asset_id: reqAssetId.value,
      target_account_id: reqAccountId.value,
      requested_start_at: startIso,
      requested_end_at: endIso,
      justification: reqJustification.value.trim(),
      ticket_ref: reqTicket.value.trim() || undefined,
    };

    const idempotencyKey = randomId("idm_req");
    await api("/requests", {
      body: payload,
      token: accessToken,
      headers: { "X-Idempotency-Key": idempotencyKey },
    });

    requestDialog.close();
    message("Access request submitted successfully.");
    switchTab("requests");
  } catch (err) {
    message(err.message || "Failed to submit access request", true);
  } finally {
    submitBtn.disabled = false;
  }
});

// Render Requests List
function renderRequests(records) {
  requestsList.replaceChildren();
  if (records.length === 0) {
    requestsList.append(element("p", "No requests found for your identity."));
    return;
  }

  for (const req of records) {
    const card = document.createElement("li");
    card.className = "card";

    const header = document.createElement("div");
    header.className = "card-header";
    header.append(
      element("h3", `Request: ${req.id}`),
      element("span", req.status, `badge-status badge-${req.status}`),
    );

    const details = document.createElement("div");
    details.className = "card-details";
    details.append(
      element("div", `Asset: ${req.asset_name || "—"}`),
      element("div", `Account: ${req.target_account || "—"}`),
      element("div", `Current Revision: ${req.current_revision_id || "—"}`),
      element("div", `Created: ${new Date(req.created_at).toLocaleString()}`),
    );

    const actions = document.createElement("div");
    actions.className = "card-actions";

    if (req.status === "pending") {
      const cancelBtn = element("button", "Cancel request", "secondary small-btn");
      cancelBtn.addEventListener("click", () => cancelRequest(req.id));

      const reviseBtn = element("button", "Revise request", "secondary small-btn");
      reviseBtn.addEventListener("click", () => openReviseDialog(req));

      actions.append(cancelBtn, reviseBtn);
    } else if (req.status === "approved") {
      const launchBtn = element("button", "Launch SSH session", "small-btn");
      launchBtn.addEventListener("click", () => launchSession(req));
      actions.append(launchBtn);
    }

    card.append(header, details);
    if (actions.children.length > 0) card.append(actions);
    requestsList.append(card);
  }
}

async function loadRequests() {
  const request = new AbortController();
  pendingRequests = request;
  refreshRequestsBtn.disabled = true;
  requestsPanel.setAttribute("aria-busy", "true");
  message("Loading access requests…");

  try {
    const records = await api("/requests", { token: accessToken, signal: request.signal });
    if (pendingRequests !== request) return;
    renderRequests(records);
    message(records.length === 1 ? "1 access request." : `${records.length} access requests.`);
  } catch (error) {
    if (pendingRequests !== request) return;
    if (error.statusCode === 401) {
      endSession("Your lab session expired. Sign in again.", true);
    } else {
      message("Failed to load requests. Use Refresh requests to retry.", true);
    }
  } finally {
    if (pendingRequests === request) {
      pendingRequests = null;
      requestsPanel.removeAttribute("aria-busy");
      refreshRequestsBtn.disabled = false;
    }
  }
}

async function cancelRequest(requestId) {
  if (!confirm(`Are you sure you want to cancel request ${requestId}?`)) return;
  message(`Cancelling request ${requestId}…`);
  try {
    await api(`/requests/${requestId}/cancel`, {
      method: "POST",
      token: accessToken,
    });
    message("Request cancelled successfully.");
    loadRequests();
  } catch (err) {
    message(err.message || "Failed to cancel request", true);
  }
}

function openReviseDialog(req) {
  reviseRequestId.value = req.id;
  reviseExpectedId.value = req.current_revision_id;
  const now = new Date();
  const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
  reviseStart.value = toLocalDatetimeString(now);
  reviseEnd.value = toLocalDatetimeString(oneHourLater);
  reviseJustification.value = "";
  reviseTicket.value = "";
  reviseDialog.showModal();
}

reviseCancelBtn.addEventListener("click", () => reviseDialog.close());

reviseForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const submitBtn = document.querySelector("#revise-submit-btn");
  submitBtn.disabled = true;
  message("Submitting replacement revision…");

  try {
    const reqId = reviseRequestId.value;
    const expectedRevId = reviseExpectedId.value;
    const payload = {
      expected_revision_id: expectedRevId,
      requested_start_at: new Date(reviseStart.value).toISOString(),
      requested_end_at: new Date(reviseEnd.value).toISOString(),
      justification: reviseJustification.value.trim(),
      ticket_ref: reviseTicket.value.trim() || undefined,
    };

    await api(`/requests/${reqId}/revisions`, {
      body: payload,
      token: accessToken,
      headers: { "X-Idempotency-Key": randomId("idm_rev") },
    });

    reviseDialog.close();
    message("Replacement revision submitted successfully.");
    loadRequests();
  } catch (err) {
    message(err.message || "Failed to submit revision replacement", true);
  } finally {
    submitBtn.disabled = false;
  }
});

async function launchSession(req) {
  message("Retrieving grant and issuing launch authorization…");
  try {
    // 1. Get full request to retrieve grant reference
    const fullReq = await api(`/requests/${req.id}`, { token: accessToken });
    const grantId = fullReq.grant_id;
    if (!grantId) {
      throw new Error("No active grant found for this approved request.");
    }

    // 2. Request launch token
    const launchData = await api(`/grants/${grantId}/launches`, {
      method: "POST",
      token: accessToken,
    });

    launchCommand.textContent = `ssh -p 2222 ${launchData.launch_token}@localhost`;
    launchExpiry.textContent = `Expires at: ${new Date(launchData.expires_at).toLocaleTimeString()}`;
    launchDialog.showModal();
    message("Launch capability issued.");
  } catch (err) {
    message(err.message || "Failed to launch session", true);
  }
}

launchCloseBtn.addEventListener("click", () => launchDialog.close());

// 3. Approver Flow: Review Queue and Decisions
function renderApprovals(records) {
  approvalsList.replaceChildren();
  approvalsCount.textContent = records.length;
  approvalsCount.hidden = records.length === 0;

  if (records.length === 0) {
    approvalsList.append(element("p", "No pending approval steps assigned to your identity."));
    return;
  }

  for (const step of records) {
    const card = document.createElement("li");
    card.className = "card";

    const header = document.createElement("div");
    header.className = "card-header";
    header.append(
      element("h3", `Step: ${step.step_id}`),
      element("span", "PENDING", "badge-status badge-pending"),
    );

    const details = document.createElement("div");
    details.className = "card-details";
    details.append(
      element("div", `Request: ${step.request_id}`),
      element("div", `Revision: ${step.revision_id}`),
      element("div", `Target: ${step.asset_name} (${step.target_account})`),
      element("div", `Window: ${new Date(step.requested_start_at).toLocaleTimeString()} - ${new Date(step.requested_end_at).toLocaleTimeString()}`),
      element("div", `Justification: "${step.justification}"`),
    );

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const approveBtn = element("button", "Approve", "small-btn");
    approveBtn.addEventListener("click", () => submitDecision(step.step_id, step.revision_id, "approved"));

    const rejectBtn = element("button", "Reject", "danger small-btn");
    rejectBtn.addEventListener("click", () => {
      const reason = prompt("Enter rejection reason:");
      if (reason && reason.trim()) {
        submitDecision(step.step_id, step.revision_id, "rejected", reason.trim());
      }
    });

    actions.append(approveBtn, rejectBtn);
    card.append(header, details, actions);
    approvalsList.append(card);
  }
}

async function loadApprovals() {
  const request = new AbortController();
  pendingApprovals = request;
  refreshApprovalsBtn.disabled = true;
  approvalsPanel.setAttribute("aria-busy", "true");
  message("Loading pending approvals…");

  try {
    const records = await api("/approvals", { token: accessToken, signal: request.signal });
    if (pendingApprovals !== request) return;
    renderApprovals(records);
    staleAlert.hidden = true;
    message(records.length === 1 ? "1 pending approval." : `${records.length} pending approvals.`);
  } catch (error) {
    if (pendingApprovals !== request) return;
    if (error.statusCode === 401) {
      endSession("Your lab session expired. Sign in again.", true);
    } else {
      message("Failed to load approvals queue.", true);
    }
  } finally {
    if (pendingApprovals === request) {
      pendingApprovals = null;
      approvalsPanel.removeAttribute("aria-busy");
      refreshApprovalsBtn.disabled = false;
    }
  }
}

async function submitDecision(stepId, revisionId, decision, reason = "") {
  message(`Recording ${decision} decision…`);
  try {
    const payload = {
      decision,
      expected_revision_id: revisionId,
      reason: reason || undefined,
    };
    await api(`/approval-steps/${stepId}/decisions`, {
      body: payload,
      token: accessToken,
      headers: { "X-Idempotency-Key": randomId("idm_dec") },
    });
    message(`Decision recorded: ${decision}.`);
    staleAlert.hidden = true;
    loadApprovals();
  } catch (err) {
    // Stale decision feedback (T-02, FR-04, P2-08)
    if (err.statusCode === 409) {
      staleAlert.hidden = false;
      message("The proposal changed. Reload the current revision before accepting another decision.", true);
    } else {
      message(err.message || "Failed to record decision.", true);
    }
  }
}

reloadStaleBtn.addEventListener("click", () => {
  staleAlert.hidden = true;
  loadApprovals();
});

// Refresh Listeners
refreshCatalogBtn.addEventListener("click", loadCatalog);
refreshRequestsBtn.addEventListener("click", loadRequests);
refreshApprovalsBtn.addEventListener("click", loadApprovals);

// 4. Session Teardown
function endSession(text, error = false) {
  pendingCatalog?.abort();
  pendingRequests?.abort();
  pendingApprovals?.abort();
  pendingCatalog = null;
  pendingRequests = null;
  pendingApprovals = null;
  accessToken = "";
  currentUser = null;
  identity.textContent = "";
  assetsList.replaceChildren();
  requestsList.replaceChildren();
  approvalsList.replaceChildren();
  approvalsCount.hidden = true;
  staleAlert.hidden = true;

  portalWorkspace.hidden = true;
  signOut.hidden = true;
  signIn.hidden = false;
  message(text, error);
  form.elements.email.focus();
}

signOut.addEventListener("click", () => endSession("Signed out."));

// 5. Sign-in Form Handler
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
    currentUser = me;
    identity.textContent = me.full_name || me.email;
    form.reset();

    signIn.hidden = true;
    portalWorkspace.hidden = false;
    signOut.hidden = false;
    signOut.focus();

    // Check roles for approver tab visibility
    const roles = (me.roles || []).map((r) => r.role);
    const isApprover = roles.includes("approver") || roles.includes("admin");
    tabApprovals.hidden = !isApprover;

    switchTab("catalog");
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
