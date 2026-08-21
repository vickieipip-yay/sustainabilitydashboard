"""
Synthetic data generator for the Club Sustainability Intelligence prototype.

Generates 180 days of linked data (spanning March-August, so summer
seasonality is visible) for a single F&B outlet ("Hilltop Paddock"),
modeled loosely on a private members' club. All data is fabricated — no
real club data is used or referenced.

Centerpiece scenario: at day 90, BEEF_BURGER is discontinued and replaced
by TURKEY_BURGER. Member-level ordering behavior (via internal, per-member
generation-time traits — never exposed as a table column) is simulated so
the substitution's effects on carbon, waste, revenue, and member adoption
are all visible and reconstructable purely by joining the tables below.
No separate "answer key" table is used anywhere.
"""

import numpy as np
import pandas as pd

import targets

RNG = np.random.default_rng(42)

OUTLET_ID = "HILLTOP-01"
OUTLET_NAME = "Hilltop Paddock"
N_DAYS = 180
SWITCH_DAY = 90  # day index (0-based) BEEF_BURGER -> TURKEY_BURGER takes effect
START_DATE = pd.Timestamp("2026-03-01")  # window runs to ~2026-08-27, covers Jun-Aug

SERVICE_PERIODS = ["breakfast", "lunch", "dinner"]
MEMBERSHIP_TYPES = ["full", "racing"]
GENDERS = ["Female", "Male"]
AGE_GROUPS = ["18-34", "35-44", "45-54", "55-64", "65+"]
WASTE_STAGES = ["prep", "service", "plate-return"]
SUPPLIERS = [f"SUP-{i:02d}" for i in range(1, 9)]

BURGER_DISH_IDS = {"BEEF_BURGER", "TURKEY_BURGER", "CHICKEN_BURGER"}

