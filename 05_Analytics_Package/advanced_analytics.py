"""
=====================================================================
 advanced_analytics.py  -  LEVEL 3 (BONUS) business questions
=====================================================================
   Q11  Correlation : do more book loans go together with more journal downloads?
   Q12  Forecast    : how much will each service be used in 2026?
   Q13  Anomalies   : which months show an unusual drop or spike?

 The script reads the clean warehouse tables exported by the ETL
 (06_Dashboards/PowerBI_Data), so it works even without MySQL.
 SQL versions of the same three analyses are in business_queries.sql.

 HOW TO RUN
     pip install pandas numpy matplotlib openpyxl
     python advanced_analytics.py
 OUTPUT
     charts/*.png                      the three charts
     advanced_analytics_results.xlsx   the numbers behind the charts
=====================================================================
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                     # draw charts to files (no window needed)
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(os.path.dirname(HERE), "06_Dashboards", "PowerBI_Data")
CHARTS = os.path.join(HERE, "charts")
os.makedirs(CHARTS, exist_ok=True)

# Same colours as the dashboards: one fixed colour per service
COLORS = {"Book Loans": "#2a78d6", "Digital Downloads": "#eb6834", "Room Bookings": "#1baf7a"}
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#c3c2b7",
                     "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e",
                     "axes.spines.top": False, "axes.spines.right": False})


def load(name):
    return pd.read_csv(os.path.join(CSV, f"{name}.csv"))


# ---------------------------------------------------------------------
# 1. Build ONE monthly table: month x service
# ---------------------------------------------------------------------
dates = load("dim_date")[["date_key", "month_label"]]
loans = load("fact_book_loan").merge(dates, left_on="checkout_date_key", right_on="date_key")
digital = load("fact_digital_usage").merge(dates, on="date_key")
rooms = load("fact_room_booking").merge(dates, on="date_key")
resources = load("dim_resource")

monthly = pd.DataFrame({
    "Book Loans": loans.groupby("month_label")["loan_count"].sum(),
    "Digital Downloads": digital.groupby("month_label")["download_count"].sum(),
    "Room Bookings": rooms.groupby("month_label")["booking_count"].sum(),
}).fillna(0)
monthly.index.name = "month"


# ---------------------------------------------------------------------
# 2. Q11 CORRELATION (department x month)
#    The digital system has no StudentID, so we cannot compare student
#    by student. We compare each department in each month instead.
# ---------------------------------------------------------------------
journals = digital.merge(resources, on="resource_key")
journals = journals[journals["resource_type"] == "Journal"]
pairs = pd.DataFrame({
    "book_loans": loans.groupby(["department_key", "month_label"])["loan_count"].sum(),
    "journal_downloads": journals.groupby(["department_key", "month_label"])["download_count"].sum(),
}).fillna(0).reset_index()
pairs = pairs[pairs["department_key"] != 1]                 # leave out 'Unknown' department
r = pairs["book_loans"].corr(pairs["journal_downloads"])    # Pearson correlation

# Part of that link is only the calendar (both rise before exams). Remove the
# month effect by comparing each value with that month's average:
for col in ("book_loans", "journal_downloads"):
    pairs[col + "_vs_month_avg"] = pairs[col] - pairs.groupby("month_label")[col].transform("mean")
r_without_season = pairs["book_loans_vs_month_avg"].corr(pairs["journal_downloads_vs_month_avg"])

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.scatter(pairs["book_loans"], pairs["journal_downloads"], s=28, color=COLORS["Book Loans"],
           alpha=0.55, edgecolor="white", linewidth=0.8)
slope, intercept = np.polyfit(pairs["book_loans"], pairs["journal_downloads"], 1)
xs = np.linspace(0, pairs["book_loans"].max(), 50)
ax.plot(xs, intercept + slope * xs, color=INK, linewidth=1.5)
ax.set_xlabel("Book loans (one department, one month)")
ax.set_ylabel("Journal downloads (same department & month)")
ax.set_title(f"Q11  More loans go with more journal downloads  (r = {r:.2f})", loc="left", color=INK)
ax.grid(color=GRID, linewidth=0.6)
fig.tight_layout()
fig.savefig(os.path.join(CHARTS, "q11_correlation.png"), dpi=160)
plt.close(fig)


# ---------------------------------------------------------------------
# 3. Q12 FORECAST for 2026 = TREND x SEASON
#    trend  : straight line through the 36 monthly values (least squares)
#    season : how busy each calendar month is compared with the trend
#             (e.g. April = 1.3 means 30% busier than normal)
# ---------------------------------------------------------------------
forecast_rows = []
history = monthly.copy()
history["t"] = range(1, len(history) + 1)                    # month number 1..36
history["cal_month"] = [int(m[5:7]) for m in history.index]
future_months = [f"2026-{m:02d}" for m in range(1, 13)]

fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
for ax, service in zip(axes, COLORS):
    y = history[service].values
    b, a = np.polyfit(history["t"], y, 1)                   # slope b, intercept a
    trend = a + b * history["t"]
    season = (y / trend).groupby(history["cal_month"]).mean()   # one factor per calendar month
    for i, month in enumerate(future_months, start=1):
        t = len(history) + i
        value = (a + b * t) * season[i]
        forecast_rows.append({"month": month, "service": service, "trend_per_month": round(b, 2),
                              "season_factor": round(season[i], 2), "forecast": round(value)})
    fc = [row["forecast"] for row in forecast_rows if row["service"] == service]

    x_hist = range(len(history))
    x_fut = range(len(history) - 1, len(history) + 12)
    ax.plot(x_hist, y, color=COLORS[service], linewidth=2)
    ax.plot(x_fut, [y[-1]] + fc, color=COLORS[service], linewidth=2, linestyle=(0, (4, 3)))
    ax.axvspan(len(history) - 0.5, len(history) + 11.5, color="#f0efec", zorder=0)
    ax.set_title(f"{service}: trend {b:+.1f} per month", loc="left", color=INK, fontsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_ylim(bottom=0)
labels = list(history.index) + future_months
axes[-1].set_xticks(range(0, len(labels), 6))
axes[-1].set_xticklabels(labels[::6])
axes[0].text(len(history) + 0.5, axes[0].get_ylim()[1] * 0.9, "forecast 2026", color=MUTED, fontsize=9)
fig.suptitle("Q12  Forecast for 2026 (dashed) = trend x seasonal pattern", x=0.01, ha="left", color=INK)
fig.tight_layout()
fig.savefig(os.path.join(CHARTS, "q12_forecast.png"), dpi=160)
plt.close(fig)
forecast = pd.DataFrame(forecast_rows)


# ---------------------------------------------------------------------
# 4. Q13 ANOMALY DETECTION
#    For every month we calculate the EXPECTED value = trend x season.
#    Here the season factor uses the MEDIAN (not the average), so one
#    broken month cannot hide itself by pulling its own baseline down.
#    A month more than 50% below or above the expected value = anomaly.
# ---------------------------------------------------------------------
anomalies = []
for service in COLORS:
    y = history[service].values
    b, a = np.polyfit(history["t"], y, 1)
    trend = a + b * history["t"].values
    season = pd.Series(y / trend).groupby(history["cal_month"].values).median()
    expected = trend * season.reindex(history["cal_month"]).values
    for month, actual, exp in zip(history.index, y, expected):
        deviation = (actual / exp - 1) * 100
        anomalies.append({"month": month, "service": service, "actual": int(actual),
                          "expected": round(exp), "deviation_pct": round(deviation, 1),
                          "status": "ANOMALY - drop" if deviation < -50
                          else "ANOMALY - spike" if deviation > 50 else "normal"})
anomalies = pd.DataFrame(anomalies)

fig, ax = plt.subplots(figsize=(10, 4))
s = "Digital Downloads"
ax.plot(range(len(history)), history[s], color=COLORS[s], linewidth=2, marker="o", markersize=4)
flagged = anomalies[(anomalies.service == s) & (anomalies.status != "normal")]
exp_line = anomalies[anomalies.service == s]["expected"].values
ax.plot(range(len(history)), exp_line, color=MUTED, linewidth=1.2, linestyle=(0, (2, 2)))
ax.text(len(history) - 1, exp_line[-1] * 1.05, "expected", color=MUTED, fontsize=9, ha="right")
for month in flagged["month"]:
    i = list(history.index).index(month)
    ax.scatter([i], [history[s].iloc[i]], s=140, facecolor="none", edgecolor="#d03b3b", linewidth=2, zorder=5)
    dev = flagged[flagged.month == month].deviation_pct.iloc[0]
    ax.annotate(f"! {month}: {int(history[s].iloc[i])} downloads\n({dev:+.0f}% vs expected)",
                (i, history[s].iloc[i]), xytext=(15, -30), textcoords="offset points", color=INK, fontsize=9)
ax.set_xticks(range(0, len(history), 3))
ax.set_xticklabels(history.index[::3], rotation=45, ha="right")
ax.set_title("Q13  Digital downloads per month - anomaly detected (red circle)", loc="left", color=INK)
ax.grid(axis="y", color=GRID, linewidth=0.6)
ax.set_ylim(bottom=0)
fig.tight_layout()
fig.savefig(os.path.join(CHARTS, "q13_anomaly.png"), dpi=160)
plt.close(fig)


# ---------------------------------------------------------------------
# 5. Save numbers + print a short summary
# ---------------------------------------------------------------------
with pd.ExcelWriter(os.path.join(HERE, "advanced_analytics_results.xlsx")) as xw:
    pd.DataFrame([{"pairs": len(pairs), "pearson_r": round(r, 3),
                   "pearson_r_without_season": round(r_without_season, 3)}]).to_excel(
        xw, sheet_name="Q11_correlation", index=False)
    pairs.to_excel(xw, sheet_name="Q11_pairs", index=False)
    forecast.pivot(index="month", columns="service", values="forecast").to_excel(xw, sheet_name="Q12_forecast_2026")
    anomalies.to_excel(xw, sheet_name="Q13_anomalies", index=False)
    monthly.to_excel(xw, sheet_name="monthly_history")

print(f"Q11 correlation loans vs journal downloads: r = {r:.2f} "
      f"(after removing the calendar effect: r = {r_without_season:.2f})")
print("Q12 forecast 2026 totals:",
      forecast.groupby("service")["forecast"].sum().to_dict(), "| 2025 actual:",
      monthly.loc[[m for m in monthly.index if m.startswith("2025")]].sum().round().astype(int).to_dict())
print("Q13 anomalies found:")
print(anomalies[anomalies.status != "normal"].to_string(index=False))
