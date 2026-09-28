/* Rendering helpers: LaTeX in text, and the \boxed{} answer display.
 *
 *   correct answer -> \boxed{answer} rendered normally by KaTeX
 *   wrong answer   -> "\boxed{" and "}" left as raw red source text, as if only
 *                     the \boxed command failed to render; the answer inside is
 *                     still rendered (in red).
 */
(function () {
  const KATEX_OPTS = { throwOnError: false, errorColor: "#ff6b6b", strict: "ignore" };

  function tex(src, el, display) {
    try {
      katex.render(src, el, Object.assign({ displayMode: !!display }, KATEX_OPTS));
    } catch (e) {
      el.textContent = src;
    }
  }

  function renderBoxed(el) {
    const ans = el.dataset.answer || "";
    const ok = el.dataset.ok === "1";
    el.textContent = "";
    el.classList.remove("ok", "fail");
    if (ok) {
      el.classList.add("ok");
      tex("\\boxed{" + ans + "}", el);
      return;
    }
    el.classList.add("fail");
    const open = document.createElement("span");
    open.className = "lit";
    open.textContent = "\\boxed{";
    const inner = document.createElement("span");
    inner.className = "inner";
    if (ans.trim()) tex(ans, inner);
    const close = document.createElement("span");
    close.className = "lit";
    close.textContent = "}";
    el.append(open, inner, close);
  }

  // Plain text with $..$, $$..$$, \(..\), \[..\] math, ```code fences``` and `inline code`.
  function renderRich(el) {
    const src = el.dataset.src !== undefined ? el.dataset.src : el.textContent;
    el.dataset.src = src;
    el.textContent = "";
    const fence = /```[^\n]*\n?([\s\S]*?)```/g;
    let last = 0, m;
    const pushText = (s) => {
      s.split(/(`[^`\n]+`)/).forEach((part, i) => {
        if (i % 2) {
          const c = document.createElement("code");
          c.textContent = part.slice(1, -1);
          el.append(c);
        } else if (part) {
          el.append(document.createTextNode(part));
        }
      });
    };
    while ((m = fence.exec(src))) {
      pushText(src.slice(last, m.index));
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = m[1].replace(/\n$/, "");
      pre.append(code);
      el.append(pre);
      last = fence.lastIndex;
    }
    pushText(src.slice(last));
    if (window.renderMathInElement) {
      renderMathInElement(el, Object.assign({
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
        ],
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
      }, KATEX_OPTS));
    }
  }

  function renderAll(root) {
    root = root || document;
    root.querySelectorAll(".rich").forEach(renderRich);
    root.querySelectorAll(".bx").forEach(renderBoxed);
    root.querySelectorAll("[data-tex]").forEach((el) => tex(el.dataset.tex, el));
    // short bits of prose with inline $..$ math
    if (window.renderMathInElement) {
      root.querySelectorAll(".tex-auto").forEach((el) => renderMathInElement(el, Object.assign({
        delimiters: [{ left: "$", right: "$", display: false }],
      }, KATEX_OPTS)));
    }
  }

  window.Boxed = { tex, renderBoxed, renderRich, renderAll };

  document.addEventListener("DOMContentLoaded", () => {
    renderAll();
    document.querySelectorAll(".answer-reveal").forEach((el) =>
      el.addEventListener("click", () => el.classList.toggle("shown")));
  });
})();
