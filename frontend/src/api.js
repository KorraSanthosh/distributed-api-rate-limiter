// All requests go through the same origin: Vite's dev proxy or nginx in Docker.
export async function fetchSummary(windowSeconds, signal) {
  const res = await fetch(`/api/v1/analytics/summary?window_seconds=${windowSeconds}`, { signal });
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}
