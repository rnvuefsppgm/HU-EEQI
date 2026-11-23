# -*- coding: utf-8 -*-
"""Figura 2: localização das 27 capitais e das cinco regiões do Brasil (IBGE, 2024; SIRGAS 2000).
Grava figuras/Figure_2_location.png (600 dpi) e .svg, com revisão automática de layout
(checar_layout.py) e uma checagem extra de rótulo sobre marcador de capital.
Uso: python figura2_localizacao.py"""
import os
import sys
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.text
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
sys.path.insert(0, V6)
sys.path.insert(0, os.path.join(V6, "mapas_anuais_filled"))
import figure_style as fs                                  # noqa: E402  (Arial, 7-8 pt, 600 dpi, SVG editável)
from checar_layout import auditar                          # noqa: E402

UF_SHP = os.path.join(HERE, "data", "BR_UF_2024.shp")       # IBGE, malha estadual 2024
CAP_SHP = os.path.join(V6, "mapas_anuais_filled", "data", "Capitais.shp")
FIG_DIR = os.path.join(HERE, "figuras")
LOG = os.path.join(HERE, "revisao_layout.txt")
os.makedirs(FIG_DIR, exist_ok=True)

REG_EN = {"Norte": "North", "Nordeste": "Northeast", "Centro-oeste": "Central-West",
          "Centro-Oeste": "Central-West", "Sudeste": "Southeast", "Sul": "South"}
REG_COL = {"North": "#cbe6cf", "Northeast": "#f7e1b5", "Central-West": "#f4cfc2",
           "Southeast": "#cdd9ee", "South": "#e3d6ec"}
REG_DARK = {"North": "#2f7d4f", "Northeast": "#b9791c", "Central-West": "#b4513a",
            "Southeast": "#3b5f9e", "South": "#77529a"}
SA_JSON = os.path.join(HERE, "data", "south_america_LSIB2017.geojson")   # USDOS LSIB simple (2017), via GEE
REG_ORDER = ["North", "Northeast", "Central-West", "Southeast", "South"]

# Posição do rótulo de cada capital: (dx, dy) em pontos a partir do marcador e alinhamento.
# Rótulos da costa nordestina vão para o oceano com linha de chamada.
LAB = {
    "Boa Vista": (6, 2, "left"), "Macapá": (6, 1, "left"), "Belém": (6, 3, "left"),
    "São Luís": (-6, -5, "right"), "Manaus": (6, 1, "left"), "Teresina": (-6, 0, "right"),
    "Fortaleza": (14, 4, "left"), "Natal": (14, 3, "left"), "João Pessoa": (14, 0, "left"),
    "Recife": (14, -4, "left"), "Maceió": (14, -6, "left"), "Aracaju": (14, -9, "left"),
    "Salvador": (12, -4, "left"), "Porto Velho": (-6, 3, "right"), "Rio Branco": (-6, -3, "right"),
    "Palmas": (6, 0, "left"), "Cuiabá": (-6, 0, "right"), "Brasília": (6, 3, "left"),
    "Goiânia": (-6, -3, "right"), "Campo Grande": (-6, -2, "right"), "Belo Horizonte": (-6, 0, "right"),
    "Vitória": (6, 0, "left"), "Rio de Janeiro": (6, -4, "left"), "São Paulo": (-6, -3, "right"),
    "Curitiba": (6, 0, "left"), "Florianópolis": (6, 0, "left"), "Porto Alegre": (-6, 2, "right"),
}
LEADER = {"Fortaleza", "Natal", "João Pessoa", "Recife", "Maceió", "Aracaju", "Salvador"}
# Siglas dos estados: deslocamento (graus) em relação ao ponto representativo, para não tocar nos rótulos
UF_SHIFT = {"MS": (1.6, 1.2), "RS": (-1.5, 1.4), "GO": (-1.0, 0.6), "SE": (-0.95, 0.55), "AL": (-0.9, 0.35),
            "PE": (-1.0, 0.0), "PB": (-0.6, 0.0), "RN": (-0.6, 0.15), "MT": (0.8, 1.5), "AC": (0.0, 0.6),
            "RO": (0.4, -1.2), "PI": (0.4, -0.6), "MA": (0.4, -0.6), "SP": (0.5, 0.9), "PR": (-1.2, -0.3),
            "TO": (-0.4, 1.6), "MG": (0.0, 0.6), "ES": (-1.0, 0.9), "RJ": (-0.4, 0.45), "SC": (-0.4, 0.1)}
