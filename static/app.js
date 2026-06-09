const fileInput = document.getElementById("file-input");
const previewContainer = document.getElementById("preview-container");
const preview = document.getElementById("preview");
const fileName = document.getElementById("file-name");
const analyzeBtn = document.getElementById("analyze-btn");
const dropZone = document.getElementById("drop-zone");
const resetBtn = document.getElementById("reset-btn");
const resultContainer = document.getElementById("result");

// Prévisualisation + encodage base64 à la sélection du fichier
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;

  // Prévisualisation (libère l'URL objet après chargement)
  const url = URL.createObjectURL(file);
  preview.src = url;
  preview.onload = () => URL.revokeObjectURL(url);

  fileName.textContent = file.name;
  previewContainer.style.display = "block";
  analyzeBtn.disabled = false;

  // Encodage base64 pour injection éventuelle côté client
  const reader = new FileReader();
  reader.onload = (e) => {
    // Stocké sur l'objet window pour usage futur si besoin
    window._imageBase64 = e.target.result.split(",")[1];
  };
  reader.readAsDataURL(file);
});

// Drag & drop
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (!file) return;

  // Injecter dans l'input pour que HTMX puisse le soumettre
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  fileInput.dispatchEvent(new Event("change"));
});

// Désactiver le bouton pendant la requête d'analyse
document.body.addEventListener("htmx:beforeRequest", (e) => {
  if (e.detail.elt.id === "upload-form") {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyse en cours…";
  }
});

// Après un swap réussi : afficher reset + scroller vers le résultat
document.body.addEventListener("htmx:afterSwap", (e) => {
  if (e.detail.target.id === "result") {
    resetBtn.style.display = "block";
    resultContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
});

// HTMX ne swape pas sur les réponses 4xx/5xx par défaut — on le fait manuellement
document.body.addEventListener("htmx:responseError", (e) => {
  const fragment = e.detail.xhr.responseText;
  resultContainer.innerHTML = fragment;
  resetBtn.style.display = "block";
  resultContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

function resetApp() {
  fileInput.value = "";
  preview.src = "";
  previewContainer.style.display = "none";
  fileName.textContent = "";
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyser la note de frais";
  window._imageBase64 = null;

  resultContainer.innerHTML = "";
  resetBtn.style.display = "none";
}
