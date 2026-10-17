"""Render the README benchmark chart from the recorded results.

Usage: python scripts/plot_benchmark.py [bench/results/latest.json] [docs/media/benchmark-f1.png]

Test split only. For keyword and vector the best k per subset is shown and labelled,
which favours the baselines. Every k is published in docs/BENCHMARK.md.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "bench/results/latest.json")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/media/benchmark-f1.png")

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"graph": "#2a78d6", "keyword": "#eb6834", "vector": "#1baf7a"}
NAMES = {"graph": "Graph reasoning", "keyword": "Keyword search (best k)", "vector": "Vector RAG (best k)"}
SUBSETS = [("change", "Change impact\n(15 questions)"), ("brain", "Company brain\n(15 questions)"), ("all", "All test\n(30 questions)")]

data = json.loads(SRC.read_text(encoding="utf-8"))
rows = [r for r in data["summary"] if r["split"] == "test"]


def best(kind, system):
    cands = [r for r in rows if r["kind"] == kind and r["system"] == system]
    return max(cands, key=lambda r: r["f1"])


fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)
width, gap = 0.26, 0.02
for i, (kind, label) in enumerate(SUBSETS):
    for j, system in enumerate(("graph", "keyword", "vector")):
        r = best(kind, system)
        x = i + (j - 1) * (width + gap)
        ax.bar(x, r["f1"], width, color=COLORS[system], label=NAMES[system] if i == 0 else None, zorder=3)
        tag = f"{r['f1']:.2f}" + (f"\nk={r['k']}" if r["k"] else "")
        ax.text(x, r["f1"] + 0.015, tag, ha="center", va="bottom", fontsize=10, color=INK, zorder=4)

ax.set_xticks(range(len(SUBSETS)), [s[1] for s in SUBSETS], fontsize=11, color=INK)
ax.set_ylim(0, 1.12)
ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
ax.tick_params(axis="y", colors=MUTED, labelsize=10, length=0)
ax.tick_params(axis="x", length=0)
ax.set_ylabel("Macro F1 (higher is better)", color=MUTED, fontsize=10)
ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.legend(loc="upper right", frameon=False, fontsize=10, labelcolor=INK, ncol=3, bbox_to_anchor=(1, 1.02))
fig.text(0.06, 0.95, "Graph reasoning vs. keyword and vector retrieval on the same FalkorDB",
         fontsize=14, fontweight="bold", color=INK)
fig.text(0.06, 0.905, "Authored synthetic benchmark, test split. Same 44 ADR passages for keyword and vector. "
         "Limits: docs/BENCHMARK.md", fontsize=10, color=MUTED)
fig.subplots_adjust(left=0.07, right=0.98, top=0.83, bottom=0.14)
fig.patches.append(matplotlib.patches.Rectangle((0, 0), 1, 1, transform=fig.transFigure, fill=False,
                                                edgecolor=GRID, linewidth=2))
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, facecolor=SURFACE)
print(f"wrote {OUT}")