# --- Recipe master -----------------------------------------------------
# unit_cost = HK$/kg ingredient cost. selling_price is the menu price a
# transaction's price is sampled around. `periods` = service periods the
# dish is offered in. active_from/active_to (day index, half-open) handle
# the burger swap; all other dishes are on the menu the whole window.
DISHES = [
    dict(dish_id="EGG_BENEDICT", dish_name="Eggs Benedict", sku="SKU-EGG-01",
         portion_weight_g=220, unit_cost=45, selling_price=128, ef=5.5,
         lower_impact=False, base_weight=0.060, plate_mult=0.5, periods=["breakfast"]),
    dict(dish_id="CONGEE_CENTURY_EGG", dish_name="Congee with Century Egg", sku="SKU-RICE-01",
         portion_weight_g=300, unit_cost=15, selling_price=78, ef=1.0,
         lower_impact=True, base_weight=0.070, plate_mult=0.4, periods=["breakfast"]),
    dict(dish_id="GRANOLA_YOGURT_BOWL", dish_name="Granola & Yogurt Bowl", sku="SKU-GRANOLA-01",
         portion_weight_g=180, unit_cost=20, selling_price=88, ef=0.8,
         lower_impact=True, base_weight=0.050, plate_mult=0.3, periods=["breakfast"]),
    dict(dish_id="AVOCADO_TOAST", dish_name="Avocado Toast", sku="SKU-AVO-01",
         portion_weight_g=200, unit_cost=25, selling_price=98, ef=1.2,
         lower_impact=True, base_weight=0.060, plate_mult=0.4, periods=["breakfast"]),
    dict(dish_id="DIM_SUM_SELECTION", dish_name="Dim Sum Selection", sku="SKU-MIXED-01",
         portion_weight_g=260, unit_cost=55, selling_price=168, ef=5.0,
         lower_impact=False, base_weight=0.070, plate_mult=0.6, periods=["lunch", "dinner"]),
    dict(dish_id="WONTON_NOODLE_SOUP", dish_name="Wonton Noodle Soup", sku="SKU-NOODLE-01",
         portion_weight_g=320, unit_cost=28, selling_price=118, ef=2.8,
         lower_impact=False, base_weight=0.060, plate_mult=0.5, periods=["lunch"]),
    dict(dish_id="CLUB_SANDWICH", dish_name="Classic Club Sandwich", sku="SKU-CHKN-02",
         portion_weight_g=250, unit_cost=42, selling_price=148, ef=4.0,
         lower_impact=True, base_weight=0.070, plate_mult=0.6, periods=["lunch"]),
    dict(dish_id="GARDEN_SALAD", dish_name="Jockey Club Garden Salad", sku="SKU-VEG-02",
         portion_weight_g=200, unit_cost=18, selling_price=108, ef=0.6,
         lower_impact=True, base_weight=0.040, plate_mult=0.4, periods=["lunch", "dinner"]),
    dict(dish_id="VEG_CURRY", dish_name="Seasonal Vegetable Curry", sku="SKU-VEG-03",
         portion_weight_g=280, unit_cost=20, selling_price=158, ef=1.3,
         lower_impact=True, base_weight=0.030, plate_mult=0.5, periods=["lunch", "dinner"]),
    dict(dish_id="GRILLED_CHICKEN_BREAST", dish_name="Grilled Chicken Breast", sku="SKU-CHKN-01",
         portion_weight_g=220, unit_cost=52, selling_price=268, ef=4.6,
         lower_impact=True, base_weight=0.060, plate_mult=0.8, periods=["lunch", "dinner"]),
    dict(dish_id="PAN_SEARED_SALMON", dish_name="Pan-Seared Salmon", sku="SKU-SALMON-01",
         portion_weight_g=210, unit_cost=148, selling_price=368, ef=6.9,
         lower_impact=False, base_weight=0.050, plate_mult=0.9, periods=["lunch", "dinner"]),
    dict(dish_id="RIBEYE_STEAK", dish_name="Grilled Ribeye Steak", sku="SKU-BEEF-02",
         portion_weight_g=280, unit_cost=340, selling_price=780, ef=39.5,
         lower_impact=False, base_weight=0.040, plate_mult=1.4, periods=["dinner"]),
    dict(dish_id="LAMB_RACK", dish_name="Lamb Rack Provencale", sku="SKU-LAMB-01",
         portion_weight_g=250, unit_cost=300, selling_price=620, ef=24.5,
         lower_impact=False, base_weight=0.030, plate_mult=1.3, periods=["dinner"]),
    dict(dish_id="BEEF_BURGER", dish_name="Signature Beef Burger", sku="SKU-BEEF-03",
         portion_weight_g=260, unit_cost=138, selling_price=168, ef=27.0,
         lower_impact=False, base_weight=0.110, plate_mult=1.5, periods=["lunch", "dinner"],
         active_from=0, active_to=SWITCH_DAY),
    dict(dish_id="TURKEY_BURGER", dish_name="Turkey Burger", sku="SKU-TURKEY-01",
         portion_weight_g=260, unit_cost=110, selling_price=162, ef=11.0,
         lower_impact=True, base_weight=0.110, plate_mult=0.7, periods=["lunch", "dinner"],
         active_from=SWITCH_DAY, active_to=N_DAYS),
    dict(dish_id="CHICKEN_BURGER", dish_name="Chicken Burger", sku="SKU-CHKN-03",
         portion_weight_g=250, unit_cost=90, selling_price=158, ef=6.5,
         lower_impact=True, base_weight=0.050, plate_mult=0.6, periods=["lunch", "dinner"]),
    dict(dish_id="MUSHROOM_RISOTTO", dish_name="Wild Mushroom Risotto", sku="SKU-RICE-02",
         portion_weight_g=320, unit_cost=32, selling_price=220, ef=1.6,
         lower_impact=True, base_weight=0.030, plate_mult=0.5, periods=["dinner"]),
    dict(dish_id="CHOC_LAVA_CAKE", dish_name="Chocolate Lava Cake", sku="SKU-DESSERT-01",
         portion_weight_g=140, unit_cost=48, selling_price=98, ef=3.6,
         lower_impact=False, base_weight=0.040, plate_mult=0.5, periods=["lunch", "dinner"]),
]
for _d in DISHES:
    _d.setdefault("active_from", 0)
    _d.setdefault("active_to", N_DAYS)
    _d["food_cost_per_portion"] = round(_d["unit_cost"] * _d["portion_weight_g"] / 1000.0, 2)
    _d["gross_margin_per_portion"] = round(_d["selling_price"] - _d["food_cost_per_portion"], 2)

