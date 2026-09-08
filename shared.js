// shared.js
// -----------------------------------------------------------------------
// Used by risks.html, recoveries.html, and audit.html. Kept separate from
// dashboard.html's own inline script since dashboard.html still works as
// a static export (for Vercel) with no live API — these three new pages
// are live-API-only and share this file instead.

// Same ₹ formatter as dashboard.html's inline script — duplicated once
// (not imported) since dashboard.html intentionally has zero <script src>
// dependencies so it keeps working as a plain static file with no server.
function inr(n) {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

// Escapes HTML special characters before text goes into innerHTML. The
// synthetic reasoning/reply text in this project is never attacker-
// controlled today, but diagnosis_reasoning and intervention_reasoning
// both come from an LLM call once --ai is used — treating ANY text that
// didn't originate as a hardcoded string in this codebase as "could
// contain markup" is the defensible default, not a today-specific fix.
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// Thin wrapper around fetch() for this project's JSON API: throws with a
// readable message on a non-2xx response instead of letting the caller
// try to .json() an HTML error page and get a confusing parse error
// three lines away from the actual problem.
async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.description || detail;
    } catch { /* body wasn't JSON, fall back to statusText */ }
    throw new Error(`${res.status} ${path}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

// POST helper that always attaches the X-Requested-With header the API's
// require_ajax_header decorator checks for (see api_server.py) — every
// state-changing call in this project's frontend goes through this
// function so that header is never forgotten on one page and not another.
async function apiPost(path, body) {
  return api(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}
