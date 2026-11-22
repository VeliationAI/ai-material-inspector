const token = localStorage.getItem("ami_token");
if (!token) location.href = "/login";

const user = JSON.parse(localStorage.getItem("ami_user") || "{}");
document.getElementById("userChip").textContent = user.full_name
  ? `${user.full_name} · ${user.email}`
  : user.email || "Signed in";

document.getElementById("logoutBtn").onclick = () => {
  localStorage.removeItem("ami_token");
  localStorage.removeItem("ami_user");
  location.href = "/login";
};

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {}, { Authorization: `Bearer ${token}` });
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("unauthorized");
  }
  return res;
}

let purchaseOrders = [];
let selectedFiles = [];

async function loadPOs() {
  const res = await api("/api/v1/purchase-orders");
  purchaseOrders = await res.json();
  const sel = document.getElementById("poSelect");
  sel.innerHTML = purchaseOrders
    .map((p) => `<option value="${p.po_number}" ${p.pilot_enabled ? "" : "disabled"}>
      ${p.po_number} — ${p.material_name}${p.pilot_enabled ? "" : " (coming soon)"}
    </option>`)
    .join("");
  updatePoMeta();
}

function currentPO() {
  return purchaseOrders.find((p) => p.po_number === document.getElementById("poSelect").value);
}

function updatePoMeta() {
  const po = currentPO();
  if (!po) return;
  const specs = po.specs || {};
  document.getElementById("poMeta").textContent =
    `${po.manufacturer} · ${po.store} · qty ${po.quantity} · ` +
    Object.entries(specs)
      .map(([k, v]) => `${k.replace("_mm", "")} ${v.nominal}±${v.tol}mm`)
      .join(", ");
}

document.getElementById("poSelect").onchange = updatePoMeta;

document.getElementById("files").onchange = (e) => {
  selectedFiles = Array.from(e.target.files || []);
  const box = document.getElementById("previews");
  box.innerHTML = "";
  selectedFiles.forEach((f) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    box.appendChild(img);
  });
};

function fillSample(kind) {
  const po = purchaseOrders.find((p) => p.pilot_enabled) || purchaseOrders[0];
  if (!po) return;
  document.getElementById("poSelect").value = po.po_number;
  updatePoMeta();
  const specs = po.specs || {};
  const creep = specs.creepage_mm?.nominal ?? 320;
  const height = specs.height_mm?.nominal ?? 150;
  const diameter = specs.diameter_mm?.nominal ?? 100;
  if (kind === "pass") {
    document.getElementById("creepage").value = (creep - 1.2).toFixed(1);
    document.getElementById("height").value = height.toFixed(1);
    document.getElementById("diameter").value = diameter.toFixed(1);
  } else {
    document.getElementById("creepage").value = (creep + 18).toFixed(1);
    document.getElementById("height").value = (height - 12).toFixed(1);
    document.getElementById("diameter").value = (diameter - 8).toFixed(1);
  }
}

document.getElementById("samplePassBtn").onclick = () => fillSample("pass");
document.getElementById("sampleFailBtn").onclick = () => fillSample("fail");

async function ensureDemoImages(kind) {
  if (selectedFiles.length >= 2) return selectedFiles;
  const res = await api(`/api/v1/inspections/demo-images?kind=${kind}`);
  if (!res.ok) throw new Error("Could not generate demo images");
  const blob = await res.blob();
  // endpoint returns zip? Better return JSON with base64 or multipart.
  // Fallback: generate canvas images client-side.
  return makeClientDemoImages(kind);
}