DISH_IDS = [d["dish_id"] for d in DISHES]
DISH_BY_ID = {d["dish_id"]: d for d in DISHES}


def _make_recipe_master() -> pd.DataFrame:
    rows = []
    for d in DISHES:
        rows.append(
            {
                "dish_id": d["dish_id"],
                "sku": d["sku"],  # join key: dish_id -> sku
                "dish_name": d["dish_name"],
                "yield_qty": 1,
                "portion_weight_g": d["portion_weight_g"],
                "unit_cost": d["unit_cost"],
                "selling_price": d["selling_price"],
                "food_cost_per_portion": d["food_cost_per_portion"],
                "gross_margin_per_portion": d["gross_margin_per_portion"],
                "emission_factor_kg_co2e_per_kg": d["ef"],  # join key: sku -> emission factor
                "lower_impact_flag": d["lower_impact"],
            }
        )
    return pd.DataFrame(rows)


def _make_purchase_orders() -> pd.DataFrame:
    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    rows = []
    po_id = 1
    for day_idx, date in enumerate(dates):
        active_dishes = [d for d in DISHES if d["active_from"] <= day_idx < d["active_to"]]
        n_deliveries = RNG.integers(4, 8)
        chosen = RNG.choice(active_dishes, size=min(n_deliveries, len(active_dishes)), replace=False)
        for d in chosen:
            rows.append(
                {
                    "supplier_id": RNG.choice(SUPPLIERS),
                    "sku": d["sku"],
                    "quantity": round(RNG.uniform(8, 70), 1),
                    "unit_cost": round(d["unit_cost"] * RNG.uniform(0.9, 1.1), 2),
                    "delivery_date": date,
                }
            )
            po_id += 1
    return pd.DataFrame(rows)


def _make_member_profile(n_members: int = 3000) -> pd.DataFrame:
    membership_type = RNG.choice(MEMBERSHIP_TYPES, size=n_members, p=[0.62, 0.38])
    gender = RNG.choice(GENDERS, size=n_members, p=[0.48, 0.52])
    age_group = RNG.choice(AGE_GROUPS, size=n_members, p=[0.22, 0.24, 0.22, 0.18, 0.14])
    join_start = START_DATE - pd.Timedelta(days=365 * 15)
    join_dates = join_start + pd.to_timedelta(RNG.integers(0, 365 * 15, size=n_members), unit="D")

    avg_visits = np.round(RNG.gamma(shape=2.0, scale=3.0, size=n_members) + 0.5, 1)
    avg_visits = np.clip(avg_visits, 0.3, 22)

    spend_base = {"full": 3800, "racing": 3300}
    avg_spend = np.array([spend_base[t] for t in membership_type]) * RNG.uniform(0.7, 1.3, size=n_members)
    avg_spend = np.round(avg_spend, 0)

    member_ids = [f"M-{i+1:05d}" for i in range(n_members)]
    return pd.DataFrame(
        {
            "member_id": member_ids,
            "membership_type": membership_type,
            "gender": gender,
            "age_group": age_group,
            "join_date": join_dates,
            "avg_visits_per_month": avg_visits,
            "avg_monthly_spend": avg_spend,
        }
    )


