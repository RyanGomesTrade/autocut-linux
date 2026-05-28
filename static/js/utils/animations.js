export function pulse(el, { durationMs = 350 } = {}) {
  if (!el) return;
  el.animate(
    [
      { transform: "scale(1)", opacity: 1 },
      { transform: "scale(1.03)", opacity: 0.9 },
      { transform: "scale(1)", opacity: 1 },
    ],
    { duration: durationMs, easing: "ease-out" }
  );
}

