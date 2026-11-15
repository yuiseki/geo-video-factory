# Charts for the panels (static PNG, dark surface, one series each, no legend: the caption names it).
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import datetime as dt

FONT = [f for f in fm.findSystemFonts() if "NotoSansCJK-Regular" in f or "NotoSansCJKjp-Regular" in f]
if FONT:
    fm.fontManager.addfont(FONT[0]); plt.rcParams["font.family"] = fm.FontProperties(fname=FONT[0]).get_name()
SURF, INK, MUTED, GRID, SERIES = "#121a2c", "#f2f4f8", "#aab4c8", "#2a3550", "#ff9a3c"

def chart(points, path, ylim, yfmt, note, label_idx):
    xs = [dt.date(y, m, 15) for (y, m, v) in points]; ys = [v for (_, _, v) in points]
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=200)
    fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
    ax.plot(xs, ys, color=SERIES, lw=3.2, solid_capstyle="round")
    ax.scatter(xs, ys, s=28, color=SERIES, zorder=3, edgecolor=SURF, linewidth=1.5)
    for i in label_idx:
        ax.annotate(yfmt(ys[i]), (xs[i], ys[i]), textcoords="offset points", xytext=(0, 12), ha="center", color=INK, fontsize=15)
    ax.set_ylim(*ylim)
    for s in ax.spines.values(): s.set_visible(False)
    ax.grid(axis="y", color=GRID, lw=1); ax.tick_params(colors=MUTED, labelsize=13, length=0)
    ax.yaxis.set_major_formatter(lambda v, p: yfmt(v))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y年"))
    ax.xaxis.set_major_locator(matplotlib.dates.YearLocator())
    fig.text(0.99, 0.01, note, color=MUTED, fontsize=10, ha="right", va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(path, facecolor=SURF); plt.close(fig)

# 東京都区部 もやし 1kg (円)。東京都「東京の物価」第7表。主な月の値 (research/market.md、2025-09〜2026-09 は CSV で確認)
moyashi = [(2021,1,158),(2021,11,163),(2022,6,163),(2022,12,166),(2023,1,166),(2023,7,176),(2023,12,173),(2024,1,173),(2024,6,177),(2024,11,183),
           (2025,1,178),(2025,3,177),(2025,6,179),(2025,9,175),(2025,12,179),(2026,1,180),(2026,2,177),(2026,3,179),(2026,4,179),(2026,5,180),(2026,6,177),(2026,7,181),(2026,8,180),(2026,9,180)]
chart(moyashi, "assets/chart_moyashi_tokyo.png", (140, 195), lambda v: f"{v:.0f}円", "主な月の値。出典：東京都「東京の物価」(総務省 小売物価統計調査)", [0, 9, 23])

# A重油 大型ローリー 全国平均 (円/L)。資源エネルギー庁 (新電力ネットの転載で確認)
aoil = [(2025,1,100.1),(2025,10,99.3),(2026,1,96.3),(2026,2,99.1),(2026,3,122.6),(2026,4,130.5),(2026,5,129.6),(2026,6,123.6),(2026,7,121.0),(2026,8,120.3),(2026,9,120.4)]
chart(aoil, "assets/chart_a_heavy_oil.png", (85, 140), lambda v: f"{v:.0f}円", "大型ローリー、全国平均。出典：資源エネルギー庁(新電力ネット経由)", [3, 5, 10])
print("ok")