def _member_traits(member_profile: pd.DataFrame) -> pd.DataFrame:
    """
    Internal generation-time traits (not part of the published schema).
    Never exposed in any table — the resulting transactions are what's
    reconstructable via joins, not these traits themselves.
    """
    df = member_profile.copy()

    type_affinity = {"full": 0.50, "racing": 0.58}
    visit_norm = (df["avg_visits_per_month"] - df["avg_visits_per_month"].min()) / (
        df["avg_visits_per_month"].max() - df["avg_visits_per_month"].min()
    )
    base_affinity = df["membership_type"].map(type_affinity).astype(float)
    affinity = np.clip(0.45 * base_affinity + 0.4 * visit_norm + RNG.normal(0, 0.08, len(df)), 0, 1)

    age_novelty = {"18-34": 0.70, "35-44": 0.55, "45-54": 0.40, "55-64": 0.30, "65+": 0.20}
    base_novelty = df["age_group"].map(age_novelty).astype(float)
    days_since_join = (START_DATE - df["join_date"]).dt.days
    recency_score = np.clip(1 - days_since_join / (365 * 3), 0, 1)
    novelty = np.clip(
        0.6 * base_novelty + 0.25 * recency_score + 0.15 * (1 - visit_norm) + RNG.normal(0, 0.06, len(df)),
        0, 1,
    )

    df["_red_meat_affinity"] = affinity
    df["_novelty_seeking"] = novelty
    df["_is_frequent"] = df["avg_visits_per_month"] > 8
    return df


def _seasonal_temperature(dates: pd.DatetimeIndex) -> np.ndarray:
    """Rough HK-like seasonal curve: cool in Mar, hot Jun-Aug, with daily noise."""
    day_of_year = dates.dayofyear.to_numpy()
    base = 23.5 + 7.5 * np.sin(2 * np.pi * (day_of_year - 100) / 365)
    noise = RNG.normal(0, 1.6, len(dates))
    return np.round(base + noise, 1)


def _covers_plan() -> dict:
    """Deterministic covers-per-day-per-period, shared by pos_transactions and utility_log so daily_covers stays consistent."""
    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    plan = {}
    for day_idx, date in enumerate(dates):
        weekend_mult = 1.2 if date.dayofweek in (4, 5) else 1.0
        plan[day_idx] = {
            period: int(RNG.integers(30, 95) * weekend_mult) for period in SERVICE_PERIODS
        }
    return plan


def _redraw_excluding(weights: np.ndarray, dish_ids: list, exclude_dish_id: str) -> str:
    w = weights.copy()
    idx = dish_ids.index(exclude_dish_id)
    w[idx] = 0.0
    if w.sum() <= 0:
        return exclude_dish_id
    w = w / w.sum()
    return str(RNG.choice(dish_ids, p=w))


