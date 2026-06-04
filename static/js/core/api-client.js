export function createApiClient({ baseUrl = "" } = {}) {
  async function requestJson(path, { method = "GET", body = undefined } = {}) {
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // Try parse error payload for better operator feedback
    const text = await res.text();
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = null;
    }

    if (!res.ok) {
      const msg =
        (json && (json.message || json.error)) ||
        text ||
        `HTTP ${res.status} ${res.statusText}`;
      throw new Error(msg);
    }
    return json;
  }

  return {
    getJson: (path) => requestJson(path),
    postJson: (path, body) => requestJson(path, { method: "POST", body }),
    putJson: (path, body) => requestJson(path, { method: "PUT", body }),
    deleteJson: (path, body) => requestJson(path, { method: "DELETE", body }),
  };
}

