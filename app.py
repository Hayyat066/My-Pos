"""
app.py
------
My Shop POS — Remote Monitoring Dashboard

Reads read-only summary data from Supabase (sales totals, inventory,
bank balances, profit & loss, advance bookings, expenses) and shows it
in a simple, password protected web page you can open from any phone
or computer browser. Customer names/numbers are never shown here.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="My Shop POS - Remote Dashboard", page_icon="🏪", layout="wide")

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
# Sales trend (line chart)
# ---------------------------------------------------------------------------
st.subheader("💰 Sales Trend")
daily_df = fetch("daily_sales", order="sale_date.asc")
if not daily_df.empty:
    daily_df["sale_date"] = pd.to_datetime(daily_df["sale_date"])
    chart_df = daily_df.set_index("sale_date")[["total_sales", "total_profit"]]
    chart_df.columns = ["Total Sales (PKR)", "Total Profit (PKR)"]
    st.line_chart(chart_df)
else:
    st.info("No sales data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Recent Sales — click a row to see the full receipt
# ---------------------------------------------------------------------------
st.subheader("🧾 Recent Sales — click a row to view the full receipt")
recent_df = fetch("recent_sales", order="sale_date.desc")
sale_items_df = fetch("recent_sale_items")

if not recent_df.empty:
    display_df = recent_df.copy()
    display_df["sale_date_fmt"] = pd.to_datetime(display_df["sale_date"]).dt.strftime("%d %b %Y, %I:%M %p")
    table_view = display_df.rename(columns={
        "id": "Sale #", "sale_date_fmt": "Date & Time", "item_count": "Items",
        "discount": "Discount (PKR)", "total": "Total (PKR)", "profit": "Profit (PKR)",
    })[["Sale #", "Date & Time", "Items", "Discount (PKR)", "Total (PKR)", "Profit (PKR)"]]

    event = st.dataframe(table_view, hide_index=True, use_container_width=True,
                          on_select="rerun", selection_mode="single-row", key="sales_table")

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_sale = display_df.iloc[selected_rows[0]]
        sale_id = selected_sale["id"]

        with st.container(border=True):
            st.markdown(f"### 🧾 Receipt — Sale #{sale_id}")
            st.write(f"**Date:** {selected_sale['sale_date_fmt']}")

            items_for_sale = sale_items_df[sale_items_df["sale_id"] == sale_id] if not sale_items_df.empty else pd.DataFrame()
            if not items_for_sale.empty:
                items_view = items_for_sale.copy()
                items_view["Amount (PKR)"] = items_view["quantity"] * items_view["price"]
                items_view = items_view.rename(columns={
                    "product_name": "Product", "quantity": "Qty", "price": "Price (PKR)",
                })[["Product", "Qty", "Price (PKR)", "Amount (PKR)"]]
                st.dataframe(items_view, hide_index=True, use_container_width=True)
            else:
                st.info("Item details for this sale weren't included in the last sync.")

            st.write(f"**Discount:** PKR {selected_sale['discount']:,.2f}")
            st.write(f"**Total:** PKR {selected_sale['total']:,.2f}")
            st.write(f"**Profit:** PKR {selected_sale['profit']:,.2f}")
else:
    st.info("No sales yet.")

st.divider()

# ---------------------------------------------------------------------------
# Banking — full detail + total at top
# ---------------------------------------------------------------------------
st.subheader("🏦 Banking")
bank_df = fetch("bank_balances", order="bank_name.asc")
bank_txn_df = fetch("bank_transactions_recent", order="transaction_date.desc")

if not bank_df.empty:
    total_balance = bank_df["current_balance"].sum()
    st.metric("💵 Total Money (All Accounts)", f"PKR {total_balance:,.0f}")

    for _, bank in bank_df.iterrows():
        with st.expander(f"🏦 {bank['bank_name']} — PKR {bank['current_balance']:,.0f}"):
            st.write(f"**Current Balance:** PKR {bank['current_balance']:,.2f}")

            if not bank_txn_df.empty:
                bank_specific = bank_txn_df[bank_txn_df["bank_id"] == bank["bank_id"]]
                if not bank_specific.empty:
                    txn_view = bank_specific.copy()
                    txn_view["transaction_date"] = pd.to_datetime(txn_view["transaction_date"]).dt.strftime("%d %b, %I:%M %p")
                    txn_view = txn_view.rename(columns={
                        "transaction_date": "Date", "type": "Type", "amount": "Amount (PKR)",
                        "note": "Note", "balance_after": "Balance After (PKR)",
                    })[["Date", "Type", "Amount (PKR)", "Note", "Balance After (PKR)"]]
                    st.dataframe(txn_view, hide_index=True, use_container_width=True)
                else:
                    st.caption("No recent deposits/withdrawals for this account.")
else:
    st.info("No bank data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Expenses (left) + Product Stock list (bottom-right)
# ---------------------------------------------------------------------------
left3, right3 = st.columns(2)

with left3:
    st.subheader("💸 Expenses")
    expenses_df = fetch("expenses_confirmed", order="expense_date.desc")
    if not expenses_df.empty:
        total_expenses = expenses_df["amount"].sum()
        st.metric("Total Confirmed Expenses", f"PKR {total_expenses:,.0f}")
        expenses_view = expenses_df.rename(columns={
            "expense_date": "Date", "note": "Note", "amount": "Amount (PKR)",
        })[["Date", "Note", "Amount (PKR)"]]
        st.dataframe(expenses_view, hide_index=True, use_container_width=True)
    else:
        st.info("No confirmed expenses yet.")

with right3:
    st.subheader("📦 Product Stock")
    inv_df = fetch("inventory_snapshot", order="name.asc")
    if not inv_df.empty:
        total_value = inv_df["value"].sum()
        st.metric("Total Inventory Value", f"PKR {total_value:,.0f}")
        low_stock = inv_df[inv_df["quantity"] <= inv_df["low_stock_threshold"]]
        if not low_stock.empty:
            st.warning(f"⚠ {len(low_stock)} product(s) low or out of stock")
        stock_view = inv_df.rename(columns={"name": "Product", "quantity": "Quantity"})[["Product", "Quantity"]]
        st.dataframe(stock_view, hide_index=True, use_container_width=True)
    else:
        st.info("No inventory data yet.")

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
    st.info("No advance bookings yet. If you've already added some in the app, make sure "
            "you've run supabase_add_v2.sql in Supabase, then click 'Sync Now' again.")
