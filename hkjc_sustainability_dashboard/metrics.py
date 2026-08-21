"""
Metric calculations for the Club Sustainability Intelligence prototype.

Every function documents the join key(s) it depends on. Tab 6 (the
beef->turkey burger case study) computes everything from raw
pos_transactions + member_profile + recipe_master joins — there is no
separate "answer key" table anywhere in this module.

Waste/carbon targets (TARGET_WASTE_PER_COVER_KG, per-period carbon
targets) are passed as optional overrides so the sidebar can make them
adjustable without regenerating any data. Electricity/water targets are
computed once at generation time by targets.py's seasonal, cover- and
temperature-adjusted engine and carried on utility_log itself.
"""

import numpy as np
import pandas as pd

import targets


# ============================================================ TAB 1 =======

def weekly_operational_trend(waste_outlet: pd.DataFrame, utility_outlet: pd.DataFrame, full_joined: pd.DataFrame) -> pd.DataFrame:
    """
    Weekly trend of waste/utility, absolute and per-cover, with week-over-
    week % change. Join key used: week_start (derived from date on all
    three pre-scoped, outlet-filtered inputs), cover count as denominator.
    """
    food = waste_outlet[waste_outlet["waste_type"] == "food"].copy()
    food["value_hkd"] = food["weight_kg"] * food["unit_cost"]
    food_wk = food.groupby("week_start", as_index=False).agg(
        food_waste_kg=("weight_kg", "sum"), food_waste_hkd=("value_hkd", "sum")
    )
    util_wk = utility_outlet.groupby("week_start", as_index=False).agg(
        water_litres=("water_litres", "sum"), electricity_kwh=("electricity_kwh", "sum")
    )
    covers_wk = full_joined.groupby("week_start", as_index=False)["covers"].sum()

    merged = food_wk.merge(util_wk, on="week_start", how="outer").merge(covers_wk, on="week_start", how="outer")
    merged = merged.fillna(0).sort_values("week_start").reset_index(drop=True)

    merged["food_waste_per_cover"] = np.where(merged["covers"] > 0, merged["food_waste_kg"] / merged["covers"], 0)
    merged["water_per_cover"] = np.where(merged["covers"] > 0, merged["water_litres"] / merged["covers"], 0)
    merged["electricity_per_cover"] = np.where(merged["covers"] > 0, merged["electricity_kwh"] / merged["covers"], 0)

    for col in [
        "food_waste_kg", "food_waste_hkd", "water_litres", "electricity_kwh",
        "food_waste_per_cover", "water_per_cover", "electricity_per_cover",
    ]:
        merged[f"{col}_wow_pct"] = merged[col].pct_change() * 100

    return merged


def weekly_kpis(
    waste_outlet: pd.DataFrame, utility_outlet: pd.DataFrame, full_joined: pd.DataFrame,
    week_start, waste_target_per_cover: float = None,
) -> dict:
    """KPI cards for one selected week. Join key used: week_start, outlet_id (pre-scoped)."""
    food = waste_outlet[(waste_outlet["waste_type"] == "food") & (waste_outlet["week_start"] == week_start)].copy()
    food["value_hkd"] = food["weight_kg"] * food["unit_cost"]
    total_waste_kg = float(food["weight_kg"].sum())
    total_waste_hkd = float(food["value_hkd"].sum())

    util = utility_outlet[utility_outlet["week_start"] == week_start]
    total_water = float(util["water_litres"].sum())
    total_water_target = float(util["water_target_litres"].sum())
    total_elec = float(util["electricity_kwh"].sum())
    total_elec_target = float(util["electricity_target_kwh"].sum())

    covers = float(full_joined.loc[full_joined["week_start"] == week_start, "covers"].sum())
    waste_per_cover = total_waste_kg / covers if covers else 0.0
    waste_target_kg = targets.food_waste_target_kg(covers, waste_target_per_cover)

    def pct(actual, target):
        return (actual - target) / target * 100 if target else 0.0

    return {
        "total_waste_kg": total_waste_kg, "total_waste_hkd": total_waste_hkd,
        "total_water": total_water, "water_target": total_water_target,
        "water_variance": total_water - total_water_target, "water_variance_pct": pct(total_water, total_water_target),
        "total_elec": total_elec, "elec_target": total_elec_target,
        "elec_variance": total_elec - total_elec_target, "elec_variance_pct": pct(total_elec, total_elec_target),
        "covers": covers, "waste_per_cover": waste_per_cover,
        "waste_target_kg": waste_target_kg, "waste_variance_kg": total_waste_kg - waste_target_kg,
        "waste_variance_pct": pct(total_waste_kg, waste_target_kg),
    }