def _make_pos_transactions(member_profile: pd.DataFrame, covers_plan: dict) -> pd.DataFrame:
    traits = _member_traits(member_profile).set_index("member_id")
    member_ids = traits.index.to_numpy()
    member_weights = traits["avg_visits_per_month"].to_numpy()
    member_weights = member_weights / member_weights.sum()

    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    rows = []
    check_number = 1

    for day_idx, date in enumerate(dates):
        active_mask_all = np.array([d["active_from"] <= day_idx < d["active_to"] for d in DISHES])
        turkey_recovery = np.clip((day_idx - SWITCH_DAY) / (N_DAYS - SWITCH_DAY), 0, 1) if day_idx >= SWITCH_DAY else 0.0

        for period in SERVICE_PERIODS:
            period_mask = np.array([period in d["periods"] for d in DISHES])
            eligible = active_mask_all & period_mask
            dish_ids_period = [DISH_IDS[i] for i in range(len(DISH_IDS)) if eligible[i]]
            weights_period = np.array([DISHES[i]["base_weight"] for i in range(len(DISHES)) if eligible[i]])
            weights_period = weights_period / weights_period.sum()

            covers_today = covers_plan[day_idx][period]
            is_guest = RNG.random(covers_today) < 0.12
            n_member_covers = int((~is_guest).sum())
            drawn_members = RNG.choice(member_ids, size=n_member_covers, p=member_weights, replace=True)
            drawn_dishes = RNG.choice(dish_ids_period, size=covers_today, p=weights_period, replace=True)

            hour = {"breakfast": 8, "lunch": 13, "dinner": 19}[period]
            member_ptr = 0
            for i in range(covers_today):
                dish_id = drawn_dishes[i]
                member_id = None
                if not is_guest[i]:
                    member_id = drawn_members[member_ptr]
                    member_ptr += 1

                    # --- Burger-substitution behavior overrides ----------
                    # Join keys this mirrors: member_id -> membership_type /
                    # avg_visits_per_month (member_profile), dish_id (this
                    # row). Nothing is stored outside this transaction row,
                    # so the outcome is fully reconstructable later purely
                    # via joins on pos_transactions + member_profile.
                    affinity = traits.at[member_id, "_red_meat_affinity"]
                    novelty = traits.at[member_id, "_novelty_seeking"]

                    if dish_id == "BEEF_BURGER":
                        accept_prob = 0.35 + 0.6 * affinity
                        if RNG.random() > accept_prob:
                            dish_id = _redraw_excluding(weights_period, dish_ids_period, "BEEF_BURGER")
                    elif dish_id == "TURKEY_BURGER":
                        accept_prob = turkey_recovery * (0.25 + 0.65 * novelty)
                        if RNG.random() > accept_prob:
                            if "CHICKEN_BURGER" in dish_ids_period and RNG.random() < 0.55 * affinity:
                                dish_id = "CHICKEN_BURGER"  # stays in burger category, just not turkey
                            else:
                                dish_id = _redraw_excluding(weights_period, dish_ids_period, "TURKEY_BURGER")

                dish = DISH_BY_ID[dish_id]
                price = round(dish["selling_price"] * RNG.uniform(0.95, 1.05), 0)
                ts = date + pd.Timedelta(hours=int(hour), minutes=int(RNG.integers(0, 59)))
                broken = RNG.random() < 0.025
                rows.append(
                    {
                        "check_number": f"CHK-{check_number:06d}",
                        "outlet_id": OUTLET_ID if not broken else "UNKNOWN-OUTLET",
                        "dish_id": dish_id if not (broken and RNG.random() < 0.5) else "D99-MISSING",
                        "price": price,
                        "timestamp": ts,
                        "service_period": period,
                        "covers": 1,
                        "member_id": member_id,
                    }
                )
                check_number += 1
    return pd.DataFrame(rows)


def _make_waste_log(covers_plan: dict) -> pd.DataFrame:
    """
    Food waste is generated per dish per production stage per day, scaled
    to that day's covers for the dish (join key: dish_id -> sku). A
    per-week random shock (not a smooth trend) is applied so weeks vary
    irregularly rather than drifting monotonically.
    """
    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    n_weeks = N_DAYS // 7 + 2
    week_shock = np.clip(RNG.normal(1.0, 0.16, n_weeks), 0.6, 1.6)

    rows = []
    for day_idx, date in enumerate(dates):
        week_idx = day_idx // 7
        shock = week_shock[week_idx]
        active = [d for d in DISHES if d["active_from"] <= day_idx < d["active_to"]]
        total_covers_today = sum(covers_plan[day_idx].values())
        weights = np.array([d["base_weight"] for d in active])
        weights = weights / weights.sum()
        covers_by_dish = RNG.multinomial(total_covers_today, weights)

        for d, covers in zip(active, covers_by_dish):
            if covers == 0:
                continue
            portion_kg = d["portion_weight_g"] / 1000.0
            throughput_kg = covers * portion_kg
            for stage in WASTE_STAGES:
                base_rate = {"prep": 0.07, "service": 0.03, "plate-return": 0.05}[stage]
                mult = d["plate_mult"] if stage == "plate-return" else 1.0
                mean_kg = throughput_kg * base_rate * mult * shock
                weight_kg = max(0.0, RNG.normal(mean_kg, mean_kg * 0.35 + 0.01))
                rows.append(
                    {
                        "outlet_id": OUTLET_ID,
                        "date": date,
                        "dish_id": d["dish_id"],
                        "sku": d["sku"],
                        "waste_type": "food",
                        "production_stage": stage,
                        "weight_kg": round(weight_kg, 3),
                        "unit_cost": d["unit_cost"],
                    }
                )

        for wtype, base, cost in [("plastic", 3.5, 4.0), ("paper", 2.2, 1.5), ("other", 1.2, 0.5)]:
            for stage in WASTE_STAGES:
                stage_mult = {"prep": 1.1, "service": 1.0, "plate-return": 0.6}[stage]
                weight_kg = max(0.0, RNG.normal(base * stage_mult * shock, base * 0.3))
                rows.append(
                    {
                        "outlet_id": OUTLET_ID,
                        "date": date,
                        "dish_id": None,
                        "sku": None,
                        "waste_type": wtype,
                        "production_stage": stage,
                        "weight_kg": round(weight_kg, 3),
                        "unit_cost": cost,
                    }
                )

    df = pd.DataFrame(rows)
    df["monetary_value"] = (df["weight_kg"] * df["unit_cost"]).round(2)
    return df


