export function fmtInt(v, fallback = "--") {
  if (v === null || v === undefined || Number.isNaN(v)) return fallback;
  return String(Math.round(v));
}

export function fmtPct01(v, fallback = "--") {
  if (v === null || v === undefined || Number.isNaN(v)) return fallback;
  return `${(v * 100).toFixed(0)}%`;
}

export function fmtX(v, fallback = "--") {
  if (v === null || v === undefined || Number.isNaN(v)) return fallback;
  return `${Number(v).toFixed(1)}x`;
}

export function fmtScore100(v, fallback = "--") {
  if (v === null || v === undefined || Number.isNaN(v)) return fallback;
  return `${(v * 100).toFixed(0)}`;
}

