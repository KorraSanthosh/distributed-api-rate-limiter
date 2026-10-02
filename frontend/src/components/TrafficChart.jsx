import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtClock } from "../util.js";

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const allowed = payload.find((p) => p.dataKey === "allowed")?.value ?? 0;
  const blocked = payload.find((p) => p.dataKey === "blocked")?.value ?? 0;
  return (
    <div className="tooltip">
      <div className="tooltip-time">{fmtClock(label)}</div>
      <div className="tooltip-row"><i className="swatch mint" />Allowed <b>{allowed}</b></div>
      <div className="tooltip-row"><i className="swatch coral" />Rate limited <b>{blocked}</b></div>
    </div>
  );
}

export default function TrafficChart({ series, bucketSeconds = 2 }) {
  return (
    <section className="panel" id="traffic">
      <div className="panel-head">
        <div>
          <h2>Traffic history</h2>
          <p className="muted">Requests per {bucketSeconds}s · last 2 minutes</p>
        </div>
        <div className="legend">
          <span><i className="swatch mint" />Allowed</span>
          <span><i className="swatch coral" />Rate limited</span>
        </div>
      </div>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <defs>
              <linearGradient id="gAllowed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5fd6b0" stopOpacity={0.55} />
                <stop offset="100%" stopColor="#5fd6b0" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gBlocked" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f58b9a" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#f58b9a" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e6e3f7" strokeDasharray="3 6" vertical={false} />
            <XAxis dataKey="timestamp" tickFormatter={fmtClock} tickLine={false} axisLine={false}
                   tick={{ fill: "#8a8fb0", fontSize: 11 }} minTickGap={48} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8a8fb0", fontSize: 11 }} allowDecimals={false} />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#b9bdf5", strokeWidth: 1 }} />
            <Area type="monotone" dataKey="allowed" stroke="#3fc29a" strokeWidth={2.4}
                  fill="url(#gAllowed)" isAnimationActive={false} />
            <Area type="monotone" dataKey="blocked" stroke="#ee6f84" strokeWidth={2.4}
                  fill="url(#gBlocked)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