def _make_utility_log(covers_plan: dict) -> pd.DataFrame:
    """
    Actual utility use = target (from targets.py's seasonal, cover- and
    temperature-adjusted target engine) x a per-week noise factor, so some
    weeks are identifiably high-variance rather than a smooth trend. Join
    key: date -> daily_covers matches the same covers_plan used for
    pos_transactions, so utility_log stays consistent with actual covers.
    """
    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    temps = _seasonal_temperature(dates)

    n_weeks = N_DAYS // 7 + 2
    week_noise_sd = np.where(RNG.random(n_weeks) < 0.15, 0.20, 0.06)  # ~15% of weeks are high-variance

    rows = []
    for day_idx, date in enumerate(dates):
        covers = sum(covers_plan[day_idx].values())
        temp = temps[day_idx]
        week_idx = day_idx // 7
        sd = week_noise_sd[week_idx]

        elec_target = targets.electricity_target_kwh(covers, date, temp)
        water_target = targets.water_target_litres(covers, date, temp)

        electricity = max(0.0, elec_target * (1 + RNG.normal(0, sd)))
        water = max(0.0, water_target * (1 + RNG.normal(0, sd)))

        rows.append(
            {
                "outlet_id": OUTLET_ID,
                "date": date,
                "electricity_kwh": round(electricity, 1),
                "water_litres": round(water, 0),
                "electricity_target_kwh": round(elec_target, 1),
                "water_target_litres": round(water_target, 0),
                "daily_covers": covers,
                "average_daily_temperature_c": temp,
            }
        )
    return pd.DataFrame(rows)


def generate_all() -> dict:
    """Generate all six linked synthetic tables and return them in a dict."""
    recipe_master = _make_recipe_master()
    purchase_orders = _make_purchase_orders()
    member_profile = _make_member_profile()
    covers_plan = _covers_plan()
    pos_transactions = _make_pos_transactions(member_profile, covers_plan)
    waste_log = _make_waste_log(covers_plan)
    utility_log = _make_utility_log(covers_plan)

    return {
        "purchase_orders": purchase_orders,
        "pos_transactions": pos_transactions,
        "recipe_master": recipe_master,
        "waste_log": waste_log,
        "utility_log": utility_log,
        "member_profile": member_profile,
        "outlet_id": OUTLET_ID,
        "outlet_name": OUTLET_NAME,
        "switch_day": SWITCH_DAY,
        "start_date": START_DATE,
        "n_days": N_DAYS,
        "burger_dish_ids": BURGER_DISH_IDS,
    }


if __name__ == "__main__":
    data = generate_all()
    for name, df in data.items():
        if isinstance(df, pd.DataFrame):
            print(f"{name}: {len(df)} rows")