def food_waste_breakdown(waste_outlet: pd.DataFrame, full_joined: pd.DataFrame, week_start, n: int = 15) -> pd.DataFrame:
    """
    Wasted items for one week, with stage split and % of production
    wasted. Join keys used: dish_id -> sku (dish_name, portion weight from
    full_joined), week_start.
    """
    food = waste_outlet[(waste_outlet["waste_type"] == "food") & (waste_outlet["week_start"] == week_start)].copy()
    food["value_hkd"] = food["weight_kg"] * food["unit_cost"]
    total_week_waste = food["weight_kg"].sum()

    by_dish = food.groupby("dish_id", as_index=False).agg(waste_kg=("weight_kg", "sum"), value_hkd=("value_hkd", "sum"))
    by_dish["share_pct"] = (by_dish["waste_kg"] / total_week_waste * 100).round(1) if total_week_waste else 0.0

    stage = (
        food.groupby(["dish_id", "production_stage"], as_index=False)["weight_kg"].sum()
        .pivot(index="dish_id", columns="production_stage", values="weight_kg")
        .fillna(0)
        .reset_index()
    )

    week_covers = full_joined[(full_joined["week_start"] == week_start) & full_joined["dish_matched"]]
    covers_by_dish = week_covers.groupby("dish_id", as_index=False).agg(
        covers_sold=("covers", "sum"), portion_weight_g=("portion_weight_g", "first"), dish_name=("dish_name", "first")
    )
    covers_by_dish["sold_kg"] = covers_by_dish["covers_sold"] * covers_by_dish["portion_weight_g"] / 1000.0

    merged = by_dish.merge(stage, on="dish_id", how="left").merge(covers_by_dish, on="dish_id", how="left")
    merged["sold_kg"] = merged["sold_kg"].fillna(0)
    merged["production_kg"] = merged["sold_kg"] + merged["waste_kg"]
    merged["pct_of_production_wasted"] = (
        merged["waste_kg"] / merged["production_kg"].replace(0, pd.NA) * 100
    ).astype(float).round(1)

    return merged.sort_values("waste_kg", ascending=False).head(n)


def daily_utility_variance(utility_outlet: pd.DataFrame) -> pd.DataFrame:
    """Daily actual vs. seasonal/cover-adjusted target, with variance. Join key: outlet_id (pre-scoped)."""
    df = utility_outlet.sort_values("date").copy()
    df["water_variance_litres"] = df["water_litres"] - df["water_target_litres"]
    df["water_variance_pct"] = df["water_variance_litres"] / df["water_target_litres"] * 100
    df["elec_variance_kwh"] = df["electricity_kwh"] - df["electricity_target_kwh"]
    df["elec_variance_pct"] = df["elec_variance_kwh"] / df["electricity_target_kwh"] * 100
    return df


def weekly_utility_variance(utility_outlet: pd.DataFrame) -> pd.DataFrame:
    """Join key used: week_start."""
    wk = utility_outlet.groupby("week_start", as_index=False).agg(
        water=("water_litres", "sum"), water_target=("water_target_litres", "sum"),
        elec=("electricity_kwh", "sum"), elec_target=("electricity_target_kwh", "sum"),
    )
    wk["water_variance"] = wk["water"] - wk["water_target"]
    wk["water_variance_pct"] = wk["water_variance"] / wk["water_target"] * 100
    wk["elec_variance"] = wk["elec"] - wk["elec_target"]
    wk["elec_variance_pct"] = wk["elec_variance"] / wk["elec_target"] * 100
    return wk.sort_values("water_variance_pct", key=lambda s: s.abs(), ascending=False)


def monthly_utility_variance(utility_outlet: pd.DataFrame) -> pd.DataFrame:
    """Join key used: month."""
    mo = utility_outlet.groupby("month", as_index=False).agg(
        water=("water_litres", "sum"), water_target=("water_target_litres", "sum"),
        elec=("electricity_kwh", "sum"), elec_target=("electricity_target_kwh", "sum"),
    )
    mo["water_variance"] = mo["water"] - mo["water_target"]
    mo["water_variance_pct"] = mo["water_variance"] / mo["water_target"] * 100
    mo["elec_variance"] = mo["elec"] - mo["elec_target"]
    mo["elec_variance_pct"] = mo["elec_variance"] / mo["elec_target"] * 100
    return mo.sort_values("month")


# ============================================================ TAB 2 =======

