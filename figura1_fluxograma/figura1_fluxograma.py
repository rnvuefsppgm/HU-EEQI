# -*- coding: utf-8 -*-
"""Figura 1: fluxograma metodológico do HU-EEQI v6 (dados de entrada, 1ª passagem com a pilha bruta,
calibração, 2ª passagem com o índice, preenchimento, tendências, síntese no domínio urbano e resultados),
com as análises de controle de qualidade e o material suplementar em que cada etapa é relatada.
Saída: figuras/Figure_1_workflow.png (600 dpi) e .svg (texto editável), 17,4 cm de largura.
Revisão automática: texto cortado/sobreposto (checar_layout) e texto que sai da própria caixa.
Uso: python figura1_fluxograma.py"""
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
sys.path.insert(0, V6)
sys.path.insert(0, os.path.join(V6, "mapas_anuais_filled"))
import figure_style as fs                                   # noqa: E402
from checar_layout import auditar                           # noqa: E402

CM, FS, FSS = fs.CM, fs.FS, fs.FS_SMALL
OUT = os.path.join(HERE, "figuras")
LOG = os.path.join(HERE, "revisao_layout.txt")
os.makedirs(OUT, exist_ok=True)

W, H = fs.WIDTH_CM, 22.75
XA = 10.9                      # conectores entre faixas: à direita dos títulos das faixas
fig = plt.figure(figsize=(W * CM, H * CM))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(H, 0)
ax.axis("off")

C_IN, C_P1, C_P2, C_TR, C_SY, C_RES, C_QC = ("#eef1f5", "#e2eef8", "#e6f2f1", "#fdf0de", "#e7f4e4",
                                             "#efe9f6", "#fffbe6")
E_IN, E_P1, E_P2, E_TR, E_SY, E_RES, E_QC = ("#5f6f84", "#2f6aa3", "#1f7a72", "#c0700f", "#3d8b37",
                                             "#6b4c9a", "#a8861f")
MX0, MX1 = 0.25, 11.75
QX0, QX1 = 12.05, 17.15
BOXES = []                     # (texto, caixa) para a checagem de transbordo


def box(x0, y0, x1, y1, title, body, fc, ec, dashed=False, tag=None, bsize=FSS):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.12",
                                fc=fc, ec=ec, lw=0.8, ls=(0, (3, 2)) if dashed else "-"))
    ty = y0 + 0.13
    if title:
        t = ax.text(x0 + 0.13, ty, title, fontsize=FSS + 0.5, fontweight="bold", va="top", ha="left",
                    color="#111111")
        BOXES.append((t, (x0, y0, x1, y1)))
        ty += 0.36 * (title.count("\n") + 1) + 0.03
    if body:
        t = ax.text(x0 + 0.13, ty, body, fontsize=bsize, va="top", ha="left", linespacing=1.22, color="#222222")
        BOXES.append((t, (x0, y0, x1, y1)))
    if tag:
        t = ax.text(x1 - 0.1, y1 - 0.08, tag, fontsize=FSS - 0.5, va="bottom", ha="right", color=ec,
                    fontweight="bold")
        BOXES.append((t, (x0, y0, x1, y1)))


def band(y0, y1, label, ec):
    ax.add_patch(FancyBboxPatch((0.08, y0), W - 0.16, y1 - y0, boxstyle="round,pad=0,rounding_size=0.15",
                                fc="none", ec=ec, lw=0.6))
    ax.text(0.22, y0 + 0.1, label, fontsize=FS, fontweight="bold", va="top", ha="left", color=ec)


def arrow(x0, y0, x1, y1, color="#333333", dashed=False, lw=0.9):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=7,
                                linestyle=(0, (3, 2)) if dashed else "-", shrinkA=0, shrinkB=0))


# ------------------------------------------------------------------------------ A. dados de entrada
band(0.1, 2.85, "A  Input data", E_IN)
iw = (W - 0.5 - 3 * 0.15) / 4
inputs = [
    ("Landsat C2 Level-2", "TM, ETM+, OLI, OLI-2 (30 m);\nQA cloud/shadow/saturation\nmasks; TM/ETM+ → OLI\n(Roy et al. 2016, OLS)"),
    ("Climate and aerosols", "ERA5-Land hourly 2-m air\nand dew-point temperature;\nMODIS MAIAC AOD 550 nm\n(best-quality retrievals)"),
    ("Population and income", "GHS-POP R2023A (100 m);\ngridded GDP per capita\n(admin-1); IBGE censuses\n(demographic indicators)"),
    ("Urban domain", "GHS-SMOD ≥ 21 in any epoch\n2000–2025, minus JRC GSW\nwater (occurrence ≥ 50%);\nIBGE municipal boundaries"),
]
for k, (t, b) in enumerate(inputs):
    x0 = 0.25 + k * (iw + 0.15)
    box(x0, 0.55, x0 + iw, 2.7, t, b, C_IN, E_IN)

