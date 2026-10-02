import { useMemo, useState } from "react";
import { Activity, Ban, CheckCircle2, Gauge, Network } from "lucide-react";
import { useAnalytics } from "./hooks/useAnalytics.js";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import KpiCard from "./components/KpiCard.jsx";
import TrafficChart from "./components/TrafficChart.jsx";
import StatusDonut from "./components/StatusDonut.jsx";
import EndpointsPanel from "./components/EndpointsPanel.jsx";
import ClientsPanel from "./components/ClientsPanel.jsx";
import LogTable from "./components/LogTable.jsx";
import { ErrorBanner, Skeleton } from "./components/States.jsx";

export default function App() {
  const [windowSeconds, setWindowSeconds] = useState(60);
  const [paused, setPaused] = useState(false);

  const { data, error, loading, lastUpdated, refresh } = useAnalytics({ windowSeconds, paused });

  const spark = useMemo(
    () => (data?.timeseries ?? []).map((p) => ({ ...p, total: p.allowed + p.blocked })),
    [data]
  );

  const live = !error && !!data;

  return (
    <div className="app">
      <div className="bg-blobs" aria-hidden="true"><i /><i /><i /></div>
      <Sidebar system={data?.system} online={live} />

      <main className="main">
        <Header
          windowSeconds={windowSeconds}
          onWindow={setWindowSeconds}
          paused={paused}
          onTogglePause={() => setPaused((p) => !p)}
          onRefresh={refresh}
          live={live}
          lastUpdated={lastUpdated}
        />

        {data?.window_truncated && (
          <div className="note">
            Traffic is heavier than the dashboard reads per refresh, so stats cover the latest{" "}
            {Math.round(data.effective_window_seconds)}s instead of {data.window_seconds}s.
          </div>
        )}

        {error && <ErrorBanner message={error} onRetry={refresh} hasData={!!data} />}

        {loading && !data ? (
          <Skeleton />
        ) : data ? (
          <>
            <div className="kpi-grid">
              <KpiCard label="Requests / sec" tone="blue" icon={Activity} value={data.requests_per_second}
                       decimals={2} hint={`${data.total_requests.toLocaleString()} in last ${Math.round(data.effective_window_seconds)}s`}
                       series={spark} dataKey="total" />
              <KpiCard label="Allowed" tone="mint" icon={CheckCircle2} value={data.allowed_requests}
                       hint={`${(100 - data.block_rate_pct).toFixed(1)}% pass rate`}
                       series={spark} dataKey="allowed" />
              <KpiCard label="Rate limited" tone="coral" icon={Ban} value={data.blocked_requests}
                       hint={`${data.block_rate_pct.toFixed(2)}% block rate`}
                       series={spark} dataKey="blocked" />
              <KpiCard label="Active IPs" tone="lilac" icon={Network} value={data.active_ips}
                       hint="unique clients in window" />
              <KpiCard label="p95 latency" tone="amber" icon={Gauge} value={data.p95_latency_ms}
                       decimals={2} suffix=" ms" hint={`avg ${data.avg_latency_ms.toFixed(2)} ms`} />
            </div>

            <div className="grid-2">
              <TrafficChart series={data.timeseries} />
              <StatusDonut statuses={data.status_codes} blockRate={data.block_rate_pct} total={data.total_requests} />
            </div>

            <div className="grid-2 even">
              <EndpointsPanel endpoints={data.endpoints} />
              <ClientsPanel clients={data.top_abusive_clients} />
            </div>

            <LogTable rows={data.recent} />
          </>
        ) : null}

        <footer className="footer">
          Distributed API Rate Limiter · FastAPI + Redis + React
        </footer>
      </main>
    </div>
  );
}