def dish_carbon_table(full_joined: pd.DataFrame, waste_outlet: pd.DataFrame, top_pct: float = 0.30) -> tuple:
    """
    Full dish economics/carbon table plus the "frequently ordered" subset
    (top `top_pct` of dishes by covers — a transparent, adjustable
    threshold). Join keys used: dish_id -> sku -> emission_factor
    (co2e_kg from full_join), service_period mix, dish_id -> waste value.
    """
    matched = full_joined[full_joined["dish_matched"]]
    grouped = matched.groupby(["dish_id", "dish_name"], as_index=False).agg(
        covers_sold=("covers", "sum"), co2e_per_cover=("co2e_kg", "mean"),
        revenue=("price", "sum"), gross_profit=("margin", "sum"),
    )
    grouped["total_co2e_kg"] = grouped["covers_sold"] * grouped["co2e_per_cover"]

    mix = matched.groupby(["dish_id", "service_period"], as_index=False)["covers"].sum()
    mix_pivot = mix.pivot(index="dish_id", columns="service_period", values="covers").fillna(0)
    mix_pivot = (mix_pivot.div(mix_pivot.sum(axis=1), axis=0) * 100).round(1).reset_index()

    food_waste = waste_outlet[waste_outlet["waste_type"] == "food"].copy()
    food_waste["value_hkd"] = food_waste["weight_kg"] * food_waste["unit_cost"]
    fw = food_waste.groupby("dish_id", as_index=False).agg(food_waste_kg=("weight_kg", "sum"), food_waste_value=("value_hkd", "sum"))

    lower_impact = matched.groupby("dish_id", as_index=False)["lower_impact_flag"].first()

    merged = grouped.merge(mix_pivot, on="dish_id", how="left").merge(fw, on="dish_id", how="left").merge(lower_impact, on="dish_id", how="left")
    merged[["food_waste_kg", "food_waste_value"]] = merged[["food_waste_kg", "food_waste_value"]].fillna(0)
    merged["rank_by_covers"] = merged["covers_sold"].rank(ascending=False, method="min").astype(int)

    threshold_covers = merged["covers_sold"].quantile(1 - top_pct)
    frequently_ordered = merged[merged["covers_sold"] >= threshold_covers]
    return merged, frequently_ordered, float(threshold_covers)


def carbon_by_service_period(full_joined: pd.DataFrame, target_by_period: dict = None) -> pd.DataFrame:
    """Join keys used: service_period, dish_id -> sku -> emission_factor."""
    matched = full_joined[full_joined["dish_matched"]]
    grouped = matched.groupby("service_period", as_index=False).agg(total_co2e_kg=("co2e_kg", "sum"), covers=("covers", "sum"))
    grouped["co2e_per_cover"] = grouped["total_co2e_kg"] / grouped["covers"]
    grouped["target_co2e_kg"] = grouped.apply(
        lambda r: targets.carbon_target_kg(r["service_period"], r["covers"], target_by_period), axis=1
    )
    grouped["variance_kg"] = grouped["total_co2e_kg"] - grouped["target_co2e_kg"]
    grouped["variance_pct"] = grouped["variance_kg"] / grouped["target_co2e_kg"] * 100
    return grouped


def top_carbon_dishes_by_period(full_joined: pd.DataFrame, service_period: str, n: int = 5) -> pd.DataFrame:
    matched = full_joined[(full_joined["dish_matched"]) & (full_joined["service_period"] == service_period)]
    grouped = matched.groupby("dish_name", as_index=False)["co2e_kg"].sum().sort_values("co2e_kg", ascending=False)
    return grouped.head(n)


def lower_carbon_dishes_with_volume_by_period(full_joined: pd.DataFrame, service_period: str, n: int = 5) -> pd.DataFrame:
    matched = full_joined[
        (full_joined["dish_matched"]) & (full_joined["service_period"] == service_period) & (full_joined["lower_impact_flag"] == True)  # noqa: E712
    ]
    grouped = matched.groupby("dish_name", as_index=False).agg(covers=("covers", "sum"), co2e_kg=("co2e_kg", "sum"))
    return grouped.sort_values("covers", ascending=False).head(n)


def weekly_carbon_by_period(full_joined: pd.DataFrame, target_by_period: dict = None) -> pd.DataFrame:
    """Join keys used: week_start, service_period."""
    matched = full_joined[full_joined["dish_matched"]]
    grouped = matched.groupby(["week_start", "service_period"], as_index=False).agg(
        total_co2e_kg=("co2e_kg", "sum"), covers=("covers", "sum")
    )
    grouped["co2e_per_cover"] = grouped["total_co2e_kg"] / grouped["covers"]
    grouped["target_co2e_kg"] = grouped.apply(
        lambda r: targets.carbon_target_kg(r["service_period"], r["covers"], target_by_period), axis=1
    )
    grouped["variance_kg"] = grouped["total_co2e_kg"] - grouped["target_co2e_kg"]
    grouped["variance_pct"] = grouped["variance_kg"] / grouped["target_co2e_kg"] * 100
    return grouped.sort_values(["week_start", "service_period"])


