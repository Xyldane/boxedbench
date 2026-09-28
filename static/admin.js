/* Live previews in admin forms (no animation, just re-render on input). */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("textarea[data-preview]").forEach((ta) => {
    const out = document.getElementById(ta.dataset.preview);
    const update = () => { out.dataset.src = ta.value; Boxed.renderRich(out); };
    ta.addEventListener("input", update);
    update();
  });
  document.querySelectorAll("input[data-boxed]").forEach((inp) => {
    const out = document.getElementById(inp.dataset.boxed);
    const update = () => { out.dataset.answer = inp.value; Boxed.renderBoxed(out); };
    inp.addEventListener("input", update);
    update();
  });
  document.querySelectorAll("input[data-boxed-ok]").forEach((cb) => {
    const out = document.getElementById(cb.dataset.boxedOk);
    cb.addEventListener("change", () => { out.dataset.ok = cb.checked ? "1" : "0"; Boxed.renderBoxed(out); });
  });
});
