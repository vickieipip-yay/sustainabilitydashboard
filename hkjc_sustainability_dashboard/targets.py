"""
Target engine for the Club Sustainability Intelligence prototype.

All constants and functions here are synthetic, illustrative demo targets
— not derived from any real club target-setting process. They are
centralized here so app.py can expose them as adjustable sidebar controls
without touching data_gen.py or metrics.py.
"""

import pandas as pd

# --- Utility targets ---------------------------------------------------
# target = fixed overhead + (per-cover rate x covers x seasonal month
# multiplier x day-of-week multiplier) + temperature adjustment.
FIXED_ELECTRICITY_KWH = 180.0
FIXED_WATER_LITRES = 1200.0
ELECTRICITY_PER_COVER_KWH = 2.6
WATER_PER_COVER_LITRES = 42.0

SUMMER_MONTHS = {6, 7, 8}
SUMMER_MULT = 1.18
SHOULDER_MONTHS = {5, 9}
SHOULDER_MULT = 1.08
WEEKEND_DOW = {4, 5}  # Fri, Sat
WEEKEND_MULT = 1.06

TEMP_BASELINE_C = 24.0
TEMP_ELEC_COEF_PER_COVER = 0.09   # extra kWh per cover per degree above baseline
TEMP_WATER_COEF_PER_COVER = 1.1   # extra litres per cover per degree above baseline

# --- Waste / carbon targets ---------------------------------------------
# Calibrated ~10% above this outlet's typical generated actuals (waste
# ~0.035 kg/cover, carbon ~0.48/1.42/2.56 kg CO2e/cover for
# breakfast/lunch/dinner) so variance around target stays credible rather
# than showing a constant, unrealistic gap in either direction.
TARGET_WASTE_PER_COVER_KG = 0.038
TARGET_CO2E_PER_COVER_BY_PERIOD = {"breakfast": 0.52, "lunch": 1.55, "dinner": 2.75}


def month_multiplier(month: int) -> float:
    if month in SUMMER_MONTHS:
        return SUMMER_MULT
    if month in SHOULDER_MONTHS:
        return SHOULDER_MULT
    return 1.0


def dow_multiplier(dow: int) -> float:
    return WEEKEND_MULT if dow in WEEKEND_DOW else 1.0


def electricity_target_kwh(
    covers: float, date: pd.Timestamp, avg_temp_c: float,
    fixed: float = None, per_cover: float = None,
) -> float:
    """
    Target electricity for one outlet-day, adjusted for covers, season,
    day-of-week, and temperature. `fixed`/`per_cover` let the sidebar
    override the base rate without touching this formula.
    """
    fixed = FIXED_ELECTRICITY_KWH if fixed is None else fixed
    per_cover = ELECTRICITY_PER_COVER_KWH if per_cover is None else per_cover
    m_mult = month_multiplier(date.month)
    d_mult = dow_multiplier(date.dayofweek)
    temp_adj = max(0.0, avg_temp_c - TEMP_BASELINE_C) * TEMP_ELEC_COEF_PER_COVER * covers
    return fixed + covers * per_cover * m_mult * d_mult + temp_adj


def water_target_litres(
    covers: float, date: pd.Timestamp, avg_temp_c: float,
    fixed: float = None, per_cover: float = None,
) -> float:
    fixed = FIXED_WATER_LITRES if fixed is None else fixed
    per_cover = WATER_PER_COVER_LITRES if per_cover is None else per_cover
    m_mult = month_multiplier(date.month)
    d_mult = dow_multiplier(date.dayofweek)
    temp_adj = max(0.0, avg_temp_c - TEMP_BASELINE_C) * TEMP_WATER_COEF_PER_COVER * covers
    return fixed + covers * per_cover * m_mult * d_mult + temp_adj


def food_waste_target_kg(covers: float, target_per_cover: float = None) -> float:
    target_per_cover = TARGET_WASTE_PER_COVER_KG if target_per_cover is None else target_per_cover
    return covers * target_per_cover


def carbon_target_kg(service_period: str, covers: float, targets_by_period: dict = None) -> float:
    targets_by_period = TARGET_CO2E_PER_COVER_BY_PERIOD if targets_by_period is None else targets_by_period
    return covers * targets_by_period.get(service_period, 3.0)