def largest_carbon_deviations(weekly_carbon_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return weekly_carbon_df.reindex(weekly_carbon_df["variance_kg"].abs().sort_values(ascending=False).index).head(n)


def menu_opportunities(dish_table: pd.DataFrame, n: int = 5) -> dict:
    median_covers = dish_table["covers_sold"].median()
    high_vol = dish_table[dish_table["covers_sold"] >= median_covers]

    reformulate = high_vol.sort_values("total_co2e_kg", ascending=False).head(n)
    promote_more = dish_table[dish_table["lower_impact_flag"] == True].sort_values("covers_sold", ascending=False).head(n)  # noqa: E712

    carbon_q = dish_table["total_co2e_kg"].quantile(0.75)
    waste_q = dish_table["food_waste_value"].quantile(0.75)
    high_carbon_high_waste = dish_table[(dish_table["total_co2e_kg"] >= carbon_q) & (dish_table["food_waste_value"] >= waste_q)]

    return {
        "reformulate_or_reprice": reformulate[["dish_name", "covers_sold", "total_co2e_kg"]],
        "promote_more": promote_more[["dish_name", "covers_sold", "total_co2e_kg"]],
        "high_carbon_high_waste": high_carbon_high_waste[["dish_name", "total_co2e_kg", "food_waste_value"]],
    }


# ============================================================ TAB 3 =======

def lower_impact_adoption_trend(full_joined: pd.DataFrame) -> pd.DataFrame:
    """Weekly aggregate adoption trend, full/racing members only. Join keys: member_id -> membership_type, dish_id -> lower_impact_flag."""
    df = full_joined[full_joined["dish_matched"] & full_joined["member_matched"] & full_joined["membership_type"].notna()]
    grouped = df.groupby("week_start", as_index=False).agg(total_covers=("covers", "sum"), lower_impact_covers=("lower_impact_flag", "sum"))
    grouped["adoption_pct"] = (grouped["lower_impact_covers"] / grouped["total_covers"] * 100).round(1)
    return grouped.sort_values("week_start")


def turkey_share_of_eligible_burger_orders_weekly(full_joined: pd.DataFrame, burger_dish_ids: set) -> pd.DataFrame:
    """% of burger-category orders that are TURKEY_BURGER, by week. Join key: dish_id membership in burger category."""
    matched = full_joined[full_joined["dish_matched"] & full_joined["dish_id"].isin(burger_dish_ids)].copy()
    matched["is_turkey"] = matched["dish_id"] == "TURKEY_BURGER"
    grouped = matched.groupby("week_start", as_index=False).agg(eligible_orders=("covers", "sum"), turkey_orders=("is_turkey", "sum"))
    grouped["turkey_share_pct"] = (grouped["turkey_orders"] / grouped["eligible_orders"] * 100).round(1)
    return grouped.sort_values("week_start")


def demographic_adoption(full_joined: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Lower-impact adoption by one demographic dimension. Join key: member_id -> `dim` (member_profile), dish_id -> lower_impact_flag."""
    df = full_joined[full_joined["dish_matched"] & full_joined["member_matched"] & full_joined[dim].notna()]
    grouped = df.groupby(dim, as_index=False).agg(total_covers=("covers", "sum"), lower_impact_covers=("lower_impact_flag", "sum"))
    grouped["adoption_pct"] = (grouped["lower_impact_covers"] / grouped["total_covers"] * 100).round(1)
    return grouped.sort_values("adoption_pct", ascending=False)


def demographic_turkey_adoption(full_joined: pd.DataFrame, dim: str, switch_day: int, start_date: pd.Timestamp) -> pd.DataFrame:
    """Post-switch turkey-burger share, by demographic dimension. Join key: member_id -> `dim`, dish_id."""
    df = full_joined[full_joined["dish_matched"] & full_joined["member_matched"] & full_joined[dim].notna()].copy()
    df["day_idx"] = (pd.to_datetime(df["date"]) - start_date).dt.days
    post = df[df["day_idx"] >= switch_day].copy()
    post["is_turkey"] = post["dish_id"] == "TURKEY_BURGER"
    grouped = post.groupby(dim, as_index=False).agg(total_covers=("covers", "sum"), turkey_covers=("is_turkey", "sum"))
    grouped["turkey_adoption_pct"] = (grouped["turkey_covers"] / grouped["total_covers"] * 100).round(2)
    return grouped.sort_values("turkey_adoption_pct", ascending=False)


def dish_waste_per_cover_lookup(waste_outlet: pd.DataFrame, full_joined: pd.DataFrame) -> pd.Series:
    """Average food-waste kg attributed per cover, by dish. Join key: dish_id."""
    food = waste_outlet[waste_outlet["waste_type"] == "food"]
    total_waste = food.groupby("dish_id")["weight_kg"].sum()
    covers = full_joined[full_joined["dish_matched"]].groupby("dish_id")["covers"].sum()
    return (total_waste / covers).fillna(0)


def frequency_segment_comparison(
    full_joined: pd.DataFrame, switch_day: int, start_date: pd.Timestamp, dish_waste_lookup: pd.Series = None
) -> pd.DataFrame:
    """
    Frequent vs. occasional diners, pre/post switch. Join keys used:
    member_id -> avg_visits_per_month, dish_id -> co2e_kg/lower_impact_flag,
    dish_id -> waste per cover (dish_waste_lookup, computed via joins.waste_for_outlet).
    """
    df = full_joined[
        full_joined["member_matched"] & full_joined["dish_matched"] & full_joined["avg_visits_per_month"].notna()
    ].copy()
    df["day_idx"] = (pd.to_datetime(df["date"]) - start_date).dt.days
    df["period"] = np.where(df["day_idx"] < switch_day, "pre-switch", "post-switch")
    df["segment"] = np.where(df["avg_visits_per_month"] > 8, "frequent (>8 visits/mo)", "occasional (<=8 visits/mo)")
    df["is_turkey"] = df["dish_id"] == "TURKEY_BURGER"
    if dish_waste_lookup is not None:
        df["attributed_waste_kg"] = df["dish_id"].map(dish_waste_lookup).fillna(0)
    else:
        df["attributed_waste_kg"] = 0.0

    grouped = df.groupby(["segment", "period"], as_index=False).agg(
        total_covers=("covers", "sum"), turkey_covers=("is_turkey", "sum"),
        avg_spend=("price", "mean"), avg_visits=("avg_visits_per_month", "mean"),
        avg_co2e_per_cover=("co2e_kg", "mean"), avg_waste_per_cover=("attributed_waste_kg", "mean"),
        revenue=("price", "sum"),
    )
    grouped["turkey_adoption_pct"] = (grouped["turkey_covers"] / grouped["total_covers"] * 100).round(2)
    grouped["avg_spend"] = grouped["avg_spend"].round(1)
    grouped["avg_visits"] = grouped["avg_visits"].round(1)
    grouped["avg_co2e_per_cover"] = grouped["avg_co2e_per_cover"].round(2)
    grouped["avg_waste_per_cover"] = grouped["avg_waste_per_cover"].round(3)
    return grouped


# ============================================================ TAB 4 =======

def target_scorecard(
    waste_outlet: pd.DataFrame, utility_outlet: pd.DataFrame, full_joined: pd.DataFrame,
    period: str = "week", period_value=None,
    waste_target_per_cover: float = None, carbon_target_by_period: dict = None,
) -> pd.DataFrame:
    """
    Actual/target/variance for one week or month. Join key used:
    week_start or month (present on all three pre-scoped inputs).
    """
    col = "week_start" if period == "week" else "month"
    if period_value is None:
        vals = sorted(full_joined[col].dropna().unique())
        period_value = vals[-1] if vals else None

    food = waste_outlet[(waste_outlet["waste_type"] == "food") & (waste_outlet[col] == period_value)].copy()
    food["value_hkd"] = food["weight_kg"] * food["unit_cost"]
    waste_kg = float(food["weight_kg"].sum())
    waste_hkd = float(food["value_hkd"].sum())

    util = utility_outlet[utility_outlet[col] == period_value]
    water = float(util["water_litres"].sum())
    water_target = float(util["water_target_litres"].sum())
    elec = float(util["electricity_kwh"].sum())
    elec_target = float(util["electricity_target_kwh"].sum())

    pos = full_joined[full_joined[col] == period_value]
    covers = float(pos["covers"].sum())
    matched = pos[pos["dish_matched"]]
    carbon = float(matched["co2e_kg"].sum())

    waste_target_kg = targets.food_waste_target_kg(covers, waste_target_per_cover)
    hkd_per_kg = (waste_hkd / waste_kg) if waste_kg else 15.0
    waste_hkd_target = waste_target_kg * hkd_per_kg

    period_covers = matched.groupby("service_period")["covers"].sum()
    carbon_target_total = sum(
        targets.carbon_target_kg(p, c, carbon_target_by_period) for p, c in period_covers.items()
    )

    def row(label, actual, target, unit):
        variance = actual - target
        pct = variance / target * 100 if target else 0.0
        if pct < -5:
            status = "Below target"
        elif abs(pct) <= 5:
            status = "On target"
        elif pct <= 15:
            status = "Slightly above target"
        else:
            status = "Materially above target"
        return {"metric": label, "actual": actual, "target": target, "variance": variance, "variance_pct": pct, "unit": unit, "status": status}

    rows = [
        row("Food waste kg", waste_kg, waste_target_kg, "kg"),
        row("Food waste HK$", waste_hkd, waste_hkd_target, "HK$"),
        row("Food waste per cover", waste_kg / covers if covers else 0, waste_target_per_cover or targets.TARGET_WASTE_PER_COVER_KG, "kg/cover"),
        row("Water litres", water, water_target, "litres"),
        row("Water per cover", water / covers if covers else 0, water_target / covers if covers else 0, "litres/cover"),
        row("Electricity kWh", elec, elec_target, "kWh"),
        row("Electricity per cover", elec / covers if covers else 0, elec_target / covers if covers else 0, "kWh/cover"),
        row("Carbon emissions", carbon, carbon_target_total, "kg CO2e"),
        row("Carbon per cover", carbon / covers if covers else 0, carbon_target_total / covers if covers else 0, "kg CO2e/cover"),
    ]
    return pd.DataFrame(rows)


def weekly_variance_summary(
    waste_outlet: pd.DataFrame, utility_outlet: pd.DataFrame, full_joined: pd.DataFrame, waste_target_per_cover: float = None
) -> pd.DataFrame:
    """One row per week with % variance for waste/water/electricity/carbon — feeds the heatmap and worst/best lists."""
    weeks = sorted(full_joined["week_start"].dropna().unique())
    rows = []
    for wk in weeks:
        sc = target_scorecard(waste_outlet, utility_outlet, full_joined, period="week", period_value=wk, waste_target_per_cover=waste_target_per_cover)
        d = sc.set_index("metric")["variance_pct"]
        rows.append(
            {
                "week_start": wk,
                "Food waste kg": d.get("Food waste kg", 0),
                "Water litres": d.get("Water litres", 0),
                "Electricity kWh": d.get("Electricity kWh", 0),
                "Carbon emissions": d.get("Carbon emissions", 0),
            }
        )
    df = pd.DataFrame(rows)
    df["avg_variance_pct"] = df[["Food waste kg", "Water litres", "Electricity kWh", "Carbon emissions"]].mean(axis=1)
    return df


def monthly_variance_summary(
    waste_outlet: pd.DataFrame, utility_outlet: pd.DataFrame, full_joined: pd.DataFrame, waste_target_per_cover: float = None
) -> pd.DataFrame:
    months = sorted(full_joined["month"].dropna().unique())
    frames = []
    for mo in months:
        sc = target_scorecard(waste_outlet, utility_outlet, full_joined, period="month", period_value=mo, waste_target_per_cover=waste_target_per_cover)
        sc["month"] = mo
        frames.append(sc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def worst_best_weeks(weekly_variance_df: pd.DataFrame, n: int = 5) -> tuple:
    worst = weekly_variance_df.sort_values("avg_variance_pct", ascending=False).head(n)
    best = weekly_variance_df.sort_values("avg_variance_pct", ascending=True).head(n)
    return worst, best


# ============================================================ TAB 5 =======

def join_health(full_joined: pd.DataFrame) -> dict:
    n = len(full_joined)
    return {
        "total_transactions": n,
        "outlet_match_rate": full_joined["outlet_matched"].mean() * 100,
        "dish_match_rate": full_joined["dish_matched"].mean() * 100,
        "member_match_rate": full_joined["member_matched"].mean() * 100,
        "fully_matched_rate": full_joined["fully_matched"].mean() * 100,
    }


def waste_dish_match_rate(waste_outlet: pd.DataFrame) -> float:
    """% of food waste rows with a dish_id (packaging waste is intentionally dish_id-less). Join key: dish_id -> sku."""
    food = waste_outlet[waste_outlet["waste_type"] == "food"]
    return float(food["dish_id"].notna().mean() * 100) if len(food) else 100.0


def utility_date_covers_match_rate(utility_outlet: pd.DataFrame) -> float:
    """% of utility_log rows with a valid daily_covers figure (join key: date)."""
    return float((utility_outlet["daily_covers"] > 0).mean() * 100) if len(utility_outlet) else 100.0


def unmatched_records(full_joined: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    cols = ["check_number", "outlet_id", "outlet_matched", "dish_id", "dish_matched", "member_id", "member_matched", "timestamp"]
    return full_joined[~full_joined["fully_matched"]][cols].head(n)


# ============================================================ TAB 6 =======
# Beef -> turkey burger case study. Every function reads only from
# full_joined / waste_with_recipe / recipe_master — nothing is
# precomputed or stashed outside the standard join pipeline.

def carbon_reduction_panel(full_joined: pd.DataFrame) -> dict:
    """Panel 1. Join used: recipe_master (emission_factor) x pos_transactions (covers, service_period, week_start)."""
    beef = full_joined[full_joined["dish_id"] == "BEEF_BURGER"]
    turkey = full_joined[full_joined["dish_id"] == "TURKEY_BURGER"]
    beef_avg = float(beef["co2e_kg"].mean()) if len(beef) else 0.0
    turkey_avg = float(turkey["co2e_kg"].mean()) if len(turkey) else 0.0
    pct_reduction = (beef_avg - turkey_avg) / beef_avg * 100 if beef_avg else 0.0

    by_period = pd.concat(
        [beef.groupby("service_period")["co2e_kg"].sum().rename("BEEF_BURGER"),
         turkey.groupby("service_period")["co2e_kg"].sum().rename("TURKEY_BURGER")],
        axis=1,
    ).fillna(0).reset_index()

    weekly = pd.concat(
        [beef.groupby("week_start")["co2e_kg"].sum().reset_index().assign(dish="BEEF_BURGER"),
         turkey.groupby("week_start")["co2e_kg"].sum().reset_index().assign(dish="TURKEY_BURGER")],
        ignore_index=True,
    )

    return {
        "beef_avg_co2e_kg": beef_avg, "turkey_avg_co2e_kg": turkey_avg, "pct_reduction": pct_reduction,
        "beef_total_co2e_kg": float(beef["co2e_kg"].sum()), "turkey_total_co2e_kg": float(turkey["co2e_kg"].sum()),
        "beef_covers": int(beef["covers"].sum()), "turkey_covers": int(turkey["covers"].sum()),
        "by_period": by_period, "weekly": weekly,
    }


def waste_reduction_panel(waste_with_recipe_df: pd.DataFrame, full_joined: pd.DataFrame, switch_day: int, n_days: int) -> tuple:
    """Panel 2. Join used: waste_log (dish_id, production_stage) x recipe_master (unit_cost, on waste_log directly)."""
    df = waste_with_recipe_df[waste_with_recipe_df["dish_id"].isin(["BEEF_BURGER", "TURKEY_BURGER"])].copy()
    df["value_hkd"] = df["weight_kg"] * df["unit_cost"]

    stage = df.groupby(["dish_id", "production_stage"], as_index=False).agg(total_weight_kg=("weight_kg", "sum"), value_hkd=("value_hkd", "sum"))
    active_days = {"BEEF_BURGER": switch_day, "TURKEY_BURGER": n_days - switch_day}
    stage["active_weeks"] = stage["dish_id"].map(active_days) / 7.0
    stage["weight_kg_per_week"] = stage["total_weight_kg"] / stage["active_weeks"]
    stage["value_hkd_per_week"] = stage["value_hkd"] / stage["active_weeks"]

    covers = full_joined[full_joined["dish_id"].isin(["BEEF_BURGER", "TURKEY_BURGER"])].groupby("dish_id")["covers"].sum()
    totals = df.groupby("dish_id", as_index=False).agg(total_weight_kg=("weight_kg", "sum"), value_hkd=("value_hkd", "sum"))
    totals["covers"] = totals["dish_id"].map(covers).fillna(0)
    totals["waste_kg_per_cover"] = totals["total_weight_kg"] / totals["covers"].replace(0, pd.NA)

    return stage, totals


def plate_return_weekly_change(stage_df: pd.DataFrame) -> dict:
    pr = stage_df[stage_df["production_stage"] == "plate-return"].set_index("dish_id")
    def get(dish, col):
        return float(pr.loc[dish, col]) if dish in pr.index else 0.0
    beef_wk, turkey_wk = get("BEEF_BURGER", "weight_kg_per_week"), get("TURKEY_BURGER", "weight_kg_per_week")
    beef_val, turkey_val = get("BEEF_BURGER", "value_hkd_per_week"), get("TURKEY_BURGER", "value_hkd_per_week")
    return {
        "beef_kg_per_week": beef_wk, "turkey_kg_per_week": turkey_wk,
        "reduction_kg_per_week": beef_wk - turkey_wk, "reduction_value_per_week": beef_val - turkey_val,
    }


def financial_impact_panel(full_joined: pd.DataFrame, recipe_master: pd.DataFrame, switch_day: int, n_days: int) -> dict:
    """Panel 3. Join used: pos_transactions (price) x recipe_master (food_cost_per_portion, selling_price, margin)."""
    beef = full_joined[full_joined["dish_id"] == "BEEF_BURGER"]
    turkey = full_joined[full_joined["dish_id"] == "TURKEY_BURGER"]
    beef_recipe = recipe_master[recipe_master["dish_id"] == "BEEF_BURGER"].iloc[0]
    turkey_recipe = recipe_master[recipe_master["dish_id"] == "TURKEY_BURGER"].iloc[0]

    food_cost_saving_pct = (
        (beef_recipe["food_cost_per_portion"] - turkey_recipe["food_cost_per_portion"]) / beef_recipe["food_cost_per_portion"] * 100
    )

    def dish_financials(df, recipe_row, weeks):
        covers = int(df["covers"].sum())
        revenue = float(df["price"].sum())
        gross_profit = float((df["price"] - recipe_row["food_cost_per_portion"]).sum())
        return {
            "selling_price": float(recipe_row["selling_price"]), "food_cost_per_portion": float(recipe_row["food_cost_per_portion"]),
            "gross_margin_per_portion": float(recipe_row["gross_margin_per_portion"]),
            "gross_margin_pct": float(recipe_row["gross_margin_per_portion"] / recipe_row["selling_price"] * 100),
            "covers": covers, "revenue": revenue, "gross_profit": gross_profit,
            "revenue_per_week": revenue / weeks if weeks else 0.0, "gross_profit_per_week": gross_profit / weeks if weeks else 0.0,
        }

    beef_fin = dish_financials(beef, beef_recipe, switch_day / 7.0)
    turkey_fin = dish_financials(turkey, turkey_recipe, (n_days - switch_day) / 7.0)

    return {
        "beef": beef_fin, "turkey": turkey_fin,
        "food_cost_saving_pct": float(food_cost_saving_pct),
        "revenue_change_per_week": turkey_fin["revenue_per_week"] - beef_fin["revenue_per_week"],
        "profit_change_per_week": turkey_fin["gross_profit_per_week"] - beef_fin["gross_profit_per_week"],
    }


def turkey_demographic_adoption_all(full_joined: pd.DataFrame, switch_day: int, start_date: pd.Timestamp) -> dict:
    """Panel 4. Join used: pos_transactions (member_id, dish_id) x member_profile (gender, age_group, membership_type, avg_visits_per_month, join_date)."""
    df = full_joined[full_joined["member_matched"] & full_joined["membership_type"].notna()].copy()
    df["day_idx"] = (pd.to_datetime(df["date"]) - start_date).dt.days
    post = df[df["day_idx"] >= switch_day].copy()
    post["is_turkey"] = post["dish_id"] == "TURKEY_BURGER"
    post["segment"] = np.where(post["avg_visits_per_month"] > 8, "frequent", "occasional")
    days_since_join = (start_date - pd.to_datetime(post["join_date"])).dt.days
    post["tenure"] = np.where(days_since_join < 365 * 2, "newer (<2yr)", "longer-tenure (>=2yr)")

    results = {}
    for dim in ["gender", "age_group", "membership_type", "segment", "tenure"]:
        grouped = post.groupby(dim, as_index=False).agg(total_covers=("covers", "sum"), turkey_covers=("is_turkey", "sum"))
        grouped["turkey_adoption_pct"] = (grouped["turkey_covers"] / grouped["total_covers"] * 100).round(2)
        results[dim] = grouped.sort_values("turkey_adoption_pct", ascending=False)
    return results


def _buyer_demographic_mix(df: pd.DataFrame, dim: str) -> pd.Series:
    counts = df.drop_duplicates("member_id").groupby(dim)["member_id"].count()
    return (counts / counts.sum() * 100).round(1) if counts.sum() else counts


def beef_vs_turkey_buyer_mix(full_joined: pd.DataFrame, switch_day: int, start_date: pd.Timestamp, dim: str) -> pd.DataFrame:
    """Compare pre-switch beef buyers vs. post-switch turkey buyers by one demographic dimension."""
    df = full_joined[full_joined["member_matched"] & full_joined["membership_type"].notna()].copy()
    df["day_idx"] = (pd.to_datetime(df["date"]) - start_date).dt.days
    beef_buyers = df[(df["dish_id"] == "BEEF_BURGER") & (df["day_idx"] < switch_day)]
    turkey_buyers = df[(df["dish_id"] == "TURKEY_BURGER") & (df["day_idx"] >= switch_day)]
    beef_pct = _buyer_demographic_mix(beef_buyers, dim).rename("beef_burger_buyers_pct")
    turkey_pct = _buyer_demographic_mix(turkey_buyers, dim).rename("turkey_burger_buyers_pct")
    return pd.concat([beef_pct, turkey_pct], axis=1).fillna(0).reset_index()


def cannibalization_check(full_joined: pd.DataFrame, burger_dish_ids: set, switch_day: int, start_date: pd.Timestamp) -> dict:
    """
    Panel 5. Join used: pos_transactions (member_id, dish_id, price,
    timestamp) x member_profile (demographics) x recipe_master (margin).
    For all historical beef-burger buyers, classify their post-switch
    behavior purely from their own subsequent transactions.
    """
    df = full_joined[full_joined["member_matched"] & full_joined["membership_type"].notna()].copy()
    df["day_idx"] = (pd.to_datetime(df["date"]) - start_date).dt.days
    pre = df[df["day_idx"] < switch_day]
    post = df[df["day_idx"] >= switch_day]

    beef_pre_members = pre.loc[pre["dish_id"] == "BEEF_BURGER", "member_id"].unique()
    if len(beef_pre_members) == 0:
        return {
            "n_beef_buyers": 0, "pct_adopted_turkey": 0.0, "pct_moved_to_another_dish": 0.0, "pct_stopped_category": 0.0,
            "spend_change_hkd": 0.0, "spend_change_pct": 0.0, "co2e_change_kg": 0.0, "co2e_change_pct": 0.0,
            "margin_change_hkd": 0.0, "margin_change_pct": 0.0,
        }

    post_group = post[post["member_id"].isin(beef_pre_members)]
    turkey_members = set(post_group.loc[post_group["dish_id"] == "TURKEY_BURGER", "member_id"])
    other_burger_members = set(post_group.loc[post_group["dish_id"] == "CHICKEN_BURGER", "member_id"]) - turkey_members

    labels = []
    for m in beef_pre_members:
        if m in turkey_members:
            labels.append("adopted_turkey")
        elif m in other_burger_members:
            labels.append("moved_to_another_dish")
        else:
            labels.append("stopped_category")
    counts = pd.Series(labels).value_counts(normalize=True) * 100

    def mean_change(pre_s, post_s):
        common = pre_s.index.intersection(post_s.index)
        if len(common) == 0:
            return 0.0, 0.0
        change = float((post_s.loc[common] - pre_s.loc[common]).mean())
        base = float(pre_s.loc[common].mean())
        return change, (change / base * 100 if base else 0.0)

    pre_g = pre[pre["member_id"].isin(beef_pre_members)]
    spend_change, spend_change_pct = mean_change(pre_g.groupby("member_id")["price"].mean(), post_group.groupby("member_id")["price"].mean())
    co2e_change, co2e_change_pct = mean_change(pre_g.groupby("member_id")["co2e_kg"].mean(), post_group.groupby("member_id")["co2e_kg"].mean())
    margin_change, margin_change_pct = mean_change(pre_g.groupby("member_id")["margin"].mean(), post_group.groupby("member_id")["margin"].mean())

    return {
        "n_beef_buyers": int(len(beef_pre_members)),
        "pct_adopted_turkey": float(counts.get("adopted_turkey", 0.0)),
        "pct_moved_to_another_dish": float(counts.get("moved_to_another_dish", 0.0)),
        "pct_stopped_category": float(counts.get("stopped_category", 0.0)),
        "spend_change_hkd": spend_change, "spend_change_pct": spend_change_pct,
        "co2e_change_kg": co2e_change, "co2e_change_pct": co2e_change_pct,
        "margin_change_hkd": margin_change, "margin_change_pct": margin_change_pct,
    }
