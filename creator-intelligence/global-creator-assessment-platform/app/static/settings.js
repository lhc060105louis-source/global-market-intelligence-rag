"use strict";

async function loadYoutubeSettings() {
  const result = await api("/settings/youtube");
  const validity = result.valid === true ? "Valid" : result.valid === false ? "Invalid" : "Not verified";
  document.getElementById("settings-key-status").textContent = result.configured ? `✓ Configured · ${validity}` : "Not configured";
}

async function saveYoutubeKey(event) {
  event.preventDefault();
  const input = document.getElementById("settings-apikey");
  await api("/settings/youtube", {method: "PUT", body: JSON.stringify({api_key: input.value.trim()})});
  input.value = "";
  await loadYoutubeSettings();
  showStatus("YouTube API key saved securely.");
}

async function deleteYoutubeKey() {
  await api("/settings/youtube", {method: "DELETE"});
  document.getElementById("settings-apikey").value = "";
  await loadYoutubeSettings();
  showStatus("YouTube API key cleared.");
}

async function loadSupabaseSettings() {
  const result = await api("/settings/supabase");
  document.getElementById("supabase-status").textContent = result.configured
    ? "✓ Team sharing enabled"
    : "Not configured";
  document.getElementById("supabase-url").value = result.url || "";
}

async function saveSupabaseSettings(event) {
  event.preventDefault();
  const payload = {
    url: document.getElementById("supabase-url").value.trim(),
    anon_key: document.getElementById("supabase-anon-key").value.trim(),
    access_token: document.getElementById("supabase-access-token").value.trim(),
  };
  await api("/settings/supabase", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  document.getElementById("supabase-anon-key").value = "";
  document.getElementById("supabase-access-token").value = "";
  await loadSupabaseSettings();
  await loadSyncStatus();
  showStatus("Supabase team sharing enabled securely.");
}
