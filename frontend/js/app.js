import { submitValuation } from "./api.js";
import { createAddressPicker } from "./address-picker.js";
import { renderResults } from "./results-view.js";

const PROGRESS_STEPS = [
  { afterMs: 0, text: "Buscando comparables en la misma calle…" },
  { afterMs: 12000, text: "Ampliando a la microzona para conseguir más referencias…" },
  { afterMs: 24000, text: "Si hace falta, abrimos a distrito y municipio…" },
];

let progressInterval = null;

function showError(message) {
  document.getElementById("errorMsg").textContent = `Error: ${message}`;
  document.getElementById("errorBox").classList.remove("hidden");
}

function hideError() {
  document.getElementById("errorBox").classList.add("hidden");
}

function startProgressUI() {
  const progressBox = document.getElementById("progressBox");
  const progressMsg = document.getElementById("progressMsg");
  const startedAt = Date.now();

  progressBox.classList.remove("hidden");
  progressMsg.textContent = PROGRESS_STEPS[0].text;

  progressInterval = window.setInterval(() => {
    const elapsed = Date.now() - startedAt;
    let currentStep = PROGRESS_STEPS[0];
    for (const step of PROGRESS_STEPS) {
      if (elapsed >= step.afterMs) currentStep = step;
    }
    progressMsg.textContent = currentStep.text;
  }, 500);
}

function stopProgressUI() {
  document.getElementById("progressBox").classList.add("hidden");
  if (progressInterval) {
    window.clearInterval(progressInterval);
    progressInterval = null;
  }
}

function resetResults() {
  document.getElementById("results").classList.add("hidden");
  document.getElementById("searchMeta").classList.add("hidden");
}

function toggleSubmit(isLoading) {
  const button = document.getElementById("submitBtn");
  const spinner = document.getElementById("btnSpinner");
  const label = document.getElementById("btnText");

  button.disabled = isLoading;
  spinner.classList.toggle("hidden", !isLoading);
  label.textContent = isLoading ? "Buscando comparables…" : "Estimar valor";
}

window.addEventListener("DOMContentLoaded", () => {
  const addressPicker = createAddressPicker({
    input: document.getElementById("address"),
    suggestionsBox: document.getElementById("addressSuggestions"),
    selectedBox: document.getElementById("selectedAddressBox"),
    selectedText: document.getElementById("selectedAddressText"),
    mapElement: document.getElementById("addressMap"),
    onError: (error) => showError(error.message),
  });

  document.getElementById("valuationForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    hideError();
    resetResults();
    startProgressUI();
    toggleSubmit(true);

    const selectedAddress = addressPicker.getSelectedAddress();
    const payload = {
      address: document.getElementById("address").value.trim(),
      m2: Number.parseInt(document.getElementById("m2").value, 10),
      bedrooms: Number.parseInt(document.getElementById("bedrooms").value, 10),
      bathrooms: Number.parseInt(document.getElementById("bathrooms").value, 10),
      selected_address: selectedAddress,
    };

    try {
      const data = await submitValuation(payload);
      renderResults(data, payload);
    } catch (error) {
      showError(error.message);
    } finally {
      stopProgressUI();
      toggleSubmit(false);
    }
  });
});
