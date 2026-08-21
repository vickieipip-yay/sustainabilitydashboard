"""
Club Sustainability Intelligence — prototype dashboard.

Demonstrates how three siloed data sources (Procurement, Membership
Analytics, Sustainability) can be joined into one operational,
decision-focused view for a single F&B outlet at a private members' club.

Run with:  streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import data_gen
import joins
import metrics
import targets

st.set_page_config(page_title="Club Sustainability Intelligence", layout="wide", initial_sidebar_state="expanded")


@st.cache_data
def load_data():
    return data_gen.generate_all()


@st.cache_data
def build_joined(_data):
    full = joins.full_join(_data["pos_transactions"], _data["recipe_master"], _data["member_profile"], _data["outlet_id"])
    waste_outlet = joins.waste_for_outlet(_data["waste_log"], _data["outlet_id"])
    utility_outlet = joins.utility_for_outlet(_data["utility_log"], _data["outlet_id"])
    return full, waste_outlet, utility_outlet


data = load_data()
full_joined, waste_outlet, utility_outlet = build_joined(data)
outlet_name = data["outlet_name"]
switch_day = data["switch_day"]
start_date = data["start_date"]
n_days = data["n_days"]

# --- Persistent banner ------------------------------------------------------
st.markdown(
    """
    <div style="background-color:#7a1f1f;color:white;padding:10px 16px;border-radius:6px;
    font-weight:600;text-align:center;margin-bottom:12px;">SYNTHETIC DATA — FOR DEMO ONLY</div>
    """,
    unsafe_allow_html=True,
)
st.title("🏇 Club Sustainability Intelligence")
st.caption(
    f"Unified operational view — outlet: **{outlet_name}** — {n_days}-day window "
    f"(modeled loosely on Hong Kong Jockey Club)"
)

# --- Sidebar: targets + global filters --------------------------------------
with st.sidebar:
    st.header("Targets (illustrative, adjustable)")
    st.caption("All targets are synthetic demo thresholds, not real club targets.")
    with st.expander("Waste & carbon targets", expanded=False):
        waste_target_per_cover = st.number_input("Food waste target (kg/cover)", 0.01, 1.0, targets.TARGET_WASTE_PER_COVER_KG, 0.005)
        co2e_breakfast = st.number_input("Carbon target — breakfast (kg CO2e/cover)", 0.1, 5.0, targets.TARGET_CO2E_PER_COVER_BY_PERIOD["breakfast"], 0.1)
        co2e_lunch = st.number_input("Carbon target — lunch (kg CO2e/cover)", 0.1, 10.0, targets.TARGET_CO2E_PER_COVER_BY_PERIOD["lunch"], 0.1)
        co2e_dinner = st.number_input("Carbon target — dinner (kg CO2e/cover)", 0.1, 12.0, targets.TARGET_CO2E_PER_COVER_BY_PERIOD["dinner"], 0.1)
        carbon_target_by_period = {"breakfast": co2e_breakfast, "lunch": co2e_lunch, "dinner": co2e_dinner}
    with st.expander("Utility target engine (read-only, set at data generation)", expanded=False):
        st.caption(
            f"Fixed load: {targets.FIXED_ELECTRICITY_KWH:.0f} kWh + {targets.ELECTRICITY_PER_COVER_KWH:.1f} kWh/cover "
            f"(x{targets.SUMMER_MULT:.2f} in Jun-Aug, x{targets.WEEKEND_MULT:.2f} Fri/Sat, "
            f"+{targets.TEMP_ELEC_COEF_PER_COVER:.2f} kWh/cover per °C above {targets.TEMP_BASELINE_C:.0f}°C).\n\n"
            f"Water: {targets.FIXED_WATER_LITRES:.0f}L + {targets.WATER_PER_COVER_LITRES:.0f}L/cover, same seasonal logic."
        )

    st.markdown("---")
    st.header("Global filters")
    min_date, max_date = full_joined["date"].min(), full_joined["date"].max()
    date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if len(date_range) != 2:
        date_range = (min_date, max_date)
    service_periods = st.multiselect("Service period", data_gen.SERVICE_PERIODS, default=data_gen.SERVICE_PERIODS)
    membership_types = st.multiselect("Membership type", data_gen.MEMBERSHIP_TYPES, default=data_gen.MEMBERSHIP_TYPES)
    genders = st.multiselect("Gender", data_gen.GENDERS, default=data_gen.GENDERS)
    age_groups = st.multiselect("Age group", data_gen.AGE_GROUPS, default=data_gen.AGE_GROUPS)
    frequency = st.selectbox("Diner frequency", ["All", "Frequent (>8 visits/mo)", "Occasional (<=8 visits/mo)"])

    st.markdown("---")
    st.markdown("**Tables loaded:**")
    for name in ["purchase_orders", "pos_transactions", "recipe_master", "waste_log", "utility_log", "member_profile"]:
        st.write(f"- `{name}`: {len(data[name]):,} rows")

filtered_full = joins.apply_global_filters(
    full_joined, date_range=date_range, service_periods=service_periods,
    membership_types=membership_types, genders=genders, age_groups=age_groups, frequency=frequency,
)
filtered_waste = joins.apply_date_filter(waste_outlet, date_range)
filtered_utility = joins.apply_date_filter(utility_outlet, date_range)

tab1, tab2, tab3, tab4 = st.tabs(
    ["📉 Operational Intensity", "🥩 Carbon-Costed Menu", "🧑‍🤝‍🧑 Member Adoption Signal", "🎯 Targets & Progress"]
)

# ============================================================ TAB 1 =======
with tab1:
    st.subheader("Operational Intensity")
    st.caption("Where waste, energy, and water stand vs. target for a selected week. Join keys: week_start, outlet_id, cover count.")

    weeks_available = sorted(filtered_full["week_start"].dropna().unique(), reverse=True)
    selected_week = st.selectbox("Select week", weeks_available, index=0 if weeks_available else None, key="tab1_week_select")

    if selected_week:
        k = metrics.weekly_kpis(filtered_waste, filtered_utility, filtered_full, selected_week, waste_target_per_cover)

        c1, c2 = st.columns(2)
        c1.metric("Total food waste", f"{k['total_waste_kg']:.1f} kg", f"{k['waste_variance_pct']:+.1f}% vs target")
        c2.metric("Food waste value", f"HK${k['total_waste_hkd']:,.0f}")

        def target_bar(label, actual, target, unit):
            over = actual > target
            fig = px.bar(
                x=["Actual", "Target"], y=[actual, target],
                title=f"{label} — {unit}", labels={"x": "", "y": unit},
            )
            fig.update_traces(marker_color=["#c0392b" if over else "#27ae60", "#9aa0a6"])
            return fig

        b1, b2, b3 = st.columns(3)
        with b1:
            st.plotly_chart(target_bar("Food waste", k["total_waste_kg"], k["waste_target_kg"], "kg"), use_container_width=True)
        with b2:
            st.plotly_chart(target_bar("Electricity", k["total_elec"], k["elec_target"], "kWh"), use_container_width=True)
        with b3:
            st.plotly_chart(target_bar("Water", k["total_water"], k["water_target"], "litres"), use_container_width=True)

# ============================================================ TAB 2 =======
with tab2:
    st.subheader("Carbon-Costed Menu")
    st.caption(
        "Frequently-ordered dishes with the highest and lowest carbon emissions, ordered by how often they're "
        "ordered. Join keys: dish_id → sku → emission_factor, covers_sold as the order-frequency ranking."
    )

    dish_table, frequently_ordered, threshold_covers = metrics.dish_carbon_table(filtered_full, filtered_waste, top_pct=0.30)
    high_carbon, low_carbon = metrics.carbon_frequency_split(frequently_ordered)
    display_cols = ["dish_name", "covers_sold", "co2e_per_cover", "total_co2e_kg"]
    fmt = {"co2e_per_cover": "{:.2f}", "total_co2e_kg": "{:.1f}"}

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Highest carbon — frequently ordered, most-ordered first**")
        st.dataframe(high_carbon[display_cols].style.format(fmt), use_container_width=True)
    with col2:
        st.markdown("**Lowest carbon — frequently ordered, most-ordered first**")
        st.dataframe(low_carbon[display_cols].style.format(fmt), use_container_width=True)

# ============================================================ TAB 3 =======
with tab3:
    st.subheader("Member Adoption Signal")
    st.caption("Only full and racing members are analyzed here; guests are excluded. Join keys: member_id → gender/age_group/membership_type, dish_id → lower_impact_flag.")

    st.markdown("#### Members who have chosen a lower-impact dish")
    dim = st.selectbox("Segment by", ["gender", "age_group", "membership_type"], format_func=lambda s: s.replace("_", " ").title())
    members = metrics.members_who_chose_lower_impact(filtered_full, dim)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Members who ordered a lower-impact dish", f"{members['adopters']:,} of {members['total_members']:,}", f"{members['pct']:.1f}%")
    with c2:
        fig = px.bar(members["by_dim"], x=dim, y="pct_members_adopted", title=f"% of members who ordered a lower-impact dish, by {dim}")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Frequent vs. occasional diners, before/after the switch")
    dish_waste_lookup = metrics.dish_waste_per_cover_lookup(filtered_waste, filtered_full)
    seg = metrics.frequency_segment_comparison(filtered_full, switch_day, start_date, dish_waste_lookup)
    st.dataframe(seg.style.format({
        "avg_spend": "HK${:,.0f}", "turkey_adoption_pct": "{:.1f}%", "avg_co2e_per_cover": "{:.2f}",
        "avg_waste_per_cover": "{:.3f}", "revenue": "HK${:,.0f}",
    }), use_container_width=True)
    fig = px.bar(seg, x="segment", y="turkey_adoption_pct", color="period", barmode="group", title="Turkey adoption: frequent vs. occasional, pre/post switch")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================ TAB 4 =======
with tab4:
    st.subheader("Targets & Progress")
    st.caption("Join key used: week_start / month (derived from date on all outlet-scoped inputs). Targets are adjustable in the sidebar.")

    period_choice = st.radio("Period", ["Week", "Month"], horizontal=True, key="tab4_period_radio")
    col_name = "week_start" if period_choice == "Week" else "month"
    period_values = sorted(filtered_full[col_name].dropna().unique(), reverse=True)
    sel_period_value = st.selectbox(f"Select {period_choice.lower()}", period_values, key="tab4_period_value_select")

    scorecard = metrics.target_scorecard(
        filtered_waste, filtered_utility, filtered_full, period=period_choice.lower(), period_value=sel_period_value,
        waste_target_per_cover=waste_target_per_cover, carbon_target_by_period=carbon_target_by_period,
    )

    def status_icon(status):
        return {"On target": "🟢", "Slightly above target": "🟡", "Materially above target": "🔴", "Below target": "🟢"}.get(status, "")

    scorecard_display = scorecard.copy()
    scorecard_display["status"] = scorecard_display["status"].apply(lambda s: f"{status_icon(s)} {s}")
    st.dataframe(scorecard_display.style.format({"actual": "{:,.2f}", "target": "{:,.2f}", "variance": "{:+,.2f}", "variance_pct": "{:+.1f}%"}), use_container_width=True)

    st.markdown("#### Weekly variance heatmap")
    weekly_var = metrics.weekly_variance_summary(filtered_waste, filtered_utility, filtered_full, waste_target_per_cover)
    heat_cols = ["Food waste kg", "Water litres", "Electricity kWh", "Carbon emissions"]
    heat_df = weekly_var.set_index("week_start")[heat_cols].T
    fig = px.imshow(heat_df, aspect="auto", color_continuous_scale="RdYlGn_r", labels=dict(color="% variance"), title="Weekly % variance vs. target")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Monthly variance summary")
    monthly_var = metrics.monthly_variance_summary(filtered_waste, filtered_utility, filtered_full, waste_target_per_cover)
    if not monthly_var.empty:
        pivot = monthly_var.pivot(index="month", columns="metric", values="variance_pct")
        st.dataframe(pivot.style.format("{:+.1f}%"), use_container_width=True)

    worst, best = metrics.worst_best_weeks(weekly_var, n=5)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Top 5 worst weeks (target deviation)**")
        st.dataframe(worst[["week_start", "avg_variance_pct"] + heat_cols].style.format("{:+.1f}", subset=["avg_variance_pct"] + heat_cols), use_container_width=True)
    with col2:
        st.markdown("**Top 5 best weeks (target performance)**")
        st.dataframe(best[["week_start", "avg_variance_pct"] + heat_cols].style.format("{:+.1f}", subset=["avg_variance_pct"] + heat_cols), use_container_width=True)