function makeClientDemoImages(kind) {
  const mk = (label, crack) => {
    const c = document.createElement("canvas");
    c.width = 640;
    c.height = 480;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#d9d2c5";
    ctx.fillRect(0, 0, 640, 480);
    ctx.fillStyle = "#b7aea0";
    ctx.beginPath();
    ctx.ellipse(320, 240, 140, 180, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1d2a33";
    ctx.font = "20px sans-serif";
    ctx.fillText("DECCAN CERAMICS", 220, 40);
    ctx.fillText("11 kV PIN INSULATOR", 210, 70);
    ctx.fillText("BATCH PI-24-0871", 230, 100);
    if (crack) {
      ctx.strokeStyle = "#3a2a22";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(280, 160);
      ctx.lineTo(360, 320);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(300, 180);
      ctx.lineTo(250, 300);
      ctx.stroke();
    }
    ctx.fillStyle = "#445";
    ctx.fillText(label, 20, 460);
    return new Promise((resolve) =>
      c.toBlob((b) => resolve(new File([b], `${label}.jpg`, { type: "image/jpeg" })), "image/jpeg", 0.92)
    );
  };
  return Promise.all([
    mk("front", kind === "fail"),
    mk("label", false),
    mk("side", kind === "fail"),
  ]);
}

async function runInspection(kind = null) {
  const err = document.getElementById("formError");
  err.hidden = true;
  const po = currentPO();
  if (!po || !po.pilot_enabled) {
    err.textContent = "Select a pilot-enabled insulator PO";
    err.hidden = false;
    return;
  }
  let files = selectedFiles;
  if (files.length < 2) {
    files = await makeClientDemoImages(kind || "pass");
  }
  const fd = new FormData();
  fd.append("po_number", po.po_number);
  const creepage = document.getElementById("creepage").value;
  const height = document.getElementById("height").value;
  const diameter = document.getElementById("diameter").value;
  if (creepage) fd.append("measured_creepage_mm", creepage);
  if (height) fd.append("measured_height_mm", height);
  if (diameter) fd.append("measured_diameter_mm", diameter);
  fd.append("angles", "front,label,side,defect");
  files.forEach((f) => fd.append("files", f));

  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  btn.textContent = "Inspecting…";
  try {
    const res = await api("/api/v1/inspections", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Inspection failed");
    renderResult(data);
    await loadHistory();
  } catch (e) {
    err.textContent = e.message || String(e);
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run AI inspection";
  }
}

document.getElementById("runBtn").onclick = () => runInspection();

function renderResult(data) {
  const panel = document.getElementById("resultPanel");
  const checks = (data.findings || [])
    .map(
      (f) => `<tr><td>${f.check_name}</td><td>${f.result}</td><td>${f.detail}</td></tr>`
    )
    .join("");
  panel.innerHTML = `
    <h2>Inspection #${data.id}</h2>
    <p><span class="decision ${data.ai_decision}">${data.ai_decision}</span>
       · approval: <strong>${data.approval_status}</strong></p>
    <p>${data.narrative}</p>
    <table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>${checks}</tbody></table>
    <div class="evidence" id="evidenceBox"></div>
    <div class="actions">
      <button type="button" id="approveBtn">Approve</button>
      <button type="button" class="ghost" id="rejectBtn">Reject receipt</button>
      <a class="button ghost" href="#" id="pdfLink">Download PDF</a>
    </div>
  `;
  document.getElementById("approveBtn").onclick = () => approve(data.id, true);
  document.getElementById("rejectBtn").onclick = () => approve(data.id, false);
  document.getElementById("pdfLink").onclick = async (ev) => {
    ev.preventDefault();
    const res = await api(`/api/v1/inspections/${data.id}/report`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `inspection_${data.id}.pdf`;
    a.click();
  };
  const box = document.getElementById("evidenceBox");
  (data.images || []).forEach(async (img) => {
    const path = img.annotated_path || img.path;
    const res = await api(path);
    if (!res.ok) return;
    const blob = await res.blob();
    const el = document.createElement("img");
    el.src = URL.createObjectURL(blob);
    el.alt = img.angle;
    box.appendChild(el);
  });
}

async function approve(id, ok) {
  const res = await api(`/api/v1/inspections/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve: ok, notes: ok ? "Officer approved" : "Officer rejected" }),
  });
  const data = await res.json();
  renderResult(data);
  await loadHistory();
}

async function loadHistory() {
  const res = await api("/api/v1/inspections");
  const rows = await res.json();
  const body = document.getElementById("historyTable");
  body.innerHTML = rows
    .map(
      (r) => `<tr class="history-item" data-id="${r.id}">
        <td>${r.id}</td><td>${r.po_number}</td><td>${r.material_name}</td>
        <td><span class="decision ${r.ai_decision}">${r.ai_decision}</span></td>
        <td>${r.approval_status}</td>
        <td>${new Date(r.created_at).toLocaleString()}</td></tr>`
    )
    .join("");
  body.querySelectorAll("tr").forEach((tr) => {
    tr.onclick = async () => {
      const res2 = await api(`/api/v1/inspections/${tr.dataset.id}`);
      renderResult(await res2.json());
    };
  });
  const pass = rows.filter((r) => r.ai_decision === "PASS").length;
  const fail = rows.filter((r) => r.ai_decision === "FAIL").length;
  const review = rows.filter((r) => r.ai_decision === "NEEDS_REVIEW").length;
  document.getElementById("kpis").innerHTML = `
    <div class="kpi"><span>Inspections</span><strong>${rows.length}</strong></div>
    <div class="kpi"><span>PASS</span><strong>${pass}</strong></div>
    <div class="kpi"><span>FAIL</span><strong>${fail}</strong></div>
    <div class="kpi"><span>Review</span><strong>${review}</strong></div>`;
}

loadPOs().then(loadHistory);
