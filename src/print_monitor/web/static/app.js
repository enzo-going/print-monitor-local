document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  const confirmation = form.dataset.confirm;
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }

  const loadingLabel = form.dataset.loading;
  if (!loadingLabel) return;
  const button = form.querySelector("button[type='submit']");
  if (!(button instanceof HTMLButtonElement) || button.disabled) {
    event.preventDefault();
    return;
  }
  button.disabled = true;
  button.dataset.originalLabel = button.textContent || "";
  button.textContent = loadingLabel;
});
