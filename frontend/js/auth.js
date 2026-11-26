/**
 * Authentication & Role-Based Route Guards.
 */
import { apiRequest, clearSession, getStoredUser, getToken, setSession } from "./api.js";
import { showToast } from "./ui.js";

export const ROLE_ROUTES = {
  ADMIN: "/ui/admin/index.html",
  BLOOD_BANK_STAFF: "/ui/bloodbank/index.html",
  HOSPITAL_STAFF: "/ui/hospital/index.html",
  DOCTOR: "/ui/doctor/index.html",
  DONOR: "/ui/donor/index.html",
};

export function routeForRole(role) {
  return ROLE_ROUTES[role] || "/ui/login.html";
}

export async function requireAuth(expectedRole = null) {
  const token = getToken();
  if (!token) {
    window.location.href = "/ui/login.html";
    return null;
  }
  try {
    const me = await apiRequest("/auth/me");
    localStorage.setItem("sbb_current_user", JSON.stringify(me));
    if (expectedRole && me.role !== expectedRole) {
      window.location.href = routeForRole(me.role);
      return null;
    }
    return me;
  } catch {
    clearSession();
    window.location.href = "/ui/login.html";
    return null;
  }
}

export async function handleLogout() {
  try {
    await apiRequest("/auth/logout", { method: "POST", skipAuthRedirect: true });
  } catch {
    // Token may already be expired; clear local session regardless
  } finally {
    clearSession();
    window.location.href = "/ui/login.html";
  }
}

export function initLoginPage() {
  const existing = getStoredUser();
  if (getToken() && existing?.role) {
    window.location.href = routeForRole(existing.role);
    return;
  }
  const form = document.getElementById("login-form");
  const alertBox = document.getElementById("auth-alert");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    alertBox.className = "hidden";
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in...";

    try {
      const payload = {
        username: form.username.value.trim(),
        password: form.password.value,
      };
      const res = await apiRequest("/auth/login", {
        method: "POST",
        body: payload,
        skipAuthRedirect: true,
      });
      setSession(res.access_token, res.user);
      showToast(`Welcome, ${res.user.username}!`, "success");
      window.location.href = routeForRole(res.user.role);
    } catch (err) {
      alertBox.textContent = err.message;
      alertBox.className = "alert alert-error";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign In";
    }
  });
}

export function initRegisterPage() {
  const form = document.getElementById("register-form");
  const alertBox = document.getElementById("auth-alert");
  if (!form) return;

  const roleSelect = form.role;
  const hospWrap = document.getElementById("hospital-scope-wrap");
  const bbWrap = document.getElementById("bloodbank-scope-wrap");

  const syncScopeVisibility = () => {
    const r = roleSelect.value;
    hospWrap.classList.toggle("hidden", r !== "HOSPITAL_STAFF" && r !== "DOCTOR");
    bbWrap.classList.toggle("hidden", r !== "BLOOD_BANK_STAFF");
  };
  roleSelect.addEventListener("change", syncScopeVisibility);
  syncScopeVisibility();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    alertBox.className = "hidden";
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating Account...";

    try {
      const payload = {
        username: form.username.value.trim(),
        email: form.email.value.trim(),
        password: form.password.value,
        role: form.role.value,
        hospital_id: form.hospital_id.value.trim() || null,
        blood_bank_id: form.blood_bank_id.value.trim() || null,
      };
      await apiRequest("/auth/register", {
        method: "POST",
        body: payload,
        skipAuthRedirect: true,
      });
      alertBox.textContent = "Registration successful! Redirecting to login...";
      alertBox.className = "alert alert-success";
      setTimeout(() => {
        window.location.href = "/ui/login.html";
      }, 1000);
    } catch (err) {
      alertBox.textContent = err.message;
      alertBox.className = "alert alert-error";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Create Account";
    }
  });
}