# ------------------------------------------------------------------------------ B. 1ª passagem
band(3.0, 8.15, "B  Pass 1 — raw annual stack (GEE), 27 capitals × 2000–2025", E_P1)
ax.text((QX0 + QX1) / 2, 3.45, "Quality control and sensitivity", fontsize=FS, fontweight="bold",
        ha="center", va="top", color=E_QC)
arrow(XA, 2.7, XA, 3.5)
box(MX0, 3.5, MX1, 4.35, "B1  Annual median composite (calendar year)",
    "Pixel kept with ≥ 3 clear observations; ETM+ excluded when OLI is available (from 2013)", C_P1, E_P1)
desc = [("Greenness", "NDVI"), ("Wetness", "Tasseled-cap\nWET (OLI scale)"), ("Dryness", "NDBSI =\n(IBI + SI) / 2"),
        ("Heat", "Median daily max\nNWS heat index,\n12–16 h; coastal\ncells: 3×3 mean"),
        ("Air quality", "Median MAIAC\nAOD; < 10\nretrievals →\ncapital median")]
dw = (MX1 - MX0 - 4 * 0.12) / 5
for k, (t, b) in enumerate(desc):
    x0 = MX0 + k * (dw + 0.12)
    arrow(x0 + dw / 2, 4.35, x0 + dw / 2, 4.65)
    box(x0, 4.65, x0 + dw, 6.55, t, b, C_P1, E_P1, bsize=FSS - 0.3)
    arrow(x0 + dw / 2, 6.55, x0 + dw / 2, 6.8)
box(MX0, 6.8, MX1, 8.0, "B2  Masked stack per capital-year (asset HU-EEQI_v6_raw)",
    "Descriptors + population + vulnerability V = 1 − scaled GDP per capita; urban domain applied\n"
    "at the source; written once (2-km buffer for the focal window); land-surface temperature kept as diagnostic",
    C_P1, E_P1, bsize=FSS - 0.3)
box(QX0, 3.75, QX1, 8.0, "QC1  Calibration (frozen)",
    "280,385 urban-domain pixel-years\nsampled from the stack;\nbounds: pooled p1–p99;\n"
    "weights: CRITIC (95% CI from\n500 city-block bootstraps);\nentropy, PCA and equal\nweights as alternatives;\n"
    "saturation per year", C_QC, E_QC, dashed=True, tag="S3")
arrow(MX1, 7.4, QX0, 7.4, color=E_QC, dashed=True, lw=0.6)

# ------------------------------------------------------------------------------ C. 2ª passagem
band(8.3, 14.55, "C  Pass 2 — index per pixel and year (GEE, 30 m)", E_P2)
arrow(XA, 8.0, XA, 8.75)
box(MX0, 8.75, MX1, 9.95, "C1  Normalization with fixed pooled bounds",
    "NI = (x − p1)/(p99 − p1) (benefit: NDVI, WET) or (p99 − x)/(p99 − p1) (cost: NDBSI, heat, AOD);\n"
    "clamped to [0.01, 1]", C_P2, E_P2, bsize=FSS - 0.3)
arrow(6.0, 9.95, 6.0, 10.15)
cw = (MX1 - MX0 - 2 * 0.15) / 3
comp = [("C2  EQ", "Weighted geometric mean\nEQ = Π NIᵢ^wᵢ\n(CRITIC weights)"),
        ("C3  E_local", "Equity: 1 − CV of EQ in a\n2-km window weighted\nby population"),
        ("C4  J_local", "Justice: 1 − max(0, ρ),\nρ = corr(1 − EQ, V) in the\nsame weighted window")]
for k, (t, b) in enumerate(comp):
    x0 = MX0 + k * (cw + 0.15)
    box(x0, 10.15, x0 + cw, 11.6, t, b, C_P2, E_P2)
    arrow(x0 + cw / 2, 11.6, x0 + cw / 2, 11.8)
box(MX0, 11.8, MX1, 12.85, "C5  HU-EEQI = EQ^0.6 · E^0.2 · J^0.2  (0 = lowest, 1 = highest)",
    "If V is constant within the capital (J uninformative), γ is redistributed: EQ^0.75 · E^0.25", C_P2, E_P2)
arrow(6.0, 12.85, 6.0, 13.1)
box(MX0, 13.1, MX1, 14.4, "C6  Pixel-wise gap filling of all bands (asset HU-EEQI_v6_filled)",
    "(1) linear interpolation in time; (2) nearest observed year at the series ends;\n"
    "(3) 2-km window mean in the same year; (4) capital median; method flagged per pixel-year",
    C_P2, E_P2, bsize=FSS - 0.3)
box(QX0, 8.75, QX1, 10.6, "QC2  Reproducibility",
    "Index recomputed off-line\nfrom the exported descriptors;\nexact decomposition", C_QC, E_QC, dashed=True,
    tag="S7")
