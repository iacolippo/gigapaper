const overlay = document.getElementById("modal-overlay");
const messageEl = document.getElementById("modal-message");
const inputEl = document.getElementById("modal-input");
const confirmBtn = document.getElementById("modal-confirm");
const cancelBtn = document.getElementById("modal-cancel");

function open(message, { showInput, defaultValue, hideCancel } = {}) {
  return new Promise((resolve) => {
    messageEl.textContent = message;
    inputEl.classList.toggle("hidden", !showInput);
    inputEl.value = defaultValue || "";
    cancelBtn.classList.toggle("hidden", !!hideCancel);
    overlay.classList.remove("hidden");
    if (showInput) inputEl.focus();

    const cleanup = (result) => {
      overlay.classList.add("hidden");
      cancelBtn.classList.remove("hidden");
      confirmBtn.onclick = null;
      cancelBtn.onclick = null;
      inputEl.onkeydown = null;
      resolve(result);
    };

    confirmBtn.onclick = () => cleanup(showInput ? inputEl.value.trim() || null : true);
    cancelBtn.onclick = () => cleanup(showInput ? null : false);
    inputEl.onkeydown = (e) => {
      if (e.key === "Enter") cleanup(inputEl.value.trim() || null);
      if (e.key === "Escape") cleanup(null);
    };
  });
}

export const showPrompt = (message, defaultValue) => open(message, { showInput: true, defaultValue });
export const showConfirm = (message) => open(message, { showInput: false });
export const showAlert = (message) => open(message, { showInput: false, hideCancel: true });
