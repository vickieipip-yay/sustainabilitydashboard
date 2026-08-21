"""
Club Sustainability Intelligence — prototype dashboard.

Demonstrates how three siloed data sources (Procurement, Membership
Analytics, Sustainability) can be joined into one operational,
decision-focused view for a single F&B outlet at a private members' club,
including a fully traceable case study on the beef -> turkey burger menu
substitution.

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
    waste_with_recipe = joins.waste_with_recipe(waste_outlet, _data["recipe_master"])
    utility_outlet = joins.utility_for_outlet(_data["utility_log"], _data["outlet_id"])
    return full, waste_outlet, waste_with_recipe, utility_outlet


data = load_data()
full_joined, waste_outlet, waste_with_recipe, utility_outlet = build_joined(data)
outlet_name = data["outlet_name"]
switch_day = data["switch_day"]
start_date = data["start_date"]
n_days = data["n_days"]
burger_dish_ids = data["burger_dish_ids"]
recipe_master = data["recipe_master"]

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
filtered_waste_recipe = joins.apply_date_filter(waste_with_recipe, date_range)
filtered_utility = joins.apply_date_filter(utility_outlet, date_range)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📉 Operational Intensity", "🥩 Carbon-Costed Menu", "🧑‍🤝‍🧑 Member Adoption Signal",
     "🎯 Targets & Progress", "🔗 Data Join Health", "🍔 Case Study: Burger Switch"]
)

# ============================================================ TAB 1 =======
with tab1:
    st.subheader("Operational Intensity")
    st.caption("Where waste occurs, when targets are missed, and which items drive it. Join keys: week_start, dish_id → sku, outlet_id, cover count.")

    trend = metrics.weekly_operational_trend(filtered_waste, filtered_utility, filtered_full)
    view_mode = st.radio("View", ["Absolute", "Per cover"], horizontal=True)

    if view_mode == "Absolute":
        cols = ["food_waste_kg", "food_waste_hkd", "water_litres", "electricity_kwh"]
    else:
        cols = ["food_waste_per_cover", "water_per_cover", "electricity_per_cover"]
    fig = px.line(trend, x="week_start", y=cols, title=f"Weekly operational intensity ({view_mode.lower()})", labels={"week_start": "Week", "value": "Value"})
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Week-over-week % change (most recent week)")
    if len(trend) >= 1:
        last = trend.iloc[-1]
        wow_cols = st.columns(4)
        for i, (label, col) in enumerate([
            ("Food waste kg", "food_waste_kg_wow_pct"), ("Food waste HK$", "food_waste_hkd_wow_pct"),
            ("Water litres", "water_litres_wow_pct"), ("Electricity kWh", "electricity_kwh_wow_pct"),
        ]):
            val = last.get(col)
            wow_cols[i].metric(label, f"{val:+.1f}%" if pd.notna(val) else "n/a")
        wow_cols2 = st.columns(3)
        for i, (label, col) in enumerate([
            ("Waste/cover", "food_waste_per_cover_wow_pct"), ("Water/cover", "water_per_cover_wow_pct"), ("Electricity/cover", "electricity_per_cover_wow_pct"),
        ]):
            val = last.get(col)
            wow_cols2[i].metric(label, f"{val:+.1f}%" if pd.notna(val) else "n/a")

    st.markdown("#### Weekly waste summary")
    weeks_available = sorted(filtered_full["week_start"].dropna().unique(), reverse=True)
    selected_week = st.selectbox("Select week", weeks_available, index=0 if weeks_available else None, key="tab1_week_select")

    if selected_week:
        k = metrics.weekly_kpis(filtered_waste, filtered_utility, filtered_full, selected_week, waste_target_per_cover)

        def rag(pct):
            return "🟢" if abs(pct) <= 5 else ("🟡" if pct <= 15 else "🔴")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total food waste", f"{k['total_waste_kg']:.1f} kg", f"{k['waste_variance_pct']:+.1f}% vs target")
        c2.metric("Food waste value", f"HK${k['total_waste_hkd']:,.0f}")
        c3.metric("Total water", f"{k['total_water']:,.0f} L", f"{rag(k['water_variance_pct'])} {k['water_variance_pct']:+.1f}%")
        c4.metric("Total electricity", f"{k['total_elec']:,.0f} kWh", f"{rag(k['elec_variance_pct'])} {k['elec_variance_pct']:+.1f}%")
        c5, c6 = st.columns(2)
        c5.metric("Total covers", f"{k['covers']:,.0f}")
        c6.metric("Food waste per cover", f"{k['waste_per_cover']:.3f} kg", f"{rag(k['waste_variance_pct'])} {k['waste_variance_pct']:+.1f}%")

        st.markdown("#### Food waste breakdown, selected week")
        breakdown = metrics.food_waste_breakdown(filtered_waste, filtered_full, selected_week, n=15)
        fmt = {"waste_kg": "{:.1f}", "value_hkd": "HK${:,.0f}", "share_pct": "{:.1f}%", "pct_of_production_wasted": "{:.1f}%"}
        st.dataframe(breakdown.style.format(fmt), use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(breakdown.sort_values("waste_kg", ascending=False).head(10), x="dish_name", y="waste_kg", title="Top wasted items by weight")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.bar(breakdown.sort_values("value_hkd", ascending=False).head(10), x="dish_name", y="value_hkd", title="Top wasted items by monetary value")
            st.plotly_chart(fig, use_container_width=True)

        stage_cols = [c for c in ["prep", "service", "plate-return"] if c in breakdown.columns]
        if stage_cols:
            stage_long = breakdown.melt(id_vars="dish_name", value_vars=stage_cols, var_name="stage", value_name="kg")
            fig = px.bar(stage_long, x="dish_name", y="kg", color="stage", title="Waste by production stage, by item", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Water performance")
    daily_util = metrics.daily_utility_variance(filtered_utility)
    fig = px.line(daily_util, x="date", y=["water_litres", "water_target_litres"], title="Daily water vs. seasonal, cover-adjusted target")
    st.plotly_chart(fig, use_container_width=True)
    weekly_util = metrics.weekly_utility_variance(filtered_utility)
    fig = px.bar(weekly_util.sort_values("water_variance_pct", key=lambda s: s.abs(), ascending=False), x="week_start", y="water_variance_pct", title="Weekly water variance vs. target (%, ranked by largest deviation)")
    st.plotly_chart(fig, use_container_width=True)
    monthly_util = metrics.monthly_utility_variance(filtered_utility)
    fig = px.bar(monthly_util, x="month", y=["water", "water_target"], barmode="group", title="Monthly water: actual vs. target")
    st.plotly_chart(fig, use_container_width=True)
    worst_water = weekly_util.reindex(weekly_util["water_variance_pct"].sort_values(ascending=False).index).head(3)
    st.caption("Weeks with the largest adverse water deviation: " + ", ".join(f"{r.week_start} ({r.water_variance_pct:+.1f}%)" for r in worst_water.itertuples()))

    st.markdown("#### Energy performance")
    fig = px.line(daily_util, x="date", y=["electricity_kwh", "electricity_target_kwh"], title="Daily electricity vs. seasonal, cover-adjusted target")
    st.plotly_chart(fig, use_container_width=True)
    fig = px.bar(weekly_util.sort_values("elec_variance_pct", key=lambda s: s.abs(), ascending=False), x="week_start", y="elec_variance_pct", title="Weekly electricity variance vs. target (%, ranked by largest deviation)")
    st.plotly_chart(fig, use_container_width=True)
    fig = px.bar(monthly_util, x="month", y=["elec", "elec_target"], barmode="group", title="Monthly electricity: actual vs. target")
    st.plotly_chart(fig, use_container_width=True)
    worst_elec = weekly_util.reindex(weekly_util["elec_variance_pct"].sort_values(ascending=False).index).head(3)
    st.caption("Weeks with the largest adverse electricity deviation: " + ", ".join(f"{r.week_start} ({r.elec_variance_pct:+.1f}%)" for r in worst_elec.itertuples()))

# ============================================================ TAB 2 =======
with tab2:
    st.subheader("Carbon-Costed Menu")
    st.caption("Which dishes and service periods create the largest carbon opportunity. Join keys: dish_id → sku → emission_factor, service_period.")

    top_pct = st.slider("Frequently-ordered threshold (top % of dishes by covers)", 0.1, 0.6, 0.30, 0.05)
    dish_table, frequently_ordered, threshold_covers = metrics.dish_carbon_table(filtered_full, filtered_waste, top_pct=top_pct)
    st.caption(f"Frequently ordered = covers_sold ≥ {threshold_covers:.0f} ({len(frequently_ordered)} of {len(dish_table)} dishes).")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Most carbon — frequently ordered**")
        top = frequently_ordered.sort_values("total_co2e_kg", ascending=False).head(15)
        st.dataframe(top[["dish_name", "covers_sold", "rank_by_covers", "total_co2e_kg", "co2e_per_cover", "revenue", "gross_profit", "food_waste_kg", "food_waste_value", "lower_impact_flag"]].style.format(
            {"total_co2e_kg": "{:.1f}", "co2e_per_cover": "{:.2f}", "revenue": "HK${:,.0f}", "gross_profit": "HK${:,.0f}", "food_waste_kg": "{:.1f}", "food_waste_value": "HK${:,.0f}"}
        ), use_container_width=True)
    with col2:
        st.markdown("**Least carbon — frequently ordered**")
        bottom = frequently_ordered.sort_values("total_co2e_kg", ascending=True).head(15)
        st.dataframe(bottom[["dish_name", "covers_sold", "rank_by_covers", "total_co2e_kg", "co2e_per_cover", "revenue", "gross_profit", "food_waste_kg", "food_waste_value", "lower_impact_flag"]].style.format(
            {"total_co2e_kg": "{:.1f}", "co2e_per_cover": "{:.2f}", "revenue": "HK${:,.0f}", "gross_profit": "HK${:,.0f}", "food_waste_kg": "{:.1f}", "food_waste_value": "HK${:,.0f}"}
        ), use_container_width=True)

    st.markdown("#### Carbon by service period")
    period_summary = metrics.carbon_by_service_period(filtered_full, carbon_target_by_period)
    st.dataframe(period_summary.style.format({"total_co2e_kg": "{:.1f}", "co2e_per_cover": "{:.2f}", "target_co2e_kg": "{:.1f}", "variance_kg": "{:+.1f}", "variance_pct": "{:+.1f}%"}), use_container_width=True)

    sel_period = st.selectbox("Service period detail", data_gen.SERVICE_PERIODS)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Top carbon contributors — {sel_period}**")
        st.dataframe(metrics.top_carbon_dishes_by_period(filtered_full, sel_period).style.format({"co2e_kg": "{:.1f}"}), use_container_width=True)
    with col2:
        st.markdown(f"**Lower-carbon, meaningful volume — {sel_period}**")
        st.dataframe(metrics.lower_carbon_dishes_with_volume_by_period(filtered_full, sel_period).style.format({"co2e_kg": "{:.1f}"}), use_container_width=True)

    st.markdown("#### Weekly carbon performance, by service period")
    weekly_carbon = metrics.weekly_carbon_by_period(filtered_full, carbon_target_by_period)
    fig = px.line(weekly_carbon, x="week_start", y="total_co2e_kg", color="service_period", title="Actual weekly CO2e by service period")
    st.plotly_chart(fig, use_container_width=True)
    fig = px.bar(weekly_carbon, x="week_start", y="variance_pct", color="service_period", barmode="group", title="Weekly carbon variance vs. target (%)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Largest carbon deviations (week x service period)**")
    st.dataframe(metrics.largest_carbon_deviations(weekly_carbon, n=10).style.format({"total_co2e_kg": "{:.1f}", "target_co2e_kg": "{:.1f}", "variance_kg": "{:+.1f}", "variance_pct": "{:+.1f}%"}), use_container_width=True)

    st.markdown("#### Actionable menu opportunities")
    opp = metrics.menu_opportunities(dish_table, n=5)
    oc1, oc2, oc3 = st.columns(3)
    with oc1:
        st.markdown("**Reformulate / resize / reprice**")
        st.dataframe(opp["reformulate_or_reprice"].style.format({"total_co2e_kg": "{:.1f}"}), use_container_width=True)
    with oc2:
        st.markdown("**Promote more (high-volume, lower-carbon)**")
        st.dataframe(opp["promote_more"].style.format({"total_co2e_kg": "{:.1f}"}), use_container_width=True)
    with oc3:
        st.markdown("**High carbon + high waste cost**")
        st.dataframe(opp["high_carbon_high_waste"].style.format({"total_co2e_kg": "{:.1f}", "food_waste_value": "HK${:,.0f}"}), use_container_width=True)

# ============================================================ TAB 3 =======
with tab3:
    st.subheader("Member Adoption Signal")
    st.caption("Demographics, not tiers. Only full and racing members are analyzed here; guests are excluded. Join keys: member_id → gender/age_group/membership_type, dish_id → lower_impact_flag.")

    trend = metrics.lower_impact_adoption_trend(filtered_full)
    switch_date = start_date + pd.Timedelta(days=switch_day)
    fig = px.line(trend, x="week_start", y="adoption_pct", title="Lower-impact adoption rate, weekly")
    fig.add_vline(x=pd.Timestamp(switch_date), line_dash="dash", line_color="red", annotation_text="Beef → Turkey switch (day 90)")
    st.plotly_chart(fig, use_container_width=True)

    eligible_trend = metrics.turkey_share_of_eligible_burger_orders_weekly(filtered_full, burger_dish_ids)
    fig = px.line(eligible_trend, x="week_start", y="turkey_share_pct", title="Turkey burger's share of eligible burger-category orders, weekly")
    fig.add_vline(x=pd.Timestamp(switch_date), line_dash="dash", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Demographic breakdown")
    dim = st.selectbox("Segment by", ["gender", "age_group", "membership_type"], format_func=lambda s: s.replace("_", " ").title())
    col1, col2 = st.columns(2)
    with col1:
        adoption = metrics.demographic_adoption(filtered_full, dim)
        fig = px.bar(adoption, x=dim, y="adoption_pct", title=f"Lower-impact adoption by {dim}")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        turkey_adoption = metrics.demographic_turkey_adoption(filtered_full, dim, switch_day, start_date)
        fig = px.bar(turkey_adoption, x=dim, y="turkey_adoption_pct", title=f"Post-switch turkey burger share by {dim}")
        st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Fastest to adopt: **{turkey_adoption.iloc[0][dim]}** ({turkey_adoption.iloc[0]['turkey_adoption_pct']:.1f}%). "
        f"Least likely: **{turkey_adoption.iloc[-1][dim]}** ({turkey_adoption.iloc[-1]['turkey_adoption_pct']:.1f}%)."
    )

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

# ============================================================ TAB 5 =======
with tab5:
    st.subheader("Data Join Health")
    st.caption("Quality and traceability of the joined dataset. Missing matches mean carbon or waste attribution silently fails for those records.")

    health = metrics.join_health(filtered_full)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("POS → recipe_master match", f"{health['dish_match_rate']:.1f}%")
    c2.metric("POS → member_profile match", f"{health['member_match_rate']:.1f}%")
    c3.metric("POS → outlet match", f"{health['outlet_match_rate']:.1f}%")
    c4.metric("Fully matched", f"{health['fully_matched_rate']:.1f}%")

    c5, c6 = st.columns(2)
    c5.metric("Waste records matched to dish/SKU", f"{metrics.waste_dish_match_rate(filtered_waste):.1f}%", help="Packaging waste (plastic/paper/other) is intentionally not dish-linked.")
    c6.metric("Utility records matched to date/covers", f"{metrics.utility_date_covers_match_rate(filtered_utility):.1f}%")

    st.write(f"Total POS transactions: **{health['total_transactions']:,}**")
    st.markdown("#### Sample of unmatched POS records")
    unmatched = metrics.unmatched_records(filtered_full, n=25)
    if len(unmatched) == 0:
        st.success("No unmatched records found.")
    else:
        st.dataframe(unmatched, use_container_width=True)
        st.warning(
            f"{(~filtered_full['fully_matched']).sum():,} of {health['total_transactions']:,} transactions failed at least one join. "
            "Unmatched dish_id rows cannot receive carbon or waste attribution; unmatched member_id rows cannot be attributed to a demographic segment — "
            "both would silently distort Tabs 2 and 3 if not surfaced here."
        )

# ============================================================ TAB 6 =======
with tab6:
    st.subheader("Case Study: Beef → Turkey Burger Substitution")
    st.write(
        "**Question:** Did replacing the beef burger with a turkey burger reduce environmental impact "
        "while improving business economics and member adoption?"
    )
    st.info(f"Menu change took effect on day {switch_day} of {n_days} ({(start_date + pd.Timedelta(days=switch_day)).date()}).")

    st.markdown("### 1. Carbon reduction")
    st.caption("Join used: recipe_master (emission_factor) × pos_transactions (covers, service_period, week_start).")
    carbon = metrics.carbon_reduction_panel(full_joined)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(x=["BEEF_BURGER (pre-switch)", "TURKEY_BURGER (post-switch)"], y=[carbon["beef_avg_co2e_kg"], carbon["turkey_avg_co2e_kg"]],
                     labels={"x": "Dish", "y": "Avg CO2e per cover (kg)"}, title="CO2e per cover")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(carbon["by_period"], x="service_period", y=["BEEF_BURGER", "TURKEY_BURGER"], barmode="group", title="Carbon impact by service period")
        st.plotly_chart(fig, use_container_width=True)
    fig = px.line(carbon["weekly"], x="week_start", y="co2e_kg", color="dish", title="Weekly carbon contribution")
    st.plotly_chart(fig, use_container_width=True)
    st.success(f"**{carbon['pct_reduction']:.1f}% reduction** in carbon per cover ({carbon['beef_covers']:,} beef covers vs. {carbon['turkey_covers']:,} turkey covers).")

    st.markdown("### 2. Waste reduction")
    st.caption("Join used: waste_log (dish_id, production_stage) × recipe_master (unit_cost, carried on waste_log directly).")
    stage_cmp, totals_cmp = metrics.waste_reduction_panel(waste_with_recipe, full_joined, switch_day, n_days)
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(stage_cmp, x="production_stage", y="weight_kg_per_week", color="dish_id", barmode="group", title="Waste per week, by stage")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(totals_cmp.style.format({"total_weight_kg": "{:.1f}", "value_hkd": "HK${:,.0f}", "waste_kg_per_cover": "{:.4f}"}), use_container_width=True)
    pr_change = metrics.plate_return_weekly_change(stage_cmp)
    st.success(
        f"Plate-return waste fell from **{pr_change['beef_kg_per_week']:.1f} kg/week** (beef) to **{pr_change['turkey_kg_per_week']:.1f} kg/week** "
        f"(turkey) — down **{pr_change['reduction_kg_per_week']:.1f} kg/week** (≈HK${pr_change['reduction_value_per_week']:,.0f}/week)."
    )

    st.markdown("### 3. Financial impact")
    st.caption("Join used: pos_transactions (price) × recipe_master (food_cost_per_portion, selling_price, gross_margin_per_portion).")
    fin = metrics.financial_impact_panel(full_joined, recipe_master, switch_day, n_days)
    fin_df = pd.DataFrame([fin["beef"], fin["turkey"]], index=["BEEF_BURGER", "TURKEY_BURGER"])
    st.dataframe(fin_df.style.format({
        "selling_price": "HK${:,.0f}", "food_cost_per_portion": "HK${:,.1f}", "gross_margin_per_portion": "HK${:,.1f}",
        "gross_margin_pct": "{:.1f}%", "revenue": "HK${:,.0f}", "gross_profit": "HK${:,.0f}",
        "revenue_per_week": "HK${:,.0f}", "gross_profit_per_week": "HK${:,.0f}",
    }), use_container_width=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Food cost saving per portion", f"{fin['food_cost_saving_pct']:.1f}%")
    c2.metric("Revenue change", f"HK${fin['revenue_change_per_week']:+,.0f}/week")
    c3.metric("Gross profit change", f"HK${fin['profit_change_per_week']:+,.0f}/week")

    st.markdown("### 4. Demographic adoption")
    st.caption("Join used: pos_transactions (member_id, dish_id) × member_profile (gender, age_group, membership_type, avg_visits_per_month, join_date).")
    demo_results = metrics.turkey_demographic_adoption_all(full_joined, switch_day, start_date)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.dataframe(demo_results["gender"].style.format({"turkey_adoption_pct": "{:.1f}%"}), use_container_width=True)
    with d2:
        st.dataframe(demo_results["age_group"].style.format({"turkey_adoption_pct": "{:.1f}%"}), use_container_width=True)
    with d3:
        st.dataframe(demo_results["membership_type"].style.format({"turkey_adoption_pct": "{:.1f}%"}), use_container_width=True)
    d4, d5 = st.columns(2)
    with d4:
        st.dataframe(demo_results["segment"].style.format({"turkey_adoption_pct": "{:.1f}%"}), use_container_width=True)
    with d5:
        st.dataframe(demo_results["tenure"].style.format({"turkey_adoption_pct": "{:.1f}%"}), use_container_width=True)

    compare_dim = st.selectbox("Compare pre-switch beef buyers vs. post-switch turkey buyers by", ["gender", "age_group", "membership_type"])
    mix = metrics.beef_vs_turkey_buyer_mix(full_joined, switch_day, start_date, compare_dim)
    fig = px.bar(mix, x=compare_dim, y=["beef_burger_buyers_pct", "turkey_burger_buyers_pct"], barmode="group", title=f"Buyer mix: beef (pre) vs. turkey (post), by {compare_dim}")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 5. Cannibalization and trade-offs")
    st.caption("Join used: pos_transactions (member_id, dish_id, price, timestamp) × member_profile (demographics) × recipe_master (margin).")
    canni = metrics.cannibalization_check(full_joined, burger_dish_ids, switch_day, start_date)
    st.write(f"Among **{canni['n_beef_buyers']:,}** historical beef-burger buyers:")
    fig = px.bar(
        x=["Adopted turkey burger", "Moved to another dish", "Stopped ordering from category"],
        y=[canni["pct_adopted_turkey"], canni["pct_moved_to_another_dish"], canni["pct_stopped_category"]],
        labels={"x": "Post-switch behavior", "y": "% of beef-burger buyers"}, title="Post-switch behavior",
    )
    st.plotly_chart(fig, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Spend per visit", f"{canni['spend_change_pct']:+.1f}%", f"HK${canni['spend_change_hkd']:+,.0f}")
    c2.metric("Carbon per visit", f"{canni['co2e_change_pct']:+.1f}%", f"{canni['co2e_change_kg']:+.2f} kg CO2e")
    c3.metric("Gross profit per visit", f"{canni['margin_change_pct']:+.1f}%", f"HK${canni['margin_change_hkd']:+,.0f}")

    st.markdown("### Executive summary")
    fastest_dim_row = demo_results["gender"].iloc[0]
    weakest_dim_row = demo_results["age_group"].iloc[-1]
    st.markdown(
        f"> After the burger substitution, turkey burger volume reached **{carbon['turkey_covers']:,} covers**, generating "
        f"**HK\\${fin['turkey']['revenue']:,.0f}** in revenue and **HK\\${fin['turkey']['gross_profit']:,.0f}** in gross profit. "
        f"Compared with beef burgers, it reduced carbon per cover by **{carbon['pct_reduction']:.1f}%**, reduced food cost per "
        f"portion by **{fin['food_cost_saving_pct']:.1f}%**, and reduced plate-return waste by "
        f"**{(pr_change['reduction_kg_per_week'] / pr_change['beef_kg_per_week'] * 100) if pr_change['beef_kg_per_week'] else 0:.1f}%**. "
        f"Adoption was strongest among **{fastest_dim_row['gender']}** members, while **{weakest_dim_row['age_group']}** "
        f"diners showed the largest opportunity for targeted promotion."
    )