box(QX0, 10.8, QX1, 12.85, "QC3  Consistency and uncertainty",
    "Common-year signal, Pettitt\nbreaks, change decomposition;\nMonte Carlo on weights, α,\nβ/γ, bounds, floor",
    C_QC, E_QC, dashed=True, tag="S8, S9, S11")
box(QX0, 13.1, QX1, 14.4, "QC4  Completeness",
    "Observed and filled shares\nper capital-year and method", C_QC, E_QC, dashed=True, tag="S2")
arrow(MX1, 9.25, QX0, 9.7, color=E_QC, dashed=True, lw=0.6)
arrow(MX1, 12.3, QX0, 11.8, color=E_QC, dashed=True, lw=0.6)
arrow(MX1, 13.75, QX0, 13.75, color=E_QC, dashed=True, lw=0.6)

# ------------------------------------------------------------------------------ D. tendências
band(14.7, 17.0, "D  Pixel-wise trends of the gap-filled series (GEE)", E_TR)
arrow(XA, 14.4, XA, 15.15)
box(MX0, 15.15, MX1, 16.85, "D1  Mann–Kendall family and Sen's slope (26 annual values per pixel)",
    "Original and tie-corrected MK; Hamed–Rao variance correction (principal test, α = 0.05);\n"
    "TFPW; Kendall's τ, Sen's slope; temporal mean, median and standard deviation", C_TR, E_TR)
box(QX0, 15.15, QX1, 16.85, "QC5  Robustness of trends",
    "Four tests on all pixels; lag-1\nautocorrelation; MapBiomas\nland-cover falsification test",
    C_QC, E_QC, dashed=True, tag="S5, S10")
arrow(MX1, 16.0, QX0, 16.0, color=E_QC, dashed=True, lw=0.6)

# ------------------------------------------------------------------------------ E. síntese
band(17.15, 19.95, "E  Synthesis within the urban domain (Python)", E_SY)
arrow(XA, 16.85, XA, 17.6)
box(MX0, 17.6, 4.05, 19.8, "E1  Trend classes",
    "Sign of τ; Hamed–Rao\np ≤ 0.05: significant\ndegradation / improvement\n(*MK ties if series incomplete)",
    C_SY, E_SY, bsize=FSS - 0.3)
box(4.25, 17.6, 7.9, 19.8, "E2  Variability classes",
    "Temporal SD:\n< 0.05 low,\n0.05–0.10 moderate,\n> 0.10 high", C_SY, E_SY)
box(8.1, 17.6, MX1, 19.8, "E3  Municipal series",
    "Annual urban-domain mean;\nMK, Hamed–Rao and\nSen's slope per capital", C_SY, E_SY)
arrow(4.05, 18.7, 4.25, 18.7)
arrow(7.9, 18.7, 8.1, 18.7)
box(QX0, 17.6, QX1, 19.8, "E4  Area accounting",
    "Share of the urban domain in\neach class, by capital and\nmacro-region (30 m)", C_SY, E_SY,
    tag="Table 1, S4")
arrow(MX1, 18.7, QX0, 18.7, color=E_SY)

# ------------------------------------------------------------------------------ F. resultados
band(20.1, 22.6, "F  Results", E_RES)
arrow(XA, 19.8, XA, 20.55)
box(MX0, 20.55, 5.9, 22.45, "Trend and variability maps",
    "Five panels per capital\n(Figures 3–11); annual\nHU-EEQI maps (S1)", C_RES, E_RES)
box(6.1, 20.55, MX1, 22.45, "Regional comparison",
    "27 capitals and five\nmacro-regions; municipal\nseries (S4)", C_RES, E_RES)
box(QX0, 20.55, QX1, 22.45, "Exploratory association",
    "Spearman ρ between trend-class\nshares and density / growth\n(n = 27; non-causal)", C_RES, E_RES,
    tag="S6")
arrow(QX0 + 2.5, 19.8, QX0 + 2.5, 20.55, color=E_SY)

# ------------------------------------------------------------------------------ revisão e gravação
fig.canvas.draw()
r = fig.canvas.get_renderer()
inv = ax.transData.inverted()
extra = []
for t, (x0, y0, x1, y1) in BOXES:
    bb = t.get_window_extent(r)
    (a0, b0), (a1, b1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
    if a0 < x0 - 0.02 or a1 > x1 + 0.02 or min(b0, b1) < y0 - 0.02 or max(b0, b1) > y1 + 0.02:
        extra.append(f"texto sai da caixa: {t.get_text()[:45]!r}")
if os.path.exists(LOG):
    os.remove(LOG)
probs = auditar(fig, "Figure_1_workflow.png", LOG, tight=False)
if extra:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.writelines(f"    - {e}\n" for e in extra)
print("layout:", probs or "OK", "| caixas:", extra or "OK")
for ext in ("png", "svg"):
    p = os.path.join(OUT, f"Figure_1_workflow.{ext}")
    fig.savefig(p + ".tmp." + ext, dpi=600)
    os.replace(p + ".tmp." + ext, p)
plt.close(fig)
