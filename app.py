"""
app.py
------
My Shop POS — Remote Monitoring Dashboard

Reads read-only summary data from Supabase (sales totals, inventory,
bank balances, profit & loss, advance bookings) and shows it in a
simple, password protected web page you can open from any phone or
computer browser.

No customer names/numbers or bank account details are ever shown here,
because they're never sent to the cloud in the first place.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="My Shop POS - Remote Dashboard", page_icon="🏪", layout="wide")

# ---------------------------------------------------------------------------
# Attractive theme (custom CSS on top of Streamlit's dark theme in
# .streamlit/config.toml)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #0f2027 0%, #203a43 50%, #2c5364 100%); }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 14px 18px;
    }
    div[data-testid="stMetricValue"] { color: #4dd0e1; }
    h1, h2, h3 { color: #f0f4f8; }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
    div[data-testid="stExpander"] {
        background: rgba(255,255,255,0.05);
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.1);
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Password gate
# ---------------------------------------------------------------------------
def check_password():
    def password_entered():
        if st.session_state.get("password_input") == st.secrets.get("DASHBOARD_PASSWORD", ""):
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct"):
        return True

    st.title("🏪 My Shop POS - Remote Dashboard")
    st.text_input("Enter password", type="password", key="password_input", on_change=password_entered)
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ---------------------------------------------------------------------------
# Supabase read-only fetch (uses the public/publishable key — safe, RLS blocks writes)
# ---------------------------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]


@st.cache_data(ttl=60)
def fetch(table, order=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*"
    if order:
        url += f"&order={order}"
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


st.title("🏪 My Shop POS — Remote Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %I:%M:%S %p')}  "
           "(data updates whenever you click 'Sync Now' on the shop computer)")

if st.button("🔄 Refresh Now"):
    st.cache_data.clear()

# ---------------------------------------------------------------------------
# Profit & Loss — hidden by default, click to expand
# ---------------------------------------------------------------------------
with st.expander("📈 Profit & Loss — click to view", expanded=False):
    pl_df = fetch("profit_loss_summary")
    if not pl_df.empty:
        cols = st.columns(len(pl_df))
        for col, (_, row) in zip(cols, pl_df.iterrows()):
            with col:
                st.metric(row["period_label"],
                          f"PKR {row['net_profit']:,.0f}",
                          f"Sales profit PKR {row['sales_profit']:,.0f} / Expenses PKR {row['expenses']:,.0f}")
    else:
        st.info("No profit & loss data yet — sync from the shop computer first.")

st.divider()

# ---------------------------------------------------------------------------
# Sales trend
# ---------------------------------------------------------------------------
st.subheader("💰 Sales Trend")
daily_df = fetch("daily_sales", order="sale_date.asc")
if not daily_df.empty:
    daily_df["sale_date"] = pd.to_datetime(daily_df["sale_date"])
    st.line_chart(daily_df.set_index("sale_date")[["total_sales", "total_profit"]])
else:
    st.info("No sales data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Recent Sales — full summary, full width
# ---------------------------------------------------------------------------
st.subheader("🧾 Recent Sales — Full Summary")
recent_df = fetch("recent_sales", order="sale_date.desc")
if not recent_df.empty:
    recent_df["sale_date"] = pd.to_datetime(recent_df["sale_date"]).dt.strftime("%d %b %Y, %I:%M %p")
    display_df = recent_df.rename(columns={
        "id": "Sale #", "sale_date": "Date & Time", "item_count": "Items",
        "discount": "Discount (PKR)", "total": "Total (PKR)", "profit": "Profit (PKR)",
    })[["Sale #", "Date & Time", "Items", "Discount (PKR)", "Total (PKR)", "Profit (PKR)"]]
    st.dataframe(display_df, hide_index=True, use_container_width=True)
else:
    st.info("No sales yet.")

st.divider()

# ---------------------------------------------------------------------------
# Inventory + Banking
# ---------------------------------------------------------------------------
left2, right2 = st.columns(2)

with left2:
    st.subheader("📦 Inventory")
    inv_df = fetch("inventory_snapshot", order="name.asc")
    if not inv_df.empty:
        total_value = inv_df["value"].sum()
        st.metric("Total Inventory Value", f"PKR {total_value:,.0f}")
        low_stock = inv_df[inv_df["quantity"] <= inv_df["low_stock_threshold"]]
        if not low_stock.empty:
            st.warning(f"⚠ {len(low_stock)} product(s) low or out of stock")
        st.dataframe(inv_df[["name", "category", "quantity", "cost_price", "selling_price", "value"]],
                     hide_index=True, use_container_width=True)
    else:
        st.info("No inventory data yet.")

with right2:
    st.subheader("🏦 Banking")
    bank_df = fetch("bank_balances", order="bank_name.asc")
    if not bank_df.empty:
        total_balance = bank_df["current_balance"].sum()
        st.metric("Total Balance (All Banks)", f"PKR {total_balance:,.0f}")
        st.dataframe(bank_df[["bank_name", "current_balance"]],
                     hide_index=True, use_container_width=True)
    else:
        st.info("No bank data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Advance Bookings
# ---------------------------------------------------------------------------
st.subheader("📑 Advance Bookings")
bookings_df = fetch("advance_bookings", order="booking_date.desc")
if not bookings_df.empty:
    total_bookings_value = bookings_df["total_amount"].sum()
    st.metric("Total Bookings Value", f"PKR {total_bookings_value:,.0f}")
    bookings_df["booking_date"] = pd.to_datetime(bookings_df["booking_date"]).dt.strftime("%d %b %Y, %I:%M %p")
    display_bookings = bookings_df.rename(columns={
        "booking_date": "Date", "product_name": "Product", "company_name": "Company",
        "price": "Price (PKR)", "quantity": "Qty", "total_amount": "Total (PKR)",
    })[["Date", "Product", "Company", "Price (PKR)", "Qty", "Total (PKR)"]]
    st.dataframe(display_bookings, hide_index=True, use_container_width=True)
else:
    st.info("No advance bookings yet.")
