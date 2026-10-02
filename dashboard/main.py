import time
import pandas as pd
import plotly.express as px
import redis
import streamlit as st

from app.core.config import settings

# Page Configurations
st.set_page_config(
    page_title="Distributed Rate Limiter Analytics",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Soft pastel light theme (base theme colours live in .streamlit/config.toml)
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(135deg, #F3EFFF 0%, #E8F7F2 45%, #FFF1E6 100%); }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #E4E9FF 0%, #E3F6EF 100%); }
    [data-testid="stMetric"], div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.75); border-radius: 14px; padding: 15px;
        border: 1px solid #DAD7F5; box-shadow: 0 2px 8px rgba(124, 131, 253, 0.12);
    }
    div[data-testid="column"]:nth-of-type(1) [data-testid="stMetric"] { border-top: 4px solid #8FB8FF; }
    div[data-testid="column"]:nth-of-type(2) [data-testid="stMetric"] { border-top: 4px solid #7ED6B5; }
    div[data-testid="column"]:nth-of-type(3) [data-testid="stMetric"] { border-top: 4px solid #F5A3A3; }
    div[data-testid="column"]:nth-of-type(4) [data-testid="stMetric"] { border-top: 4px solid #C3A6F5; }
    div[data-testid="column"]:nth-of-type(5) [data-testid="stMetric"] { border-top: 4px solid #F7C98B; }
    h1, h2, h3 { color: #5B63C9 !important; }
    .stButton>button {
        background-color: #B9BEFF; color: #2F3358; font-weight: 600;
        border: none; border-radius: 10px;
    }
    .stButton>button:hover { background-color: #A3F0D2; color: #2F3358; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_redis_client() -> redis.Redis:
    """Creates a synchronous Redis client for Streamlit."""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        socket_timeout=2.0,
        decode_responses=True,  # Decode results to strings
    )


def initialize_session_state() -> None:
    """Initializes persistent structures across page refreshes."""
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "last_id" not in st.session_state:
        st.session_state.last_id = "0"
    if "is_paused" not in st.session_state:
        st.session_state.is_paused = False


def fetch_new_logs(r: redis.Redis) -> None:
    """Reads new stream entries from Redis and appends to local log memory."""
    if st.session_state.is_paused:
        return

    try:
        # Read from Redis Stream starting from last fetched message ID
        stream_data = r.xread({"api_traffic_stream": st.session_state.last_id}, count=500)
        if not stream_data:
            return

        new_entries = []
        last_processed_id = st.session_state.last_id

        # Parse stream format: [['stream_key', [('msg_id', {'field': 'val'})]]]
        for _, messages in stream_data:
            for msg_id, fields in messages:
                # Coerce fields back to correct types
                entry = {
                    "request_id": fields.get("request_id"),
                    "timestamp": float(fields.get("timestamp", 0)),
                    "client_ip": fields.get("client_ip"),
                    "method": fields.get("method"),
                    "endpoint": fields.get("endpoint"),
                    "status_code": int(fields.get("status_code", 0)),
                    "latency_ms": float(fields.get("latency_ms", 0.0)),
                    "allowed": fields.get("allowed") == "True",
                }
                new_entries.append(entry)
                last_processed_id = msg_id

        # Update logs list and clamp storage size to prevent memory leaks (keep last 5000 items)
        st.session_state.logs.extend(new_entries)
        if len(st.session_state.logs) > 5000:
            st.session_state.logs = st.session_state.logs[-5000:]

        st.session_state.last_id = last_processed_id

    except redis.RedisError as e:
        st.sidebar.error(f"Redis Connection Error: {e}")


def main() -> None:
    initialize_session_state()
    r = get_redis_client()

    # Sidebar Controls
    st.sidebar.title("🛡️ Limiter Console")
    st.sidebar.markdown("Distributed API Gateway Real-Time Traffic & Rate Limiting Monitor.")
    
    # Connection Health Metric
    try:
        redis_ok = r.ping()
        st.sidebar.success("Redis Status: CONNECTED" if redis_ok else "Redis Status: DISCONNECTED")
    except Exception:
        st.sidebar.error("Redis Status: UNREACHABLE")

    # Refresh toggle
    st.sidebar.subheader("Dashboard Controls")
    pause_label = "▶️ Resume Stream" if st.session_state.is_paused else "⏸️ Pause Stream"
    if st.sidebar.button(pause_label):
        st.session_state.is_paused = not st.session_state.is_paused
        st.rerun()

    if st.sidebar.button("🧹 Clear Metric Logs"):
        st.session_state.logs = []
        st.session_state.last_id = "0"
        st.rerun()

    # Fetch new stream inputs
    fetch_new_logs(r)

    # Convert local memory to DataFrame for analytics calculations
    logs = st.session_state.logs

    # Title Banner
    st.title("📊 Real-Time API Traffic Analyzer")

    if not logs:
        st.info("No incoming traffic logs detected in Redis Stream yet. Fire up the Traffic Simulator!")
        time.sleep(1.0)
        st.rerun()
        return

    df = pd.DataFrame(logs)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

    # 1. Key Metrics Calculations
    now = time.time()
    one_min_ago = now - 60.0
    
    # Slice last 60 seconds
    df_1m = df[df["timestamp"] >= one_min_ago]
    
    total_req_1m = len(df_1m)
    allowed_req_1m = len(df_1m[df_1m["allowed"] == True])
    blocked_req_1m = len(df_1m[df_1m["allowed"] == False])

    avg_req_sec = total_req_1m / 60.0 if total_req_1m > 0 else 0.0
    blocked_req_sec = blocked_req_1m / 60.0 if blocked_req_1m > 0 else 0.0
    allowed_req_sec = allowed_req_1m / 60.0 if allowed_req_1m > 0 else 0.0

    active_ips = df_1m["client_ip"].nunique()
    
    avg_latency = df["latency_ms"].mean()
    p95_latency = df["latency_ms"].quantile(0.95)

    # 2. Render Metric KPI Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(label="RPS (Last 60s)", value=f"{avg_req_sec:.2f}/s")
    with col2:
        st.metric(label="Allowed RPS", value=f"{allowed_req_sec:.2f}/s")
    with col3:
        st.metric(label="Blocked RPS", value=f"{blocked_req_sec:.2f}/s", delta=f"{blocked_req_1m} blocks", delta_color="inverse")
    with col4:
        st.metric(label="Active IPs (Last 60s)", value=str(active_ips))
    with col5:
        st.metric(label="p95 Latency", value=f"{p95_latency:.1f} ms")

    # Spacer
    st.write("")

    # 3. Live Charts Row
    chart_col1, chart_col2 = st.columns([2, 1])

    with chart_col1:
        st.subheader("Traffic History (Allowed vs Blocked)")
        # Group traffic into 2-second windows for smooth plotting
        df_time = df.copy()
        df_time["time_bucket"] = df_time["datetime"].dt.round("2s")
        df_chart = (
            df_time.groupby(["time_bucket", "allowed"])
            .size()
            .reset_index(name="requests")
        )
        # Human readable labels
        df_chart["status"] = df_chart["allowed"].map({True: "Allowed", False: "Rate Limited"})

        fig_traffic = px.line(
            df_chart,
            x="time_bucket",
            y="requests",
            color="status",
            color_discrete_map={"Allowed": "#5CC8A1", "Rate Limited": "#F28B93"},
            template="plotly_white",
        )
        fig_traffic.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Time",
            yaxis_title="Request Volume",
            legend_title="Traffic Status",
        )
        st.plotly_chart(fig_traffic, use_container_width=True)

    with chart_col2:
        st.subheader("HTTP Status Code Split")
        df_status = df["status_code"].value_counts().reset_index()
        df_status.columns = ["status_code", "count"]
        df_status["status_code"] = df_status["status_code"].astype(str)

        fig_pie = px.pie(
            df_status,
            values="count",
            names="status_code",
            color="status_code",
            color_discrete_map={"200": "#7ED6B5", "429": "#F5A3A3"},
            hole=0.4,
            template="plotly_white",
        )
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend_title="HTTP Status",
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # 4. Tables and Breakdowns Row
    st.write("")
    table_col1, table_col2 = st.columns(2)

    with table_col1:
        st.subheader("🚨 Top 10 Abusive Client IPs (Rate Limited)")
        blocked_df = df[df["allowed"] == False]
        if not blocked_df.empty:
            abusive_ips = (
                blocked_df["client_ip"]
                .value_counts()
                .reset_index()
            )
            abusive_ips.columns = ["Client IP", "Blocked Requests Count"]
            st.dataframe(abusive_ips.head(10), use_container_width=True, hide_index=True)
        else:
            st.success("No clients have triggered rate limits yet!")

    with table_col2:
        st.subheader("🗺️ Endpoint Traffic Split")
        endpoint_traffic = df["endpoint"].value_counts().reset_index()
        endpoint_traffic.columns = ["API Endpoint", "Request Count"]
        
        # Calculate percentage share
        total_reqs = endpoint_traffic["Request Count"].sum()
        endpoint_traffic["Traffic Share (%)"] = (
            (endpoint_traffic["Request Count"] / total_reqs) * 100
        ).round(2)
        
        st.dataframe(endpoint_traffic, use_container_width=True, hide_index=True)

    # 5. Raw Logger View
    st.write("")
    st.subheader("📄 Live Request Event Stream Logs")
    st.dataframe(
        df[["datetime", "client_ip", "method", "endpoint", "status_code", "latency_ms", "allowed"]]
        .sort_values(by="datetime", ascending=False)
        .head(25),
        use_container_width=True,
        hide_index=True,
    )

    # Trigger Auto refresh loop in 1s if stream is playing
    if not st.session_state.is_paused:
        time.sleep(1.0)
        st.rerun()


if __name__ == "__main__":
    main()
