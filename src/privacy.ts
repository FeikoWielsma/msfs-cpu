const status = document.getElementById("analyticsStatus")!;
const disable = document.getElementById("disableAnalytics") as HTMLButtonElement;
const enable = document.getElementById("enableAnalytics") as HTMLButtonElement;

function storageUnavailable() {
  status.textContent = "Your browser blocked saving this preference. Use your browser's Do Not Track setting or content blocker instead.";
  disable.disabled = true;
  enable.disabled = true;
}

function showPreference() {
  try {
    const optedOut = !!localStorage.getItem("umami.disabled");
    status.textContent = optedOut
      ? "Analytics is disabled in this browser for this site."
      : "No analytics opt-out is saved in this browser. Browser Do Not Track is also respected.";
    disable.disabled = optedOut;
    enable.disabled = !optedOut;
  } catch {
    storageUnavailable();
  }
}

disable.addEventListener("click", () => {
  try { localStorage.setItem("umami.disabled", "1"); } catch { storageUnavailable(); return; }
  showPreference();
});
enable.addEventListener("click", () => {
  try { localStorage.removeItem("umami.disabled"); } catch { storageUnavailable(); return; }
  showPreference();
});
showPreference();
