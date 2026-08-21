"""
Join logic for the Club Sustainability Intelligence prototype.

Every join is annotated with which key(s) it depends on, from the shared
set: outlet_id, member_id, dish_id, dish_id -> sku, date,
timestamp -> service_period, date -> week_start/month. Downstream tabs
should only need functions from this module and metrics.py.
"""

import pandas as pd


def pos_with_recipe(pos_transactions: pd.DataFrame, recipe_master: pd.DataFrame) -> pd.DataFrame:
    """
    Join POS transactions to recipe_master.

    Join key used: dish_id -> sku (brings in cost/price/emission-factor
    fields). Rows whose dish_id has no match become unmatched — intentional,
    so Tab 5 can surface join failures instead of silently dropping them.
    """
    merged = pos_transactions.merge(
        recipe_master, on="dish_id", how="left", indicator="_recipe_match"
    )
    merged["dish_matched"] = merged["_recipe_match"] == "both"
    return merged.drop(columns="_recipe_match")


def pos_with_member(pos_transactions: pd.DataFrame, member_profile: pd.DataFrame) -> pd.DataFrame:
    """
    Join POS transactions to member_profile.

    Join key used: member_id. A null member_id (guest cover) is valid and
    NOT a join failure. A non-null member_id with no match IS a join
    failure (Tab 5). Guests naturally fall out of demographic analysis
    downstream since their demographic columns are NaN after this merge.
    """
    merged = pos_transactions.merge(
        member_profile, on="member_id", how="left", indicator="_member_match"
    )
    merged["member_matched"] = (merged["member_id"].isna()) | (merged["_member_match"] == "both")
    return merged.drop(columns="_member_match")


def pos_outlet_matched(pos_transactions: pd.DataFrame, outlet_id: str) -> pd.Series:
    """Flag rows whose outlet_id matches this outlet. Join key: outlet_id."""
    return pos_transactions["outlet_id"] == outlet_id


def full_join(
    pos_transactions: pd.DataFrame,
    recipe_master: pd.DataFrame,
    member_profile: pd.DataFrame,
    outlet_id: str,
) -> pd.DataFrame:
    """
    Build the single unified table the whole dashboard reads from.

    Chains outlet_id, member_id, dish_id->sku, and derives
    date/week_start/month from timestamp for weekly/monthly aggregation
    and service_period grouping (service_period is already on pos_transactions).
    """
    df = pos_with_recipe(pos_transactions, recipe_master)
    df = pos_with_member(df, member_profile)
    df["outlet_matched"] = pos_outlet_matched(df, outlet_id)
    df["fully_matched"] = df["outlet_matched"] & df["dish_matched"] & df["member_matched"]

    df["co2e_kg"] = (df["portion_weight_g"] / 1000.0) * df["emission_factor_kg_co2e_per_kg"]
    # actual per-transaction margin, using price actually paid rather than
    # the recipe_master list price, so promos/discounts flow through
    df["margin"] = df["price"] - df["food_cost_per_portion"]

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["week_start"] = (df["timestamp"] - pd.to_timedelta(df["timestamp"].dt.dayofweek, unit="D")).dt.date
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["is_frequent"] = df["avg_visits_per_month"] > 8

    return df


def waste_for_outlet(waste_log: pd.DataFrame, outlet_id: str) -> pd.DataFrame:
    """Filter waste_log to the outlet. Join key used: outlet_id."""
    df = waste_log[waste_log["outlet_id"] == outlet_id].copy()
    dt = pd.to_datetime(df["date"])
    df["week_start"] = (dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.date
    df["month"] = dt.dt.to_period("M").astype(str)
    return df


def utility_for_outlet(utility_log: pd.DataFrame, outlet_id: str) -> pd.DataFrame:
    """Filter utility_log to the outlet. Join key used: outlet_id."""
    df = utility_log[utility_log["outlet_id"] == outlet_id].copy()
    dt = pd.to_datetime(df["date"])
    df["week_start"] = (dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.date
    df["month"] = dt.dt.to_period("M").astype(str)
    return df


def waste_with_recipe(waste_outlet: pd.DataFrame, recipe_master: pd.DataFrame) -> pd.DataFrame:
    """Join outlet waste to recipe_master for dish_name context. Join key: dish_id -> sku."""
    return waste_outlet.merge(
        recipe_master[["dish_id", "dish_name"]], on="dish_id", how="left"
    )


def apply_global_filters(
    full_joined: pd.DataFrame,
    date_range=None,
    service_periods=None,
    membership_types=None,
    genders=None,
    age_groups=None,
    frequency=None,
) -> pd.DataFrame:
    """
    Apply the dashboard's global filters to the unified transaction table.
    Every filter is a simple predicate on a column already produced by
    full_join — no additional joins are needed here.
    """
    df = full_joined
    if date_range:
        start, end = date_range
        df = df[(df["date"] >= start) & (df["date"] <= end)]
    if service_periods:
        df = df[df["service_period"].isin(service_periods)]
    if membership_types:
        df = df[df["membership_type"].isin(membership_types) | df["membership_type"].isna()]
    if genders:
        df = df[df["gender"].isin(genders) | df["gender"].isna()]
    if age_groups:
        df = df[df["age_group"].isin(age_groups) | df["age_group"].isna()]
    if frequency and frequency != "All":
        want_frequent = frequency == "Frequent (>8 visits/mo)"
        df = df[(df["is_frequent"] == want_frequent) | df["is_frequent"].isna()]
    return df


def apply_date_filter(df: pd.DataFrame, date_range=None) -> pd.DataFrame:
    """Date-only filter for waste_outlet/utility_outlet, which carry no demographic columns."""
    if not date_range:
        return df
    start, end = date_range
    dates = pd.to_datetime(df["date"]).dt.date
    return df[(dates >= start) & (dates <= end)]
