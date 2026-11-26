/**
 * Multi-Role Dashboard Controller (Admin, Blood Bank Staff, Hospital Staff, Doctor, Donor).
 * Renders role-appropriate sidebar sections and communicates with FastAPI REST endpoints.
 */
import { apiRequest } from "./api.js";
import { handleLogout, requireAuth } from "./auth.js";
import { badgeForStatus, escapeHtml, formatDate, renderBarChart, setLoading, showToast } from "./ui.js";

const ROLE_TABS = {
  ADMIN: [
    { id: "overview", label: "Analytics Overview" },
    { id: "requests", label: "Triage & Requests" },
    { id: "inventory", label: "Blood Inventory" },
    { id: "donations", label: "Donations & Separation" },
    { id: "donors", label: "Donors" },
    { id: "patients", label: "Patients" },
    { id: "hospitals", label: "Hospitals" },
    { id: "camps", label: "Blood Camps" },
    { id: "users", label: "Users & RBAC" },
    { id: "audit", label: "Audit Logs" },
    { id: "notifications", label: "Notifications" },
  ],
  BLOOD_BANK_STAFF: [
    { id: "overview", label: "Bank Analytics" },
    { id: "requests", label: "Triage & Allocation" },
    { id: "inventory", label: "Blood Inventory" },
    { id: "donations", label: "Donations & Separation" },
    { id: "donors", label: "Donors" },
    { id: "camps", label: "Blood Camps" },
    { id: "hospitals", label: "Hospitals" },
    { id: "notifications", label: "Notifications" },
  ],
  HOSPITAL_STAFF: [
    { id: "overview", label: "Inventory Summary" },
    { id: "requests", label: "Hospital Requests" },
    { id: "patients", label: "Patients" },
    { id: "inventory", label: "Available Blood" },
    { id: "camps", label: "Blood Camps" },
    { id: "notifications", label: "Notifications" },
  ],
  DOCTOR: [
    { id: "overview", label: "Clinical Summary" },
    { id: "patients", label: "My Patients" },
    { id: "requests", label: "Patient Requests" },
    { id: "inventory", label: "Available Blood" },
    { id: "camps", label: "Blood Camps" },
    { id: "notifications", label: "Notifications" },
  ],
  DONOR: [
    { id: "overview", label: "Donor Overview" },
    { id: "donors", label: "My Donor Profile" },
    { id: "donations", label: "My Donations" },
    { id: "camps", label: "Nearby Blood Camps" },
    { id: "notifications", label: "Notifications" },
  ],
};

let currentUser = null;
let activeTab = "overview";

export async function initDashboard(expectedRole) {
  currentUser = await requireAuth(expectedRole);
  if (!currentUser) return;

  renderHeader();
  renderSidebar();
  await refreshUnreadBadge();
  await loadTab("overview");

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);
}

function renderHeader() {
  const userPill = document.getElementById("user-meta-pill");
  if (!userPill) return;
  const scope = currentUser.hospital_id
    ? `Hospital: ${currentUser.hospital_id}`
    : currentUser.blood_bank_id
    ? `Blood Bank: ${currentUser.blood_bank_id}`
    : "Global Scope";
  userPill.innerHTML = `
    <span class="badge badge-info">${escapeHtml(currentUser.role)}</span>
    <strong>${escapeHtml(currentUser.username)}</strong>
    <span class="text-muted">(${escapeHtml(scope)})</span>
  `;
}

function renderSidebar() {
  const nav = document.getElementById("sidebar-nav");
  if (!nav) return;
  const tabs = ROLE_TABS[currentUser.role] || [];
  nav.innerHTML = tabs
    .map(
      (t) => `
      <button class="nav-btn ${t.id === activeTab ? "active" : ""}" data-tab="${escapeHtml(t.id)}">
        <span>${escapeHtml(t.label)}</span>
        ${t.id === "notifications" ? `<span id="notif-badge" class="badge badge-danger hidden">0</span>` : ""}
      </button>
    `
    )
    .join("");

  nav.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => loadTab(btn.dataset.tab));
  });
}

async function refreshUnreadBadge() {
  try {
    const unread = await apiRequest("/notifications?is_read=false&limit=100");
    const badge = document.getElementById("notif-badge");
    if (badge) {
      if (unread.length > 0) {
        badge.textContent = String(unread.length);
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }
  } catch {
    // Non-fatal
  }
}

async function loadTab(tabId) {
  activeTab = tabId;
  document.querySelectorAll("#sidebar-nav .nav-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabId);
  });

  const container = document.getElementById("dashboard-content");
  setLoading(container, true, "Loading section...");

  try {
    switch (tabId) {
      case "overview":
        await renderOverview(container);
        break;
      case "donors":
        await renderDonors(container);
        break;
      case "donations":
        await renderDonations(container);
        break;
      case "inventory":
        await renderInventory(container);
        break;
      case "patients":
        await renderPatients(container);
        break;
      case "requests":
        await renderRequests(container);
        break;
      case "camps":
        await renderCamps(container);
        break;
      case "hospitals":
        await renderHospitals(container);
        break;
      case "users":
        await renderUsersAndRoles(container);
        break;
      case "audit":
        await renderAuditLogs(container);
        break;
      case "notifications":
        await renderNotifications(container);
        break;
      default:
        container.innerHTML = `<div class="card"><p>Unknown section.</p></div>`;
    }
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error">${escapeHtml(err.message)}</div>`;
  }
}

// ==========================================
// 1. Overview & MongoDB Aggregation Dashboards
// ==========================================

