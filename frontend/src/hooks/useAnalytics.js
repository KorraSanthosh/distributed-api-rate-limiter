import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSummary } from "../api.js";

/** Polls the analytics summary. Keeps the last good data visible if a poll fails. */
export function useAnalytics({ windowSeconds, paused, intervalMs = 2000 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const inflight = useRef(null);

  const load = useCallback(async () => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    try {
      const summary = await fetchSummary(windowSeconds, controller.signal);
      setData(summary);
      setError(null);
      setLastUpdated(Date.now());
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message || "Request failed");
    } finally {
      if (inflight.current === controller) setLoading(false);
    }
  }, [windowSeconds]);

  useEffect(() => {
    setLoading(true);
    load();
    if (paused) return () => inflight.current?.abort();
    const id = setInterval(load, intervalMs);
    return () => {
      clearInterval(id);
      inflight.current?.abort();
    };
  }, [load, paused, intervalMs]);

  return { data, error, loading, lastUpdated, refresh: load };
}
