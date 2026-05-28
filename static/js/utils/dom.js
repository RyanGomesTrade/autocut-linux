export const dom = {
  qs: (sel, root = document) => root.querySelector(sel),
  qsa: (sel, root = document) => Array.from(root.querySelectorAll(sel)),
  setText: (el, text) => {
    if (!el) return;
    el.textContent = text ?? "";
  },
  clear: (el) => {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  },
};