async function renderOverview(container) {
  if (currentUser.role === "ADMIN" || currentUser.role === "BLOOD_BANK_STAFF") {
    const [stats, cs] = await Promise.all([
      apiRequest("/analytics/dashboard"),
      apiRequest("/analytics/change-streams/status"),
    ]);

    container.innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Total Donors</div><div class="kpi-value">${stats.total_donors}</div></div>
        <div class="kpi-card"><div class="kpi-label">Total Donations</div><div class="kpi-value">${stats.total_donations}</div></div>
        <div class="kpi-card"><div class="kpi-label">Available Units</div><div class="kpi-value">${stats.available_blood_units}</div></div>
        <div class="kpi-card"><div class="kpi-label">Expiring (7d)</div><div class="kpi-value">${stats.expiring_soon_units}</div></div>
        <div class="kpi-card"><div class="kpi-label">Pending Requests</div><div class="kpi-value">${stats.pending_requests}</div></div>
        <div class="kpi-card"><div class="kpi-label">Allocated Requests</div><div class="kpi-value">${stats.allocated_requests}</div></div>
      </div>

      <div class="two-col">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">Blood Group Distribution (Aggregation)</h3>
            <button id="scan-alerts-btn" class="btn btn-primary btn-sm">Scan Expiry & Low Stock</button>
          </div>
          <div id="bg-chart"></div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">MongoDB Change Streams & Priority Breakdown</h3>
            ${badgeForStatus(cs.supported ? "ACTIVE" : "PENDING")}
          </div>
          <p class="text-muted">${escapeHtml(cs.details)}</p>
          <div class="mt-4">
            <strong style="font-size:13px;">Request Priority Distribution</strong>
            <div id="prio-chart" class="mt-2"></div>
          </div>
        </div>
      </div>

      <div class="two-col">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Component Inventory Breakdown</h3></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Component</th><th>Status</th><th>Units</th></tr></thead>
              <tbody>
                ${
                  stats.component_breakdown.length
                    ? stats.component_breakdown
                        .map((r) => `<tr><td>${escapeHtml(r.component_type)}</td><td>${badgeForStatus(r.status)}</td><td>${r.count}</td></tr>`)
                        .join("")
                    : `<tr><td colspan="3" class="text-muted">No blood units recorded yet.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><h3 class="card-title">Monthly Donation Trends</h3></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Month</th><th>Donations</th><th>Total Volume (mL)</th></tr></thead>
              <tbody>
                ${
                  stats.monthly_donations.length
                    ? stats.monthly_donations
                        .map((m) => `<tr><td>${m.year}-${String(m.month).padStart(2, "0")}</td><td>${m.count}</td><td>${m.total_volume_ml}</td></tr>`)
                        .join("")
                    : `<tr><td colspan="3" class="text-muted">No donations recorded yet.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    renderBarChart(
      document.getElementById("bg-chart"),
      stats.blood_group_distribution,
      (r) => `${r.blood_group} ${r.rh_factor === "POSITIVE" ? "+" : "-"}`,
      (r) => r.count
    );
    renderBarChart(
      document.getElementById("prio-chart"),
      stats.request_priority_breakdown,
      (r) => r.priority,
      (r) => r.count
    );

    document.getElementById("scan-alerts-btn").addEventListener("click", async () => {
      try {
        const res = await apiRequest("/notifications/scan-alerts", { method: "POST", body: {} });
        showToast(
          `Scan complete: ${res.expired_units_marked} expired, ${res.expiring_soon_count} expiring soon, ${res.notifications_dispatched} alert(s) sent.`,
          "success"
        );
        await refreshUnreadBadge();
        await loadTab("overview");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    return;
  }

  if (currentUser.role === "HOSPITAL_STAFF" || currentUser.role === "DOCTOR") {
    const [dist, requests] = await Promise.all([
      apiRequest("/analytics/inventory-distribution"),
      apiRequest("/blood-requests"),
    ]);
    const totalAvailable = dist.reduce((acc, r) => acc + r.available_units, 0);
    const pending = requests.filter((r) => r.status === "PENDING").length;

    container.innerHTML = `
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Available Units (Network)</div><div class="kpi-value">${totalAvailable}</div></div>
        <div class="kpi-card"><div class="kpi-label">Scoped Blood Requests</div><div class="kpi-value">${requests.length}</div></div>
        <div class="kpi-card"><div class="kpi-label">Pending Requests</div><div class="kpi-value">${pending}</div></div>
      </div>
      <div class="card">
        <div class="card-header"><h3 class="card-title">Available Blood Stock by Group & Component</h3></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Blood Group</th><th>Rh Factor</th><th>Component</th><th>Available Units</th><th>Earliest Expiry</th></tr></thead>
            <tbody>
              ${
                dist.length
                  ? dist
                      .map(
                        (r) =>
                          `<tr><td><strong>${escapeHtml(r.blood_group)}</strong></td><td>${escapeHtml(r.rh_factor)}</td><td>${escapeHtml(r.component_type)}</td><td>${r.available_units}</td><td>${formatDate(r.earliest_expiry)}</td></tr>`
                      )
                      .join("")
                  : `<tr><td colspan="5" class="text-muted">No available units in inventory.</td></tr>`
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
    return;
  }

  // DONOR overview
  const [donors, donations, camps] = await Promise.all([
    apiRequest("/donors"),
    apiRequest("/donations"),
    apiRequest("/blood-camps"),
  ]);
  const profile = donors[0] || null;
  container.innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-label">Blood Type</div><div class="kpi-value">${profile ? escapeHtml(`${profile.blood_group} ${profile.rh_factor === "POSITIVE" ? "+" : "-"}`) : "Not Set"}</div></div>
      <div class="kpi-card"><div class="kpi-label">Eligibility</div><div class="kpi-value" style="font-size:18px;margin-top:12px;">${profile ? badgeForStatus(profile.eligibility_status) : badgeForStatus("PENDING")}</div></div>
      <div class="kpi-card"><div class="kpi-label">My Donations</div><div class="kpi-value">${donations.length}</div></div>
      <div class="kpi-card"><div class="kpi-label">Blood Camps Listed</div><div class="kpi-value">${camps.length}</div></div>
    </div>
    <div class="card">
      <h3 class="card-title">Welcome, ${escapeHtml(currentUser.username)}</h3>
      <p class="text-muted mt-2">
        ${
          profile
            ? `Donor Card: <strong>${escapeHtml(profile.donor_card_number)}</strong> | Next Eligible Donation: <strong>${formatDate(profile.next_eligible_date)}</strong>`
            : "Create your donor profile under 'My Donor Profile' to track eligibility and donations."
        }
      </p>
    </div>
  `;
}

// ==========================================
// 2. Donors / Donor Self-Service
// ==========================================

async function renderDonors(container) {
  const donors = await apiRequest("/donors");
  const isDonor = currentUser.role === "DONOR";

  if (isDonor) {
    const profile = donors[0] || null;
    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">${profile ? "My Encrypted Donor Profile" : "Complete Donor Registration"}</h3>
          ${profile ? badgeForStatus(profile.eligibility_status) : ""}
        </div>
        <form id="donor-self-form" class="form-grid">
          ${
            !profile
              ? `
            <div class="form-group"><label>Donor Card Number</label><input name="donor_card_number" required placeholder="CARD-2026-01"></div>
            <div class="form-group"><label>Date of Birth</label><input type="date" name="date_of_birth" required></div>
            <div class="form-group"><label>Gender</label><select name="gender"><option>MALE</option><option>FEMALE</option><option>OTHER</option></select></div>
            <div class="form-group"><label>Blood Group</label><select name="blood_group"><option>O</option><option>A</option><option>B</option><option>AB</option></select></div>
            <div class="form-group"><label>Rh Factor</label><select name="rh_factor"><option>POSITIVE</option><option>NEGATIVE</option></select></div>
          `
              : ""
          }
          <div class="form-group"><label>First Name</label><input name="first_name" required value="${escapeHtml(profile?.first_name || "")}"></div>
          <div class="form-group"><label>Last Name</label><input name="last_name" required value="${escapeHtml(profile?.last_name || "")}"></div>
          <div class="form-group"><label>Phone (AES-256-GCM Encrypted)</label><input name="contact_phone" required value="${escapeHtml(profile?.contact_phone || "")}"></div>
          <div class="form-group"><label>Address (AES-256-GCM Encrypted)</label><input name="address" required value="${escapeHtml(profile?.address || "")}"></div>
          <div class="form-group"><label>Emergency Contact</label><input name="emergency_contact" value="${escapeHtml(profile?.emergency_contact || "")}"></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">${profile ? "Update Profile" : "Save Donor Profile"}</button></div>
        </form>
      </div>
    `;

    document.getElementById("donor-self-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        if (profile) {
          await apiRequest(`/donors/${profile._id}`, {
            method: "PUT",
            body: {
              first_name: f.first_name.value.trim(),
              last_name: f.last_name.value.trim(),
              contact_phone: f.contact_phone.value.trim(),
              address: f.address.value.trim(),
              emergency_contact: f.emergency_contact.value.trim() || null,
            },
          });
          showToast("Donor profile updated securely.", "success");
        } else {
          await apiRequest("/donors", {
            method: "POST",
            body: {
              user_id: currentUser._id,
              donor_card_number: f.donor_card_number.value.trim(),
              first_name: f.first_name.value.trim(),
              last_name: f.last_name.value.trim(),
              date_of_birth: f.date_of_birth.value,
              gender: f.gender.value,
              blood_group: f.blood_group.value,
              rh_factor: f.rh_factor.value,
              contact_phone: f.contact_phone.value.trim(),
              address: f.address.value.trim(),
              emergency_contact: f.emergency_contact.value.trim() || null,
            },
          });
          showToast("Donor profile created!", "success");
        }
        await loadTab("donors");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    return;
  }

  // ADMIN / BLOOD_BANK_STAFF Donors Management
  container.innerHTML = `
    <div class="card">
      <div class="card-header"><h3 class="card-title">Register New Donor</h3></div>
      <form id="create-donor-form" class="form-grid">
        <div class="form-group"><label>Linked User ID</label><input name="user_id" required placeholder="MongoDB User _id"></div>
        <div class="form-group"><label>Donor Card #</label><input name="donor_card_number" required placeholder="CARD-1001"></div>
        <div class="form-group"><label>First Name</label><input name="first_name" required></div>
        <div class="form-group"><label>Last Name</label><input name="last_name" required></div>
        <div class="form-group"><label>DOB</label><input type="date" name="date_of_birth" required></div>
        <div class="form-group"><label>Gender</label><select name="gender"><option>MALE</option><option>FEMALE</option><option>OTHER</option></select></div>
        <div class="form-group"><label>Blood Group</label><select name="blood_group"><option>O</option><option>A</option><option>B</option><option>AB</option></select></div>
        <div class="form-group"><label>Rh Factor</label><select name="rh_factor"><option>POSITIVE</option><option>NEGATIVE</option></select></div>
        <div class="form-group"><label>Phone</label><input name="contact_phone" required></div>
        <div class="form-group"><label>Address</label><input name="address" required></div>
        <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Register Donor</button></div>
      </form>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">Registered Donors (${donors.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Card #</th><th>Name</th><th>Blood Type</th><th>Phone</th><th>Eligibility</th><th>Last Donation</th></tr></thead>
          <tbody>
            ${
              donors.length
                ? donors
                    .map(
                      (d) =>
                        `<tr><td>${escapeHtml(d.donor_card_number)}</td><td>${escapeHtml(`${d.first_name} ${d.last_name}`)}</td><td><strong>${escapeHtml(d.blood_group)} ${d.rh_factor === "POSITIVE" ? "+" : "-"}</strong></td><td>${escapeHtml(d.contact_phone || "Encrypted")}</td><td>${badgeForStatus(d.eligibility_status)}</td><td>${formatDate(d.last_donation_date)}</td></tr>`
                    )
                    .join("")
                : `<tr><td colspan="6" class="text-muted">No donors found.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("create-donor-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await apiRequest("/donors", {
        method: "POST",
        body: {
          user_id: f.user_id.value.trim(),
          donor_card_number: f.donor_card_number.value.trim(),
          first_name: f.first_name.value.trim(),
          last_name: f.last_name.value.trim(),
          date_of_birth: f.date_of_birth.value,
          gender: f.gender.value,
          blood_group: f.blood_group.value,
          rh_factor: f.rh_factor.value,
          contact_phone: f.contact_phone.value.trim(),
          address: f.address.value.trim(),
        },
      });
      showToast("Donor registered with AES-256-GCM encrypted PII.", "success");
      await loadTab("donors");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

// ==========================================
// 3. Donations & Component Separation
// ==========================================

async function renderDonations(container) {
  const donations = await apiRequest("/donations");
  const canWrite = currentUser.role === "ADMIN" || currentUser.role === "BLOOD_BANK_STAFF";

  container.innerHTML = `
    ${
      canWrite
        ? `
      <div class="card">
        <div class="card-header"><h3 class="card-title">Record New Blood Donation</h3></div>
        <form id="create-donation-form" class="form-grid">
          <div class="form-group"><label>Donation Code</label><input name="donation_code" required placeholder="DON-2026-001"></div>
          <div class="form-group"><label>Donor ID</label><input name="donor_id" required placeholder="Donor _id"></div>
          <div class="form-group"><label>Blood Bank ID</label><input name="blood_bank_id" required value="${escapeHtml(currentUser.blood_bank_id || "bb_central")}"></div>
          <div class="form-group"><label>Volume (mL)</label><input type="number" name="volume_ml" value="450" min="200" max="600" required></div>
          <div class="form-group"><label>Hemoglobin (g/dL)</label><input type="number" step="0.1" name="hemoglobin_g_dl" value="14.0" min="10" max="20" required></div>
          <div class="form-group"><label>Blood Pressure</label><input name="blood_pressure" value="120/80" required></div>
          <div class="form-group"><label>Screening Status</label><select name="screening_status"><option>PASSED</option><option>PENDING</option><option>REJECTED</option></select></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Record Donation</button></div>
        </form>
      </div>
    `
        : ""
    }
    <div class="card">
      <div class="card-header"><h3 class="card-title">Donation Records (${donations.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Code</th><th>Donor ID</th><th>Blood Bank</th><th>Date</th><th>Screening</th><th>Components</th>${canWrite ? "<th>Action</th>" : ""}</tr></thead>
          <tbody>
            ${
              donations.length
                ? donations
                    .map(
                      (d) => `
                  <tr>
                    <td><strong>${escapeHtml(d.donation_code)}</strong></td>
                    <td>${escapeHtml(d.donor_id)}</td>
                    <td>${escapeHtml(d.blood_bank_id)}</td>
                    <td>${formatDate(d.donation_date)}</td>
                    <td>${badgeForStatus(d.screening_status)}</td>
                    <td>${d.components_separated ? badgeForStatus("ALLOCATED") : badgeForStatus("PENDING")}</td>
                    ${
                      canWrite
                        ? `<td>${
                            !d.components_separated && d.screening_status === "PASSED"
                              ? `<button class="btn btn-success btn-sm sep-btn" data-id="${escapeHtml(d._id)}">Separate Components</button>`
                              : `<span class="text-muted">—</span>`
                          }</td>`
                        : ""
                    }
                  </tr>`
                    )
                    .join("")
                : `<tr><td colspan="${canWrite ? 7 : 6}" class="text-muted">No donations found.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  if (canWrite) {
    document.getElementById("create-donation-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await apiRequest("/donations", {
          method: "POST",
          body: {
            donation_code: f.donation_code.value.trim(),
            donor_id: f.donor_id.value.trim(),
            blood_bank_id: f.blood_bank_id.value.trim(),
            volume_ml: Number(f.volume_ml.value),
            hemoglobin_g_dl: Number(f.hemoglobin_g_dl.value),
            blood_pressure: f.blood_pressure.value.trim(),
            screening_status: f.screening_status.value,
          },
        });
        showToast("Donation recorded.", "success");
        await loadTab("donations");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    container.querySelectorAll(".sep-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await apiRequest(`/donations/${btn.dataset.id}/separate-components`, {
            method: "POST",
            body: { components: ["RBC", "FFP", "PLATELETS"] },
          });
          showToast(`Created ${res.generated_units.length} blood unit(s) from ${res.donation_code}.`, "success");
          await loadTab("donations");
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  }
}

// ==========================================
// 4. Blood Inventory
// ==========================================

async function renderInventory(container) {
  const units = await apiRequest("/blood-units");
  const canWrite = currentUser.role === "ADMIN" || currentUser.role === "BLOOD_BANK_STAFF";

  container.innerHTML = `
    ${
      canWrite
        ? `
      <div class="card">
        <div class="card-header"><h3 class="card-title">Add Individual Blood Unit</h3></div>
        <form id="create-unit-form" class="form-grid">
          <div class="form-group"><label>Unit ID</label><input name="unit_id" required placeholder="UNIT-2026-001"></div>
          <div class="form-group"><label>Source Donation</label><input name="source_donation_id" required placeholder="DON-2026-001"></div>
          <div class="form-group"><label>Blood Bank ID</label><input name="blood_bank_id" required value="${escapeHtml(currentUser.blood_bank_id || "bb_central")}"></div>
          <div class="form-group"><label>Blood Group</label><select name="blood_group"><option>O</option><option>A</option><option>B</option><option>AB</option></select></div>
          <div class="form-group"><label>Rh Factor</label><select name="rh_factor"><option>POSITIVE</option><option>NEGATIVE</option></select></div>
          <div class="form-group"><label>Component</label><select name="component_type"><option>RBC</option><option>WHOLE_BLOOD</option><option>PLATELETS</option><option>FFP</option><option>CRYOPRECIPITATE</option></select></div>
          <div class="form-group"><label>Volume (mL)</label><input type="number" name="volume_ml" value="250" min="50" max="500" required></div>
          <div class="form-group"><label>Expiry Date</label><input type="datetime-local" name="expiry_date" required></div>
          <div class="form-group"><label>Refrigerator</label><input name="refrigerator_id" value="REF-A1" required></div>
          <div class="form-group"><label>Shelf</label><input name="shelf" value="S1" required></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Add Blood Unit</button></div>
        </form>
      </div>
    `
        : ""
    }
    <div class="card">
      <div class="card-header"><h3 class="card-title">Blood Units Inventory (${units.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Unit ID</th><th>Type</th><th>Component</th><th>Blood Bank</th><th>Expiry</th><th>Status</th>${canWrite ? "<th>Action</th>" : ""}</tr></thead>
          <tbody>
            ${
              units.length
                ? units
                    .map(
                      (u) => `
                  <tr>
                    <td><strong>${escapeHtml(u.unit_id)}</strong></td>
                    <td>${escapeHtml(u.blood_group)} ${u.rh_factor === "POSITIVE" ? "+" : "-"}</td>
                    <td>${escapeHtml(u.component_type)}</td>
                    <td>${escapeHtml(u.blood_bank_id)}</td>
                    <td>${formatDate(u.expiry_date)}</td>
                    <td>${badgeForStatus(u.status)}</td>
                    ${
                      canWrite
                        ? `<td>${
                            u.status === "AVAILABLE"
                              ? `<button class="btn btn-danger btn-sm discard-btn" data-id="${escapeHtml(u._id)}">Discard</button>`
                              : `<span class="text-muted">—</span>`
                          }</td>`
                        : ""
                    }
                  </tr>`
                    )
                    .join("")
                : `<tr><td colspan="${canWrite ? 7 : 6}" class="text-muted">No blood units available.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  if (canWrite) {
    document.getElementById("create-unit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await apiRequest("/blood-units", {
          method: "POST",
          body: {
            unit_id: f.unit_id.value.trim(),
            source_donation_id: f.source_donation_id.value.trim(),
            blood_bank_id: f.blood_bank_id.value.trim(),
            blood_group: f.blood_group.value,
            rh_factor: f.rh_factor.value,
            component_type: f.component_type.value,
            volume_ml: Number(f.volume_ml.value),
            expiry_date: new Date(f.expiry_date.value).toISOString(),
            storage_location: { refrigerator_id: f.refrigerator_id.value.trim(), shelf: f.shelf.value.trim() },
          },
        });
        showToast("Blood unit added to inventory.", "success");
        await loadTab("inventory");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    container.querySelectorAll(".discard-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await apiRequest(`/blood-units/${btn.dataset.id}`, {
            method: "PUT",
            body: { status: "DISCARDED" },
          });
          showToast("Unit marked DISCARDED.", "success");
          await loadTab("inventory");
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  }
}

// ==========================================
// 5. Patients
// ==========================================

async function renderPatients(container) {
  const patients = await apiRequest("/patients");
  container.innerHTML = `
    <div class="card">
      <div class="card-header"><h3 class="card-title">Register Patient</h3></div>
      <form id="create-patient-form" class="form-grid">
        <div class="form-group"><label>Hospital ID</label><input name="hospital_id" required value="${escapeHtml(currentUser.hospital_id || "hosp_01")}"></div>
        <div class="form-group"><label>Attending Doctor ID</label><input name="attending_doctor_id" required value="${escapeHtml(currentUser.role === "DOCTOR" ? currentUser._id : "")}" placeholder="Doctor User _id"></div>
        <div class="form-group"><label>MRN</label><input name="mrn" required placeholder="MRN-2026-01"></div>
        <div class="form-group"><label>Full Name</label><input name="full_name" required></div>
        <div class="form-group"><label>Blood Group</label><select name="blood_group"><option>O</option><option>A</option><option>B</option><option>AB</option></select></div>
        <div class="form-group"><label>Rh Factor</label><select name="rh_factor"><option>POSITIVE</option><option>NEGATIVE</option></select></div>
        <div class="form-group"><label>Clinical Indication</label><input name="clinical_indication" required></div>
        <div class="form-group"><label>Medical Notes (AES-256-GCM Encrypted)</label><input name="medical_notes" placeholder="Optional clinical notes"></div>
        <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Register Patient</button></div>
      </form>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">Patients (${patients.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>MRN</th><th>Name</th><th>Blood Type</th><th>Hospital</th><th>Indication</th><th>Medical Notes (Decrypted)</th></tr></thead>
          <tbody>
            ${
              patients.length
                ? patients
                    .map(
                      (p) =>
                        `<tr><td>${escapeHtml(p.mrn)}</td><td>${escapeHtml(p.full_name)}</td><td><strong>${escapeHtml(p.blood_group)} ${p.rh_factor === "POSITIVE" ? "+" : "-"}</strong></td><td>${escapeHtml(p.hospital_id)}</td><td>${escapeHtml(p.clinical_indication)}</td><td>${escapeHtml(p.medical_notes || "—")}</td></tr>`
                    )
                    .join("")
                : `<tr><td colspan="6" class="text-muted">No patients found in your scope.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("create-patient-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await apiRequest("/patients", {
        method: "POST",
        body: {
          hospital_id: f.hospital_id.value.trim(),
          attending_doctor_id: f.attending_doctor_id.value.trim(),
          mrn: f.mrn.value.trim(),
          full_name: f.full_name.value.trim(),
          blood_group: f.blood_group.value,
          rh_factor: f.rh_factor.value,
          clinical_indication: f.clinical_indication.value.trim(),
          medical_notes: f.medical_notes.value.trim() || null,
        },
      });
      showToast("Patient registered securely.", "success");
      await loadTab("patients");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

// ==========================================
// 6. Blood Requests, Triage & Atomic Allocation
// ==========================================

async function renderRequests(container) {
  const canSubmit = ["ADMIN", "HOSPITAL_STAFF", "DOCTOR"].includes(currentUser.role);
  const canProcess = ["ADMIN", "BLOOD_BANK_STAFF"].includes(currentUser.role);
  const requests = canProcess ? await apiRequest("/blood-requests/triage") : await apiRequest("/blood-requests");

  container.innerHTML = `
    ${
      canSubmit
        ? `
      <div class="card">
        <div class="card-header"><h3 class="card-title">Submit Blood Request</h3></div>
        <form id="create-req-form" class="form-grid">
          <div class="form-group"><label>Request Code</label><input name="request_code" required placeholder="REQ-2026-001"></div>
          <div class="form-group"><label>Hospital ID</label><input name="hospital_id" required value="${escapeHtml(currentUser.hospital_id || "hosp_01")}"></div>
          <div class="form-group"><label>Doctor ID</label><input name="doctor_id" required value="${escapeHtml(currentUser.role === "DOCTOR" ? currentUser._id : "doc_01")}"></div>
          <div class="form-group"><label>Patient ID</label><input name="patient_id" required placeholder="Patient _id"></div>
          <div class="form-group"><label>Blood Group</label><select name="blood_group"><option>O</option><option>A</option><option>B</option><option>AB</option></select></div>
          <div class="form-group"><label>Rh Factor</label><select name="rh_factor"><option>POSITIVE</option><option>NEGATIVE</option></select></div>
          <div class="form-group"><label>Component</label><select name="component_type"><option>RBC</option><option>WHOLE_BLOOD</option><option>PLATELETS</option><option>FFP</option><option>CRYOPRECIPITATE</option></select></div>
          <div class="form-group"><label>Units</label><input type="number" name="units_requested" value="1" min="1" max="20" required></div>
          <div class="form-group"><label>Priority</label><select name="priority"><option>ROUTINE</option><option>URGENT</option><option>CRITICAL</option></select></div>
          <div class="form-group"><label>Clinical Reason</label><input name="clinical_reason" required placeholder="Reason for transfusion"></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Submit Request</button></div>
        </form>
      </div>
    `
        : ""
    }
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${canProcess ? "Priority Triage Queue" : "Blood Requests"} (${requests.length})</h3>
      </div>
      <div id="alloc-banner" class="hidden"></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Code</th><th>Hospital</th><th>Needed</th><th>Priority</th><th>Status</th><th>Allocated Units</th>${canProcess ? "<th>Actions</th>" : ""}</tr></thead>
          <tbody>
            ${
              requests.length
                ? requests
                    .map(
                      (r) => `
                  <tr>
                    <td><strong>${escapeHtml(r.request_code)}</strong></td>
                    <td>${escapeHtml(r.hospital_id)}</td>
                    <td>${escapeHtml(r.blood_group)} ${r.rh_factor === "POSITIVE" ? "+" : "-"} ${escapeHtml(r.component_type)} (x${r.units_requested})</td>
                    <td>${badgeForStatus(r.priority)}</td>
                    <td>${badgeForStatus(r.status)}</td>
                    <td>${escapeHtml((r.allocated_units || []).join(", ") || "—")}</td>
                    ${
                      canProcess
                        ? `<td><div class="flex-row">
                            ${r.status === "PENDING" ? `<button class="btn btn-secondary btn-sm req-approve" data-code="${escapeHtml(r.request_code)}">Approve</button>` : ""}
                            ${["PENDING", "APPROVED", "PARTIALLY_ALLOCATED"].includes(r.status) ? `<button class="btn btn-success btn-sm req-alloc" data-code="${escapeHtml(r.request_code)}">Atomic Allocate</button>` : ""}
                            ${["PENDING", "APPROVED"].includes(r.status) ? `<button class="btn btn-danger btn-sm req-reject" data-code="${escapeHtml(r.request_code)}">Reject</button>` : ""}
                          </div></td>`
                        : ""
                    }
                  </tr>`
                    )
                    .join("")
                : `<tr><td colspan="${canProcess ? 7 : 6}" class="text-muted">No blood requests found.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  if (canSubmit) {
    document.getElementById("create-req-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await apiRequest("/blood-requests", {
          method: "POST",
          body: {
            request_code: f.request_code.value.trim(),
            hospital_id: f.hospital_id.value.trim(),
            doctor_id: f.doctor_id.value.trim(),
            patient_id: f.patient_id.value.trim(),
            blood_group: f.blood_group.value,
            rh_factor: f.rh_factor.value,
            component_type: f.component_type.value,
            units_requested: Number(f.units_requested.value),
            priority: f.priority.value,
            clinical_reason: f.clinical_reason.value.trim(),
          },
        });
        showToast("Blood request submitted.", "success");
        await loadTab("requests");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }

  if (canProcess) {
    container.querySelectorAll(".req-approve").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          await apiRequest(`/blood-requests/${b.dataset.code}/approve`, { method: "POST", body: {} });
          showToast(`Approved ${b.dataset.code}`, "success");
          await loadTab("requests");
        } catch (err) {
          showToast(err.message, "error");
        }
      })
    );
    container.querySelectorAll(".req-reject").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          await apiRequest(`/blood-requests/${b.dataset.code}/reject`, {
            method: "POST",
            body: { reason: "Rejected via triage console" },
          });
          showToast(`Rejected ${b.dataset.code}`, "success");
          await loadTab("requests");
        } catch (err) {
          showToast(err.message, "error");
        }
      })
    );
    container.querySelectorAll(".req-alloc").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          const res = await apiRequest(`/blood-requests/${b.dataset.code}/allocate`, { method: "POST", body: {} });
          showToast(
            `Allocated ${res.newly_allocated_count} unit(s) to ${b.dataset.code}. ${res.compatibility_disclaimer}`,
            "success"
          );
          await loadTab("requests");
        } catch (err) {
          showToast(err.message, "error");
        }
      })
    );
  }
}

// ==========================================
// 7. Blood Camps & Geospatial Nearby Search
// ==========================================

async function renderCamps(container) {
  const canWrite = currentUser.role === "ADMIN" || currentUser.role === "BLOOD_BANK_STAFF";
  const camps = await apiRequest("/blood-camps");

  container.innerHTML = `
    ${
      canWrite
        ? `
      <div class="card">
        <div class="card-header"><h3 class="card-title">Create Community Blood Camp</h3></div>
        <form id="create-camp-form" class="form-grid">
          <div class="form-group"><label>Camp Code</label><input name="camp_code" required placeholder="CAMP-2026-01"></div>
          <div class="form-group"><label>Title</label><input name="title" required placeholder="City Tech Park Drive"></div>
          <div class="form-group"><label>Blood Bank ID</label><input name="organizer_blood_bank_id" required value="${escapeHtml(currentUser.blood_bank_id || "bb_central")}"></div>
          <div class="form-group"><label>Address</label><input name="address" required></div>
          <div class="form-group"><label>Longitude</label><input type="number" step="any" name="longitude" value="77.5946" required></div>
          <div class="form-group"><label>Latitude</label><input type="number" step="any" name="latitude" value="12.9716" required></div>
          <div class="form-group"><label>Start Time</label><input type="datetime-local" name="start_time" required></div>
          <div class="form-group"><label>End Time</label><input type="datetime-local" name="end_time" required></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Create Blood Camp</button></div>
        </form>
      </div>
    `
        : ""
    }
    <div class="card">
      <div class="card-header"><h3 class="card-title">Geospatial Blood Camp Finder (2dsphere)</h3></div>
      <form id="nearby-camp-form" class="flex-row">
        <input type="number" step="any" name="longitude" value="77.5946" placeholder="Longitude" style="width:140px;" required>
        <input type="number" step="any" name="latitude" value="12.9716" placeholder="Latitude" style="width:140px;" required>
        <input type="number" step="1" name="radius_km" value="25" placeholder="Radius km" style="width:120px;" required>
        <button class="btn btn-primary" type="submit">Find Nearby Camps</button>
        <button class="btn btn-secondary" type="button" id="reset-camps-btn">Show All</button>
      </form>
      <div class="table-wrap mt-4">
        <table>
          <thead><tr><th>Code</th><th>Title</th><th>Address</th><th>Start</th><th>Distance</th><th>Status</th></tr></thead>
          <tbody id="camps-tbody">
            ${renderCampRows(camps)}
          </tbody>
        </table>
      </div>
    </div>
  `;

  if (canWrite) {
    document.getElementById("create-camp-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await apiRequest("/blood-camps", {
          method: "POST",
          body: {
            camp_code: f.camp_code.value.trim(),
            title: f.title.value.trim(),
            organizer_blood_bank_id: f.organizer_blood_bank_id.value.trim(),
            address: f.address.value.trim(),
            location: { type: "Point", coordinates: [Number(f.longitude.value), Number(f.latitude.value)] },
            start_time: new Date(f.start_time.value).toISOString(),
            end_time: new Date(f.end_time.value).toISOString(),
          },
        });
        showToast("Blood camp created.", "success");
        await loadTab("camps");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }

  document.getElementById("nearby-camp-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      const nearby = await apiRequest(
        `/blood-camps/nearby?longitude=${f.longitude.value}&latitude=${f.latitude.value}&radius_km=${f.radius_km.value}`
      );
      document.getElementById("camps-tbody").innerHTML = renderCampRows(nearby);
    } catch (err) {
      showToast(err.message, "error");
    }
  });
  document.getElementById("reset-camps-btn").addEventListener("click", () => loadTab("camps"));
}

function renderCampRows(camps) {
  if (!camps.length) return `<tr><td colspan="6" class="text-muted">No blood camps found.</td></tr>`;
  return camps
    .map(
      (c) => `
    <tr>
      <td><strong>${escapeHtml(c.camp_code)}</strong></td>
      <td>${escapeHtml(c.title)}</td>
      <td>${escapeHtml(c.address)}</td>
      <td>${formatDate(c.start_time)}</td>
      <td>${c.distance_km !== null && c.distance_km !== undefined ? `${escapeHtml(c.distance_km)} km` : "—"}</td>
      <td>${badgeForStatus(c.status)}</td>
    </tr>`
    )
    .join("");
}

// ==========================================
// 8. Hospitals, Users & RBAC, Audit Logs, Notifications
// ==========================================

async function renderHospitals(container) {
  const hospitals = await apiRequest("/hospitals");
  const isAdmin = currentUser.role === "ADMIN";
  container.innerHTML = `
    ${
      isAdmin
        ? `
      <div class="card">
        <div class="card-header"><h3 class="card-title">Register Hospital Facility</h3></div>
        <form id="create-hosp-form" class="form-grid">
          <div class="form-group"><label>Hospital Name</label><input name="name" required></div>
          <div class="form-group"><label>License #</label><input name="license_number" required></div>
          <div class="form-group"><label>Longitude</label><input type="number" step="any" name="longitude" value="77.6" required></div>
          <div class="form-group"><label>Latitude</label><input type="number" step="any" name="latitude" value="12.97" required></div>
          <div class="form-group"><label>Address (Encrypted)</label><input name="address" required></div>
          <div class="form-group"><label>Helpline (Encrypted)</label><input name="emergency_helpline" required></div>
          <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Register Hospital</button></div>
        </form>
      </div>`
        : ""
    }
    <div class="card">
      <div class="card-header"><h3 class="card-title">Registered Hospitals (${hospitals.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>License</th><th>Address (Decrypted)</th><th>Helpline</th><th>Status</th></tr></thead>
          <tbody>
            ${
              hospitals.length
                ? hospitals
                    .map(
                      (h) =>
                        `<tr><td><strong>${escapeHtml(h.name)}</strong></td><td>${escapeHtml(h.license_number)}</td><td>${escapeHtml(h.address || "—")}</td><td>${escapeHtml(h.emergency_helpline || "—")}</td><td>${badgeForStatus(h.verification_status)}</td></tr>`
                    )
                    .join("")
                : `<tr><td colspan="5" class="text-muted">No hospitals registered.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
  if (isAdmin) {
    document.getElementById("create-hosp-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await apiRequest("/hospitals", {
          method: "POST",
          body: {
            name: f.name.value.trim(),
            license_number: f.license_number.value.trim(),
            location: { type: "Point", coordinates: [Number(f.longitude.value), Number(f.latitude.value)] },
            address: f.address.value.trim(),
            emergency_helpline: f.emergency_helpline.value.trim(),
          },
        });
        showToast("Hospital registered.", "success");
        await loadTab("hospitals");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }
}

async function renderUsersAndRoles(container) {
  const [users, roles] = await Promise.all([apiRequest("/users"), apiRequest("/roles")]);
  container.innerHTML = `
    <div class="card">
      <div class="card-header"><h3 class="card-title">Create System User (Admin)</h3></div>
      <form id="admin-user-form" class="form-grid">
        <div class="form-group"><label>Username</label><input name="username" required></div>
        <div class="form-group"><label>Email</label><input type="email" name="email" required></div>
        <div class="form-group"><label>Password</label><input type="password" name="password" minlength="8" required></div>
        <div class="form-group"><label>Role</label><select name="role"><option>ADMIN</option><option>BLOOD_BANK_STAFF</option><option>HOSPITAL_STAFF</option><option>DOCTOR</option><option>DONOR</option></select></div>
        <div class="form-group"><label>Hospital ID (optional)</label><input name="hospital_id"></div>
        <div class="form-group"><label>Blood Bank ID (optional)</label><input name="blood_bank_id"></div>
        <div class="form-group" style="grid-column:1/-1;"><button class="btn btn-primary" type="submit">Create User</button></div>
      </form>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">System Users (${users.length})</h3></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Username</th><th>Email (Decrypted)</th><th>Role</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            ${users
              .map(
                (u) => `
              <tr>
                <td><strong>${escapeHtml(u.username)}</strong></td>
                <td>${escapeHtml(u.email || "—")}</td>
                <td>${badgeForStatus(u.role)}</td>
                <td>${badgeForStatus(u.is_active ? "ACTIVE" : "REJECTED")}</td>
                <td><button class="btn btn-secondary btn-sm toggle-active-btn" data-id="${escapeHtml(u._id)}" data-next="${!u.is_active}">${u.is_active ? "Deactivate" : "Activate"}</button></td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">RBAC Roles & Permissions</h3>
        <button id="seed-roles-btn" class="btn btn-secondary btn-sm">Reset Default Matrix</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Role</th><th>Description</th><th>Permissions</th></tr></thead>
          <tbody>
            ${roles
              .map(
                (r) =>
                  `<tr><td><strong>${escapeHtml(r.role_name)}</strong></td><td>${escapeHtml(r.description)}</td><td>${r.permissions.map((p) => `<span class="badge badge-neutral" style="margin:2px;">${escapeHtml(p)}</span>`).join("")}</td></tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("admin-user-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await apiRequest("/users", {
        method: "POST",
        body: {
          username: f.username.value.trim(),
          email: f.email.value.trim(),
          password: f.password.value,
          role: f.role.value,
          hospital_id: f.hospital_id.value.trim() || null,
          blood_bank_id: f.blood_bank_id.value.trim() || null,
        },
      });
      showToast("User created.", "success");
      await loadTab("users");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  container.querySelectorAll(".toggle-active-btn").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await apiRequest(`/users/${btn.dataset.id}`, {
          method: "PUT",
          body: { is_active: btn.dataset.next === "true" },
        });
        showToast("User status updated.", "success");
        await loadTab("users");
      } catch (err) {
        showToast(err.message, "error");
      }
    })
  );

  document.getElementById("seed-roles-btn").addEventListener("click", async () => {
    try {
      await apiRequest("/roles/seed", { method: "POST" });
      showToast("RBAC matrix reset to defaults.", "success");
      await loadTab("users");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

async function renderAuditLogs(container) {
  const logs = await apiRequest("/audit?limit=100");
  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Security Audit Log Viewer (${logs.length})</h3>
        <form id="audit-filter-form" class="flex-row">
          <input name="action" placeholder="Action (e.g. ACCESS_DENIED)" style="width:200px;">
          <select name="status" style="width:140px;"><option value="">All Status</option><option>SUCCESS</option><option>FAILURE</option><option>DENIED</option></select>
          <button class="btn btn-primary btn-sm" type="submit">Filter</button>
        </form>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Event ID</th><th>Timestamp</th><th>Actor</th><th>Action</th><th>Resource</th><th>Status</th><th>Metadata</th></tr></thead>
          <tbody id="audit-tbody">
            ${renderAuditRows(logs)}
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("audit-filter-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const params = new URLSearchParams({ limit: "100" });
    if (e.target.action.value.trim()) params.set("action", e.target.action.value.trim());
    if (e.target.status.value) params.set("status", e.target.status.value);
    const filtered = await apiRequest(`/audit?${params.toString()}`);
    document.getElementById("audit-tbody").innerHTML = renderAuditRows(filtered);
  });
}

function renderAuditRows(logs) {
  if (!logs.length) return `<tr><td colspan="7" class="text-muted">No audit events match filter.</td></tr>`;
  return logs
    .map(
      (l) => `
    <tr>
      <td><code>${escapeHtml(l.event_id)}</code></td>
      <td>${formatDate(l.timestamp)}</td>
      <td>${escapeHtml(l.actor?.username || "anonymous")} (${escapeHtml(l.actor?.role || "—")})</td>
      <td><strong>${escapeHtml(l.action)}</strong></td>
      <td>${escapeHtml(l.resource_type)} ${l.resource_id ? `(${escapeHtml(l.resource_id)})` : ""}</td>
      <td>${badgeForStatus(l.status)}</td>
      <td><code style="font-size:11px;">${escapeHtml(JSON.stringify(l.metadata || {}))}</code></td>
    </tr>`
    )
    .join("");
}

async function renderNotifications(container) {
  const notifications = await apiRequest("/notifications");
  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">My Notifications (${notifications.length})</h3>
        <button id="mark-all-read-btn" class="btn btn-secondary btn-sm">Mark All Read</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Type</th><th>Title</th><th>Message</th><th>Received</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            ${
              notifications.length
                ? notifications
                    .map(
                      (n) => `
                  <tr>
                    <td>${badgeForStatus(n.notification_type === "EMERGENCY_REQUEST" ? "CRITICAL" : "INFO")}</td>
                    <td><strong>${escapeHtml(n.title)}</strong></td>
                    <td>${escapeHtml(n.message)}</td>
                    <td>${formatDate(n.created_at)}</td>
                    <td>${n.is_read ? badgeForStatus("SUCCESS") : badgeForStatus("PENDING")}</td>
                    <td>${!n.is_read ? `<button class="btn btn-primary btn-sm mark-read-btn" data-id="${escapeHtml(n._id)}">Mark Read</button>` : "—"}</td>
                  </tr>`
                    )
                    .join("")
                : `<tr><td colspan="6" class="text-muted">No notifications yet.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("mark-all-read-btn").addEventListener("click", async () => {
    await apiRequest("/notifications/read-all", { method: "POST" });
    await refreshUnreadBadge();
    await loadTab("notifications");
  });

  container.querySelectorAll(".mark-read-btn").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await apiRequest(`/notifications/${btn.dataset.id}/read`, { method: "PATCH" });
      await refreshUnreadBadge();
      await loadTab("notifications");
    })
  );
}
