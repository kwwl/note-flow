let supabaseClient = null;
let currentSession = null; // session stockée de façon synchrone pour HTMX

async function initSupabase() {
  const res = await fetch("/api/config");
  const { supabase_url, supabase_anon_key } = await res.json();
  supabaseClient = supabase.createClient(supabase_url, supabase_anon_key);
  checkAuthState();
}

async function checkAuthState() {
  const {
    data: { session },
  } = await supabaseClient.auth.getSession();
  currentSession = session;
  if (session) {
    await showApp(session.user);
  } else {
    showAuth();
  }

  supabaseClient.auth.onAuthStateChange(async (_event, session) => {
    currentSession = session; // mise à jour synchrone
    if (session) {
      await showApp(session.user);
    } else {
      showAuth();
    }
  });
}

function showAuth() {
  document.getElementById("auth-section").hidden = false;
  document.getElementById("app-section").hidden = true;
}

async function showApp(user) {
  document.getElementById("auth-section").hidden = true;
  document.getElementById("app-section").hidden = false;

  const { data: profile } = await supabaseClient
    .from("profiles")
    .select("nom, prenom")
    .eq("id", user.id)
    .maybeSingle();

  const display = profile ? `${profile.prenom} ${profile.nom}` : user.email;

  document.getElementById("user-display").textContent = display;

  loadHistory();
}

async function loadHistory() {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) return;
  const res = await fetch("/api/history", {
    headers: { "Authorization": `Bearer ${session.access_token}` }
  });
  const html = await res.text();
  document.getElementById("history-container").innerHTML = html;
}

function switchTab(tab) {
  const isLogin = tab === "login";
  document.getElementById("login-form").hidden = !isLogin;
  document.getElementById("signup-form").hidden = isLogin;
  document.getElementById("tab-login").classList.toggle("active", isLogin);
  document.getElementById("tab-signup").classList.toggle("active", !isLogin);
  document.getElementById("auth-error").style.display = "none";
}

function showAuthError(msg) {
  const el = document.getElementById("auth-error");
  el.textContent = msg;
  el.style.display = "block";
  el.style.background = "rgba(231,76,60,0.1)";
  el.style.borderColor = "rgba(231,76,60,0.3)";
  el.style.color = "var(--error)";
}

async function handleLogin() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;

  const { error } = await supabaseClient.auth.signInWithPassword({
    email,
    password,
  });
  if (error) { showAuthError(error.message); return; }

  // Affiche le message de confirmation email
  const el = document.getElementById("auth-error");
  el.textContent = "✅ Un email de confirmation vient de vous être envoyé. Veuillez consulter votre boîte mail et cliquer sur le lien de validation pour activer votre compte.";
  el.style.display = "block";
  el.style.background = "rgba(46,204,113,0.1)";
  el.style.borderColor = "rgba(46,204,113,0.3)";
  el.style.color = "#2ecc71";
}

async function handleSignup() {
  const nom = document.getElementById("signup-nom").value.trim();
  const prenom = document.getElementById("signup-prenom").value.trim();
  const email = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value;

  if (!nom || !prenom) {
    showAuthError("Veuillez renseigner votre nom et prénom.");
    return;
  }

  const { error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: { data: { nom, prenom } },
  });

  if (error) {
    showAuthError(error.message);
  } else {
    const el = document.getElementById("auth-error");
    el.textContent = "✉️ Un email de confirmation vient de vous être envoyé. Veuillez consulter votre boîte mail et cliquer sur le lien de validation pour activer votre compte.";
    el.style.display = "block";
    el.style.background = "rgba(46,204,113,0.1)";
    el.style.borderColor = "rgba(46,204,113,0.3)";
    el.style.color = "#2ecc71";
  }
}

async function handleLogout() {
  await supabaseClient.auth.signOut();
  resetApp();
}

document.body.addEventListener("htmx:configRequest", (e) => {
  if (currentSession?.access_token) {
    e.detail.headers["Authorization"] = `Bearer ${currentSession.access_token}`;
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.getElementById("file-input");
  const preview = document.getElementById("preview");
  const previewContainer = document.getElementById("preview-container");
  const fileName = document.getElementById("file-name");
  const analyzeBtn = document.getElementById("analyze-btn");
  const dropZone = document.getElementById("drop-zone");

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    preview.src = url;
    preview.onload = () => URL.revokeObjectURL(url);
    fileName.textContent = file.name;
    previewContainer.style.display = "block";
    analyzeBtn.disabled = false;

    const reader = new FileReader();
    reader.onload = (e) => {
      window._imageBase64 = e.target.result.split(",")[1];
    };
    reader.readAsDataURL(file);
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () =>
    dropZone.classList.remove("dragover"),
  );

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("change"));
  });

  document.body.addEventListener("htmx:beforeRequest", (e) => {
    if (e.detail.elt.id === "upload-form") {
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = "Analyse en cours…";
    }
  });
});

document.body.addEventListener("htmx:afterSwap", (e) => {
  if (e.detail.target.id === "result") {
    document.getElementById("reset-btn").style.display = "block";
    e.detail.target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // Rafraîchit l'historique après un submit réussi
    if (e.detail.requestConfig?.path === "/api/submit") loadHistory();
  }
});

document.body.addEventListener("htmx:responseError", (e) => {
  const result = document.getElementById("result");
  result.innerHTML = e.detail.xhr.responseText;
  document.getElementById("reset-btn").style.display = "block";
  result.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

function resetApp() {
  const fileInput = document.getElementById("file-input");
  const analyzeBtn = document.getElementById("analyze-btn");
  const preview = document.getElementById("preview");
  const previewContainer = document.getElementById("preview-container");

  if (fileInput) fileInput.value = "";
  if (preview) preview.src = "";
  if (previewContainer) previewContainer.style.display = "none";
  if (analyzeBtn) {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyser la note de frais";
  }

  const result = document.getElementById("result");
  if (result) result.innerHTML = "";

  const resetBtn = document.getElementById("reset-btn");
  if (resetBtn) resetBtn.style.display = "none";

  window._imageBase64 = null;
}

initSupabase();
