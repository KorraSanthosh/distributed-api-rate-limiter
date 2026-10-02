export const fmtInt = (n) => Math.round(n).toLocaleString();
export const fmtTime = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour12: false });
export const fmtClock = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export const METHOD_CLASS = { GET: "m-get", POST: "m-post", PUT: "m-put", DELETE: "m-del" };

export function statusTone(code) {
  if (code >= 500) return "bad";
  if (code === 429) return "blocked";
  if (code >= 400) return "warn";
  return "ok";
}
