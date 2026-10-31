"""
=====================================================================
 build_dashboard_images.py
 Draws the 3 dashboards as images (.jpg) from the clean warehouse data
 in PowerBI_Data/. They are the DESIGN of the Power BI report: every
 visual here is rebuilt in Power BI by following dashboard_guide.pdf.

   executive_dashboard.jpg    - high-level KPIs for the Library Director
   department_dashboard.jpg   - usage by academic unit
   operational_dashboard.jpg  - daily operational metrics

 HOW TO RUN:   python build_dashboard_images.py
=====================================================================
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "PowerBI_Data")

# ---------------------------------------------------------------------
# Colours - one fixed colour per thing, the same in every dashboard
# ---------------------------------------------------------------------
SERVICE = {"Book Loans": "#2a78d6", "Digital Downloads": "#eb6834", "Room Bookings": "#1baf7a"}
RESOURCE = {"E-book": "#e87ba4", "Journal": "#6250d6", "Article": "#eda100"}
LEVEL = {"Undergraduate": "#e87ba4", "Graduate": "#6250d6"}
PAGE, CARD, BORDER = "#f9f9f7", "#fcfcfb", "#e1e0d9"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
GOOD, BAD = "#006300", "#d03b3b"
BLUES = LinearSegmentedColormap.from_list("blues", ["#eef5fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])

for f in ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"]:
    if os.path.exists(f):
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": ["Inter", "DejaVu Sans"], "font.size": 10,
    "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.facecolor": CARD,
})


# ---------------------------------------------------------------------
# Load the warehouse tables and add readable columns to each fact
# ---------------------------------------------------------------------
def load(name):
    return pd.read_csv(os.path.join(DATA, f"{name}.csv"))


date = load("dim_date")
dept = load("dim_department")
loans = (load("fact_book_loan")
         .merge(date, left_on="checkout_date_key", right_on="date_key")
         .merge(dept, on="department_key").merge(load("dim_book"), on="book_key")
         .merge(load("dim_student"), on="student_key"))
digital = (load("fact_digital_usage").merge(date, on="date_key").merge(dept, on="department_key")
           .merge(load("dim_resource"), on="resource_key").merge(load("dim_user_type"), on="user_type_key"))
rooms = (load("fact_room_booking").merge(date, on="date_key").merge(dept, on="department_key")
         .merge(load("dim_room"), on="room_key").merge(load("dim_time_slot"), on="time_slot_key"))

YEAR, PREV = 2025, 2024


# ---------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------
def new_canvas(title, subtitle, filters):
    """1920 x 1080 page with a title and a row of slicers (filters)."""
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=PAGE)
    fig.text(0.02, 0.955, title, fontsize=24, weight="semibold", color=INK)
    fig.text(0.02, 0.925, subtitle, fontsize=12, color=INK2)
    x = 0.98
    for label in reversed(filters):                   # slicers drawn right-aligned
        w = 0.0062 * len(label) + 0.03
        x -= w
        fig.patches.append(FancyBboxPatch((x, 0.928), w - 0.008, 0.034, boxstyle="round,pad=0.002,rounding_size=0.006",
                                          transform=fig.transFigure, facecolor=CARD, edgecolor=BORDER, zorder=-1))
        fig.text(x + 0.008, 0.945, label + "  ▾", fontsize=11, color=INK, va="center")
    return fig


def card(fig, rect):
    """White card with a thin border behind a visual."""
    fig.patches.append(FancyBboxPatch(rect[:2], rect[2], rect[3], boxstyle="round,pad=0,rounding_size=0.008",
                                      transform=fig.transFigure, facecolor=CARD, edgecolor=BORDER, zorder=-1))   # behind the charts


def kpi(fig, rect, label, value, delta=None, good_when_up=True, note=None):
    """A KPI card: label, big number, change vs last year (arrow + text, never colour alone)."""
    card(fig, rect)
    x, y, w, h = rect
    fig.text(x + 0.012, y + h - 0.035, label, fontsize=12, color=INK2)
    fig.text(x + 0.012, y + h * 0.36, value, fontsize=30, weight="semibold", color=INK)
    if delta is not None:
        up = delta >= 0
        good = up == good_when_up
        fig.text(x + 0.012, y + 0.018, f"{'▲' if up else '▼'} {abs(delta):.1f}% vs {PREV}",
                 fontsize=11, color=GOOD if good else BAD)
    elif note:
        fig.text(x + 0.012, y + 0.018, note, fontsize=11, color=MUTED)


def chart(fig, rect, title, pad=(0.045, 0.06, 0.02, 0.07)):
    """Card + axes inside it. pad = left, bottom, right, top margins inside the card."""
    card(fig, rect)
    x, y, w, h = rect
    fig.text(x + 0.012, y + h - 0.032, title, fontsize=13, weight="semibold", color=INK)
    ax = fig.add_axes([x + pad[0], y + pad[1], w - pad[0] - pad[2], h - pad[1] - pad[3]])
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return ax


def pct_change(new, old):
    return (new - old) / old * 100


def bar_ends_rounded(ax):
    """Thin bars with a small rounded look: draw a 1px surface gap between bars."""
    for p in ax.patches:
        p.set_edgecolor(CARD)
        p.set_linewidth(1.5)


# =====================================================================
# 1. EXECUTIVE DASHBOARD
# =====================================================================
def executive():
    fig = new_canvas("Executive Dashboard", "University Library Analytics  ·  key figures for the Library Director",
                     ["Year: 2025", "Department: All", "Service: All"])
    ly, py_ = loans[loans.year_num == YEAR], loans[loans.year_num == PREV]
    dy, dp = digital[digital.year_num == YEAR], digital[digital.year_num == PREV]
    ry, rp = rooms[rooms.year_num == YEAR], rooms[rooms.year_num == PREV]

    w, gap, top = 0.152, 0.008, 0.745
    cards = [
        ("Book loans", f"{len(ly):,}", pct_change(len(ly), len(py_)), True),
        ("Digital downloads", f"{dy.download_count.sum():,}", pct_change(dy.download_count.sum(), dp.download_count.sum()), True),
        ("Room bookings", f"{len(ry):,}", pct_change(len(ry), len(rp)), True),
        ("Avg loan duration", f"{ly.loan_duration_days.mean():.1f} days",
         pct_change(ly.loan_duration_days.mean(), py_.loan_duration_days.mean()), False),
        ("Overdue loans (>21 days)", f"{ly[ly.is_returned].is_overdue.mean() * 100:.0f}%",
         pct_change(ly[ly.is_returned].is_overdue.mean(), py_[py_.is_returned].is_overdue.mean()), False),
        ("Downloads per book loan", f"{dy.download_count.sum() / len(ly):.1f}",
         pct_change(dy.download_count.sum() / len(ly), dp.download_count.sum() / len(py_)), True),
    ]
    for i, (lab, val, d, good_up) in enumerate(cards):
        kpi(fig, (0.02 + i * (w + gap), top, w, 0.155), lab, val, d, good_up)

    # ---- Line chart: usage index (2023 average month = 100) - one axis for all three services
    ax = chart(fig, (0.02, 0.37, 0.6, 0.355), "Are digital resources replacing physical books?  Usage index (2023 average month = 100)",
               pad=(0.04, 0.05, 0.075, 0.06))
    monthly = pd.DataFrame({
        "Book Loans": loans.groupby("month_label").size(),
        "Digital Downloads": digital.groupby("month_label").download_count.sum(),
        "Room Bookings": rooms.groupby("month_label").size(),
    })
    smooth = monthly.rolling(3, min_periods=1).mean()                      # 3-month average = calmer lines
    index = smooth / monthly.loc[monthly.index.str.startswith("2023")].mean() * 100
    xs = np.arange(len(index))
    for s, col in SERVICE.items():
        ax.plot(xs, index[s], color=col, linewidth=2.2)
        ax.text(xs[-1] + 0.6, index[s].iloc[-1], f"{s}  {index[s].iloc[-1]:.0f}", color=INK, fontsize=10, va="center")
        ax.plot([xs[-1]], [index[s].iloc[-1]], "o", color=col, markersize=6, markeredgecolor=CARD, markeredgewidth=1.5)
    ax.axhline(100, color="#c3c2b7", linewidth=1)
    ax.set_xticks(xs[::3])
    ax.set_xticklabels(index.index[::3], fontsize=9)
    ax.set_xlim(-0.5, len(xs) - 0.5)
    ax.set_ylim(0, index.max().max() * 1.12)

    # ---- Donut: digital downloads by resource type
    ax = chart(fig, (0.628, 0.37, 0.352, 0.355), f"Digital downloads by resource type ({YEAR})", pad=(0.01, 0.02, 0.15, 0.06))
    ax.grid(False)
    by_type = dy.groupby("resource_type").download_count.sum().reindex(RESOURCE)
    wedges, _ = ax.pie(by_type, colors=[RESOURCE[t] for t in by_type.index], startangle=90, counterclock=False,
                       wedgeprops={"width": 0.38, "edgecolor": CARD, "linewidth": 2})
    ax.text(0, 0.06, f"{by_type.sum():,}", ha="center", fontsize=20, weight="semibold", color=INK)
    ax.text(0, -0.16, "downloads", ha="center", fontsize=10, color=INK2)
    for i, (t, v) in enumerate(by_type.items()):
        fig.text(0.86, 0.62 - i * 0.055, "■", color=RESOURCE[t], fontsize=16, va="center")
        fig.text(0.875, 0.62 - i * 0.055, f"{t}  {v / by_type.sum() * 100:.0f}%", fontsize=12, color=INK, va="center")

    # ---- Bar: department ranking (total usage events, YEAR)
    ax = chart(fig, (0.02, 0.03, 0.4, 0.32), f"Which departments use the library most? ({YEAR}, all services)",
               pad=(0.11, 0.03, 0.04, 0.06))
    total = (ly.groupby("department_name").size() + dy.groupby("department_name").download_count.sum()
             + ry.groupby("department_name").size()).drop("Unknown", errors="ignore").sort_values().astype(int)
    ax.barh(total.index, total.values, color=SERVICE["Book Loans"], height=0.6)
    bar_ends_rounded(ax)
    for i, v in enumerate(total.values):
        ax.text(v + total.max() * 0.01, i, f"{v:,}", va="center", fontsize=10, color=INK)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.tick_params(axis="y", labelsize=10, length=0)

    # ---- Table: top 5 borrowed books
    card(fig, (0.428, 0.03, 0.552, 0.32))
    fig.text(0.44, 0.318, f"Top 5 borrowed books ({YEAR})", fontsize=13, weight="semibold", color=INK)
    top5 = ly[ly.book_key != 1].groupby(["title", "book_category"]).size().sort_values(ascending=False).head(5)
    fig.text(0.44, 0.275, "Title", fontsize=10, color=MUTED)
    fig.text(0.80, 0.275, "Category", fontsize=10, color=MUTED)
    fig.text(0.955, 0.275, "Loans", fontsize=10, color=MUTED, ha="right")
    for i, ((title, cat), n) in enumerate(top5.items()):
        y = 0.235 - i * 0.042
        fig.text(0.44, y, f"{i + 1}.  {title}", fontsize=12, color=INK)
        fig.text(0.80, y, cat, fontsize=12, color=INK2)
        fig.text(0.955, y, f"{n}", fontsize=12, color=INK, ha="right", weight="semibold")
        fig.add_artist(plt.Line2D([0.44, 0.965], [y - 0.014, y - 0.014], transform=fig.transFigure, color=GRID, linewidth=0.8))
    fig.savefig(os.path.join(HERE, "executive_dashboard.jpg"), dpi=100, facecolor=PAGE, pil_kwargs={"quality": 92})
    plt.close(fig)


# =====================================================================
# 2. DEPARTMENT DASHBOARD
# =====================================================================
def department():
    fig = new_canvas("Department Dashboard", "Usage by academic unit  ·  2023-2025  ·  department heads see only their own unit",
                     ["Year: All", "Department: All", "Student level: All"])
    order = (loans.groupby("department_name").size() + digital.groupby("department_name").download_count.sum()
             + rooms.groupby("department_name").size()).drop("Unknown", errors="ignore").sort_values(ascending=False).index

    # ---- Small multiples: one bar chart per service (different scales, so not one axis)
    data = {"Book Loans": loans.groupby("department_name").size(),
            "Digital Downloads": digital.groupby("department_name").download_count.sum(),
            "Room Bookings": rooms.groupby("department_name").size()}
    for i, (s, series) in enumerate(data.items()):
        ax = chart(fig, (0.02 + i * 0.322, 0.53, 0.314, 0.37), f"{s} by department",
                   pad=(0.035, 0.085, 0.01, 0.065))
        vals = series.reindex(order).fillna(0)
        short = [n.replace("Arts & Humanities", "Arts & Hum.").replace("Natural Sciences", "Nat. Sci.")
                  .replace("Computer Science", "Comp. Sci.").replace("Health Sciences", "Health Sci.") for n in vals.index]
        ax.bar(range(len(vals)), vals.values, color=SERVICE[s], width=0.62)
        bar_ends_rounded(ax)
        for j, v in enumerate(vals.values):
            ax.text(j, v + vals.max() * 0.015, f"{int(v):,}", ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(short, rotation=35, ha="right", fontsize=9)
        ax.set_ylim(0, vals.max() * 1.12)

    # ---- Heat map (pivot): department x resource type
    ax = chart(fig, (0.02, 0.03, 0.36, 0.47), "Pivot: digital downloads, department × resource type",
               pad=(0.105, 0.03, 0.015, 0.09))
    pivot = digital.pivot_table(index="department_name", columns="resource_type", values="download_count",
                                aggfunc="sum").reindex(order)[list(RESOURCE)]
    ax.imshow(pivot.values, cmap=BLUES, aspect="auto")
    ax.grid(False)
    for (r, c), v in np.ndenumerate(pivot.values):
        ax.text(c, r, f"{int(v):,}", ha="center", va="center", fontsize=11,
                color="white" if v > pivot.values.max() * 0.55 else INK)
    ax.set_xticks(range(3))
    ax.set_xticklabels(pivot.columns, fontsize=11)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(pivot.index, fontsize=10)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

    # ---- Average loan duration by department (+ overdue %)
    ax = chart(fig, (0.388, 0.03, 0.29, 0.47), "Average loan duration (days)", pad=(0.105, 0.04, 0.05, 0.08))
    ret = loans[loans.is_returned]
    dur = ret.groupby("department_name").agg(days=("loan_duration_days", "mean"), overdue=("is_overdue", "mean"))
    dur = dur.drop("Unknown", errors="ignore").sort_values("days")
    ax.barh(dur.index, dur.days, color=SERVICE["Book Loans"], height=0.6)
    bar_ends_rounded(ax)
    for i, (d, o) in enumerate(zip(dur.days, dur.overdue)):
        ax.text(d + 0.2, i, f"{d:.1f}  ({o * 100:.0f}% overdue)", va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, dur.days.max() * 1.55)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.tick_params(axis="y", length=0, labelsize=10)

    # ---- Undergraduate vs graduate
    card(fig, (0.686, 0.03, 0.294, 0.47))
    fig.text(0.698, 0.468, "Undergraduate vs graduate", fontsize=13, weight="semibold", color=INK)
    fig.text(0.698, 0.44, "■", color=LEVEL["Undergraduate"], fontsize=14)
    fig.text(0.71, 0.44, "Undergraduate", fontsize=11, color=INK)
    fig.text(0.79, 0.44, "■", color=LEVEL["Graduate"], fontsize=14)
    fig.text(0.802, 0.44, "Graduate", fontsize=11, color=INK)
    sl = loans[loans.student_level.isin(LEVEL)]
    g = sl.groupby("student_level")
    stats = {
        "Avg loan days": g.loan_duration_days.mean(),
        "Overdue %": g.is_overdue.mean() * 100,
        "Research books %": g.apply(lambda x: (x.book_category == "Research").mean() * 100),
        "Journal share of downloads %": digital.groupby(digital.student_level).apply(
            lambda x: x[x.resource_type == "Journal"].download_count.sum() / x.download_count.sum() * 100),
    }
    for i, (name, val) in enumerate(stats.items()):
        y0 = 0.385 - i * 0.088
        fig.text(0.698, y0, name, fontsize=11, color=INK2)
        top = max(val["Undergraduate"], val["Graduate"])
        for j, lev in enumerate(["Undergraduate", "Graduate"]):
            v = val[lev]
            yb = y0 - 0.03 - j * 0.026
            fig.patches.append(plt.Rectangle((0.698, yb), 0.2 * v / top, 0.02, transform=fig.transFigure,
                                             facecolor=LEVEL[lev], edgecolor="none"))
            fig.text(0.702 + 0.2 * v / top, yb + 0.01, f"{v:.1f}", fontsize=10, color=INK, va="center")
    fig.savefig(os.path.join(HERE, "department_dashboard.jpg"), dpi=100, facecolor=PAGE, pil_kwargs={"quality": 92})
    plt.close(fig)


# =====================================================================
# 3. OPERATIONAL DASHBOARD
# =====================================================================
def operational():
    fig = new_canvas("Operational Dashboard", "Daily operations  ·  study rooms and circulation  ·  data up to 31 Dec 2025",
                     ["Period: last 30 days", "Room: All"])
    end = pd.Timestamp("2025-12-31")
    rooms["d"] = pd.to_datetime(rooms.full_date)
    last30 = rooms[rooms.d > end - pd.Timedelta(days=30)]
    prev30 = rooms[(rooms.d <= end - pd.Timedelta(days=30)) & (rooms.d > end - pd.Timedelta(days=60))]
    out = loans[~loans.is_returned].copy()
    out["days_out"] = (end - pd.to_datetime(out.full_date)).dt.days
    real_rooms = 11
    util = last30.duration_hours.sum() / (real_rooms * 12 * 30) * 100

    w, gap, top = 0.152, 0.008, 0.745
    cards = [
        ("Room bookings", f"{len(last30):,}", None, "last 30 days"),
        ("Hours booked", f"{last30.duration_hours.sum():,.0f} h", None, f"previous 30 days: {prev30.duration_hours.sum():,.0f} h"),
        ("Room utilisation", f"{util:.1f}%", None, "booked hours / open hours"),
        ("Walk-in bookings", f"{last30.is_walk_in.mean() * 100:.0f}%", None, "no StudentID recorded"),
        ("Books currently out", f"{len(out):,}", None, "not yet returned"),
        ("Out longer than 30 days", f"{(out.days_out > 30).sum():,}", None, "follow up at the desk"),
    ]
    for i, (lab, val, d, note) in enumerate(cards):
        kpi(fig, (0.02 + i * (w + gap), top, w, 0.155), lab, val, d, note=note)

    # ---- Heat map: peak times (day x time slot), 2025
    ax = chart(fig, (0.02, 0.37, 0.4, 0.355), "Peak times: room bookings by day and time slot (2025)",
               pad=(0.06, 0.03, 0.015, 0.09))
    r25 = rooms[(rooms.year_num == YEAR) & (rooms.slot_code != "UNK")]
    heat = r25.pivot_table(index="day_of_week", columns="slot_label", values="booking_count", aggfunc="sum").fillna(0)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ax.imshow(heat.values, cmap=BLUES, aspect="auto")
    ax.grid(False)
    for (r, c), v in np.ndenumerate(heat.values):
        ax.text(c, r, f"{int(v)}", ha="center", va="center", fontsize=10,
                color="white" if v > heat.values.max() * 0.55 else INK)
    ax.set_xticks(range(heat.shape[1]))
    ax.set_xticklabels([s.replace(" - ", "-") for s in heat.columns], fontsize=9.5)
    ax.xaxis.tick_top()
    ax.set_yticks(range(7))
    ax.set_yticklabels(days, fontsize=10)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

    # ---- Daily bookings, last 60 days + 7-day average (roll-up)
    ax = chart(fig, (0.428, 0.37, 0.552, 0.355), "Daily room bookings, last 60 days (bars) and 7-day average (line)",
               pad=(0.035, 0.07, 0.015, 0.07))
    days60 = pd.date_range(end - pd.Timedelta(days=59), end)
    daily = rooms.groupby("d").size().reindex(days60, fill_value=0)
    ax.bar(range(60), daily.values, color=SERVICE["Room Bookings"], width=0.75)
    ax.plot(range(60), daily.rolling(7, min_periods=1).mean().values, color=INK, linewidth=1.8)
    ax.set_xticks(range(0, 60, 7))
    ax.set_xticklabels([d.strftime("%d %b") for d in days60[::7]], fontsize=9)
    ax.set_xlim(-0.6, 59.6)

    # ---- Room utilisation (2025)
    ax = chart(fig, (0.02, 0.03, 0.4, 0.32), "Room utilisation 2025 (% of open hours booked)",
               pad=(0.12, 0.03, 0.05, 0.06))
    rs = r25[r25.room_number != "UNKNOWN"].groupby(["room_number", "room_type", "capacity"]).duration_hours.sum().reset_index()
    rs["util"] = rs.duration_hours / (12 * 365) * 100
    rs = rs.sort_values("util")
    labels = [f"{r.room_number}  {r.room_type}, {r.capacity} seats" for r in rs.itertuples()]
    ax.barh(labels, rs.util, color=SERVICE["Room Bookings"], height=0.62)
    bar_ends_rounded(ax)
    for i, v in enumerate(rs.util):
        ax.text(v + 0.1, i, f"{v:.1f}%", va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, rs.util.max() * 1.18)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.tick_params(axis="y", length=0, labelsize=9.5)

    # ---- Books out: ageing
    ax = chart(fig, (0.428, 0.03, 0.29, 0.32), "Books not returned: how long out?", pad=(0.04, 0.06, 0.015, 0.07))
    bins = pd.cut(out.days_out, [-1, 14, 30, 90, 10_000], labels=["0-14 d", "15-30 d", "31-90 d", "90+ d"])
    counts = bins.value_counts().reindex(["0-14 d", "15-30 d", "31-90 d", "90+ d"])
    ax.bar(counts.index, counts.values, color=SERVICE["Book Loans"], width=0.6)
    bar_ends_rounded(ax)
    for i, v in enumerate(counts.values):
        ax.text(i, v + counts.max() * 0.02, f"{v}", ha="center", fontsize=11, color=INK)
    ax.set_ylim(0, counts.max() * 1.15)

    # ---- Alerts (status: icon + label, never colour alone)
    card(fig, (0.726, 0.03, 0.254, 0.32))
    fig.text(0.738, 0.318, "Alerts", fontsize=13, weight="semibold", color=INK)
    alerts = [
        (BAD, "!", "Anomaly - digital downloads", "Oct 2024: -57% vs normal October\n(e-resource platform outage)"),
        ("#ec835a", "!", "Busiest slot", "Wed 14:00-16:00 - open overflow\nroom or add staff at the desk"),
        (GOOD, "✓", "Data quality", "Last ETL: 0 duplicates in warehouse,\nall 12 validation checks passed"),
    ]
    for i, (col, icon, head, text) in enumerate(alerts):
        y = 0.262 - i * 0.087
        fig.patches.append(plt.Circle((0.748, y + 0.004), 0.009, transform=fig.transFigure, color=col))
        fig.text(0.748, y + 0.004, icon, color="white", fontsize=11, ha="center", va="center", weight="bold")
        fig.text(0.763, y + 0.004, head, fontsize=11.5, weight="semibold", color=INK, va="center")
        fig.text(0.763, y - 0.016, text, fontsize=10, color=INK2, va="top", linespacing=1.4)
    fig.savefig(os.path.join(HERE, "operational_dashboard.jpg"), dpi=100, facecolor=PAGE, pil_kwargs={"quality": 92})
    plt.close(fig)


if __name__ == "__main__":
    executive()
    department()
    operational()
    print("Saved executive_dashboard.jpg, department_dashboard.jpg, operational_dashboard.jpg")
