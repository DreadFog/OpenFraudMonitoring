function getToken() {
  return localStorage.getItem("ofm_token");
}

function authHeaders(extra = {}) {
  const token = getToken();
  const headers = { ...extra };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function authFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
  if (res.status === 401) {
    localStorage.removeItem("ofm_token");
    localStorage.removeItem("ofm_user");
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}