UF_SKIP = {"DF"}                                           # o DF é o próprio ponto de Brasília


def deg_fmt(axis):
    def f(v, _):
        if axis == "x":
            return f"{abs(v):.0f}°W" if v < 0 else f"{v:.0f}°E"
        return f"{abs(v):.0f}°S" if v < 0 else ("0°" if v == 0 else f"{v:.0f}°N")
    return FuncFormatter(f)


def main():
    uf = gpd.read_file(UF_SHP).to_crs("EPSG:4674")
    uf["region"] = uf["NM_REGIA"].map(REG_EN)
    cap = gpd.read_file(CAP_SHP).to_crs("EPSG:4674")
    pts = cap.copy()
    pts["geometry"] = cap.geometry.representative_point()
    reg = uf.dissolve("region")
    br = uf.dissolve()
    # simplifica (~1 km, invisível na escala do país) só depois de dissolver: SVG leve e sem frestas entre estados
    tol = 0.01
    reg["geometry"] = reg.geometry.simplify(tol, preserve_topology=True)
    br["geometry"] = br.geometry.simplify(tol, preserve_topology=True)
    uf_lines = uf.boundary.simplify(tol, preserve_topology=True)

    W = fs.WIDTH_CM * fs.CM
    fig, ax = plt.subplots(figsize=(W, W * 0.86))
    lat0 = -14.0
    ax.set_aspect(1 / np.cos(np.radians(lat0)))
    for r in REG_ORDER:
        reg.loc[[r]].plot(ax=ax, color=REG_COL[r], edgecolor="none", zorder=1)
    uf_lines.plot(ax=ax, color="#8c8c8c", linewidth=0.3, zorder=2)
    br.boundary.plot(ax=ax, color="#333333", linewidth=0.6, zorder=3)

    for _, u in uf.iterrows():
        s = u["SIGLA_UF"]
        if s in UF_SKIP:
            continue
        p = u.geometry.representative_point()
        dx, dy = UF_SHIFT.get(s, (0, 0))
        ax.text(p.x + dx, p.y + dy, s, fontsize=6, color="#6e6e6e", style="italic",
                ha="center", va="center", zorder=4)

    pts["region"] = pts["NM_REGIA"].map(REG_EN)
    ax.scatter(pts.geometry.x, pts.geometry.y, s=16, marker="s", c=pts["region"].map(REG_DARK),
               edgecolor="white", linewidth=0.7, zorder=6)
    for _, c in pts.iterrows():
        name = c["NM_MUN"]
        dx, dy, ha = LAB[name]
        kw = dict(textcoords="offset points", xytext=(dx, dy), ha=ha, va="center",
                  fontsize=fs.FS_SMALL, fontweight="bold", color="#1a1a1a", zorder=8)
        if name in LEADER:
            kw["arrowprops"] = dict(arrowstyle="-", color="#555555", lw=0.4, shrinkA=0, shrinkB=2.5)
        ax.annotate(name, (c.geometry.x, c.geometry.y), **kw)

    x0, y0, x1, y1 = br.total_bounds
    ax.set_xlim(x0 - 1.2, x1 + 4.2)
    ax.set_ylim(y0 - 1.0, y1 + 1.2)
    ax.set_xticks([-70, -60, -50, -40])
    ax.set_yticks([0, -10, -20, -30])
    ax.xaxis.set_major_formatter(deg_fmt("x"))
    ax.yaxis.set_major_formatter(deg_fmt("y"))
    ax.tick_params(length=2, width=0.4, labelsize=fs.FS_SMALL, top=True, right=True,
                   labeltop=False, labelright=False)
    ax.grid(color="#bdbdbd", linewidth=0.3, linestyle=(0, (3, 3)), zorder=0)

    # legenda das regiões
    from matplotlib.lines import Line2D
    hs = [Patch(facecolor=REG_COL[r], edgecolor=REG_DARK[r], linewidth=0.5, label=r) for r in REG_ORDER]
    hs += [Line2D([], [], marker="s", ls="none", color="#555555", mec="white", ms=5, label="State capital"),
           Line2D([], [], color="#8c8c8c", lw=0.6, label="State boundary")]
    leg = ax.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.5, -0.045), ncol=7, frameon=False,
                    fontsize=fs.FS_SMALL, handlelength=1.4, columnspacing=1.1, handletextpad=0.4)
    # barra de escala (km no paralelo da barra)
    ybar = y0 + 1.6
    km_deg = 111.32 * np.cos(np.radians(ybar))
    xs = x0 + 0.2
    for k, colr in enumerate(["#1a1a1a", "white"]):
        ax.add_patch(Rectangle((xs + k * 250 / km_deg, ybar), 250 / km_deg, 0.35, facecolor=colr,
                               edgecolor="#1a1a1a", linewidth=0.5, zorder=9))
    for k, lab in enumerate(["0", "250", "500 km"]):
        ax.text(xs + k * 250 / km_deg, ybar + 0.6, lab, fontsize=6, ha="center" if k < 2 else "left",
                va="bottom", zorder=9)
    # rosa dos ventos simples (acima da barra de escala)
    from matplotlib.patches import Polygon
    cx, cy, rr = xs + 1.0, ybar + 4.2, 1.5
    ax.add_patch(Polygon([(cx, cy + rr), (cx - 0.45, cy), (cx, cy + 0.25)], closed=True, fc="#1a1a1a",
                         ec="#1a1a1a", lw=0.4, zorder=9))
    ax.add_patch(Polygon([(cx, cy + rr), (cx + 0.45, cy), (cx, cy + 0.25)], closed=True, fc="white",
                         ec="#1a1a1a", lw=0.4, zorder=9))
    ax.text(cx, cy + rr + 0.25, "N", fontsize=fs.FS, fontweight="bold", ha="center", va="bottom", zorder=9)
    # fonte (sem caixa, sob a barra de escala)
    ax.text(xs, y0 - 0.75, "Data: IBGE (2024), LSIB (2017) · Datum: SIRGAS 2000", fontsize=6, ha="left",
            va="bottom", color="#444444", zorder=9)
    # inset: o Brasil na América do Sul
    sa = gpd.read_file(SA_JSON)
    ins = ax.inset_axes([0.80, 0.035, 0.18, 0.27])
    sa.plot(ax=ins, color="#e6e6e6", edgecolor="#9e9e9e", linewidth=0.25)
    br.plot(ax=ins, color="#7d7d7d", edgecolor="#4d4d4d", linewidth=0.3)
    ins.set_xlim(-82, -34)
    ins.set_ylim(-56, 13)
    ins.set_aspect(1 / np.cos(np.radians(-20)))
    ins.set_xticks([])
    ins.set_yticks([])
    ins.set_facecolor("white")
    for sp in ins.spines.values():
        sp.set_linewidth(0.5)
        sp.set_color("#777777")
    ins.set_title("South America", fontsize=5.5, color="#333333", pad=1.5)

    # checagem extra: rótulo de capital sobre marcador de outra capital
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    xy = ax.transData.transform(np.c_[pts.geometry.x, pts.geometry.y])
    rad = 4.5 * fig.dpi / 72
    extra = []
    for t in ax.texts:
        if t.get_text() not in LAB:
            continue
        bb = matplotlib.text.Text.get_window_extent(t, r)      # só o texto (sem a linha de chamada)
        for (px, py), nm in zip(xy, pts["NM_MUN"]):
            if nm != t.get_text() and bb.x0 - rad < px < bb.x1 + rad and bb.y0 - rad < py < bb.y1 + rad:
                extra.append(f"rótulo {t.get_text()!r} sobre o marcador de {nm!r}")
    for t in ax.texts:                                     # siglas sobre marcadores
        if len(t.get_text()) == 2 and t.get_text().isupper():
            bb = t.get_window_extent(r)
            for (px, py), nm in zip(xy, pts["NM_MUN"]):
                if bb.x0 - rad < px < bb.x1 + rad and bb.y0 - rad < py < bb.y1 + rad:
                    extra.append(f"sigla {t.get_text()!r} sobre o marcador de {nm!r}")

    name = "Figure_2_location"
    probs = auditar(fig, name + ".png", LOG)
    if extra:
        with open(LOG, "a", encoding="utf-8") as fh:
            for e in extra:
                fh.write(f"    - {e}\n")
    print(name, "| layout:", probs or "OK", "| marcadores:", extra or "OK")
    for ext in ("png", "svg"):
        path = os.path.join(FIG_DIR, f"{name}.{ext}")
        tmp = path + ".tmp." + ext
        fig.savefig(tmp, dpi=600, bbox_inches="tight", pad_inches=0.04)
        os.replace(tmp, path)
    plt.close(fig)
    return probs + extra


if __name__ == "__main__":
    main()
