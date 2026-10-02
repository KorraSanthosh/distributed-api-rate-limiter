import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { useCountUp } from "../hooks/useCountUp.js";

export default function KpiCard({ label, value, decimals = 0, suffix = "", icon: Icon, tone, hint, series, dataKey }) {
  const animated = useCountUp(value);
  const display = animated.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const gradId = `spark-${tone}`;

  return (
    <div className={`kpi tone-${tone}`}>
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        <span className="kpi-icon"><Icon size={17} /></span>
      </div>
      <div className="kpi-value">
        {display}
        {suffix && <span className="kpi-suffix">{suffix}</span>}
      </div>
      <div className="kpi-hint">{hint}</div>
      {series && (
        <div className="kpi-spark">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--tone)" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="var(--tone)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey={dataKey} stroke="var(--tone)" strokeWidth={2}
                    fill={`url(#${gradId})`} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
