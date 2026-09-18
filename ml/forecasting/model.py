"""Monthly spending forecast.

Mandatory behaviour (per product spec)
    If fewer than MIN_MONTHS months of history exist, return an explicit
    insufficient-data result. NEXUS never invents a forecast.

Model (when enough data exists)
    - per-month total spending series (calendar months, up to 24)
    - linear trend via least squares on a 3-month moving average
    - seasonal adjustment = mean residual per calendar month
    - forecast: trend(month) + seasonal(month)
    - 95% interval: ±1.96 * residual standard deviation (floored at 0)

Limitations (stated honestly)
    - 6-24 months is a small sample; intervals are wide and should be read as
      decision support, not point predictions.
    - One-off large expenses (travel, repairs) distort the series; no
      outlier-robust variant is applied yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

MIN_MONTHS = 6


class InsufficientDataError(ValueError):
    pass


@dataclass
class Forecast:
    ok: bool
    message: str
    history: list[dict] = field(default_factory=list)     # {month, total}
    points: list[dict] = field(default_factory=list)      # {month, value, lo, hi}
    trend_pct_mom: float | None = None
    model: str = "trend+seasonal-naive-v1"


def _month_label(d: date) -> str:
    return d.strftime("%Y-%m")


def _add_months(label: str, n: int) -> str:
    y, m = int(label[:4]), int(label[5:7])
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def monthly_totals(transactions: list[dict], today: date, months: int = 24) -> list[dict]:
    totals: dict[str, float] = {}
    for i in range(months):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12
            y -= 1
        totals[_month_label(date(y, m, 1))] = 0.0
    for t in transactions:
        key = _month_label(t["date"])
        if key in totals:
            totals[key] += t.get("amount", 0)
    return [{"month": k, "total": round(v, 2)} for k, v in sorted(totals.items())]


def forecast_monthly_spending(transactions: list[dict], today: date,
                              horizon: int = 3) -> Forecast:
    hist = monthly_totals(transactions, today)
    values = [h["total"] for h in hist]
    months = [h["month"] for h in hist]
    if len([v for v in values if v > 0]) < MIN_MONTHS:
        return Forecast(
            ok=False,
            message=("Not enough historical data to produce a reliable forecast "
                     f"(need >= {MIN_MONTHS} months with activity)."),
            history=hist,
        )
    y = np.array(values, dtype=np.float64)
    x = np.arange(len(y), dtype=np.float64)
    # 3-month moving average to reduce one-off spikes, then fit a line
    ma = np.convolve(y, np.ones(3) / 3, mode="same")
    ma[0], ma[-1] = y[0], y[-1]
    trend = np.polyfit(x, ma, 1)
    pred_trend = np.polyval(trend, x)
    resid = y - pred_trend
    seasonal = {m: 0.0 for m in range(1, 13)}
    counts = {m: 0 for m in range(1, 13)}
    for mlabel, r in zip(months, resid, strict=True):
        mm = int(mlabel[5:7])
        seasonal[mm] += r
        counts[mm] += 1
    for m in seasonal:
        if counts[m]:
            seasonal[m] /= counts[m]
    sigma = float(np.std(resid, ddof=1)) if len(resid) > 2 else 0.0
    points: list[dict] = []
    for h in range(1, horizon + 1):
        xi = len(y) - 1 + h
        v = float(np.polyval(trend, xi) + seasonal[int(_add_months(months[-1], h)[5:7])])
        v = max(0.0, v)
        points.append({
            "month": _add_months(months[-1], h),
            "value": round(v, 2),
            "lo": round(max(0.0, v - 1.96 * sigma), 2),
            "hi": round(v + 1.96 * sigma, 2),
        })
    last, prev = y[-1], y[-2]
    trend_pct = round((last - prev) / prev * 100, 1) if prev > 0 else None
    return Forecast(
        ok=True,
        message=(f"Trend + seasonal-naive forecast over {len(values)} months of history. "
                 "Intervals are 95% and wide at this sample size — decision support only."),
        history=hist, points=points, trend_pct_mom=trend_pct,
    )
