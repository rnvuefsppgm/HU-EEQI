# -*- coding: utf-8 -*-
"""
Material suplementar do notebook 03 (HU-EEQI v6): consistência temporal, decomposição, teste de
falsificação com MapBiomas e incerteza/sensibilidade. Roda FORA do Colab sobre o painel exportado
(dados/panel_v6.csv) e a calibração (dados/calibration_v6.json), reaproveitando a configuração e as
funções de análise do próprio notebook 03 (lidas do .ipynb, sem cópia).
Saídas: figuras/ (PNG 600 dpi), tabelas/ (CSV + XLSX) e documentos/ (um .docx por análise).
Uso: python gerar_material_suplementar_03.py
"""
import os
import json
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import docx
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ---- revisão automática de layout + salvamento sem cortar texto () ----
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checar_layout import auditar
LAYOUT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "revisao_layout.txt")
open(LAYOUT_LOG, "w", encoding="utf-8").close()


def salvar(fig, path, **kw):
    auditar(fig, os.path.basename(path), LAYOUT_LOG)
    kw.setdefault("bbox_inches", "tight")
    kw.setdefault("pad_inches", 0.04)
    tmp = path + ".tmp" + os.path.splitext(path)[1]   # grava num temporário e troca (arquivo aberto em outro programa)
    fig.savefig(tmp, **kw)
    for _k in range(10):
        try:
            os.replace(tmp, path); break
        except OSError:
            import time as _t; _t.sleep(3)
    else:
        print("AVISO: não consegui substituir", path, "(arquivo aberto?) -> nova versão em", tmp, flush=True)


HERE = os.path.dirname(os.path.abspath(__file__))
NB03 = os.path.join(HERE, "..", "colab", "03_HU-EEQI_sensibilidade_diagnostico_v6.ipynb")
FIG, TAB, DOC = (os.path.join(HERE, d) for d in ("figuras", "tabelas", "documentos"))
for d in (FIG, TAB, DOC):
    os.makedirs(d, exist_ok=True)
DPI = 600
plt.rcParams.update({"font.family": "Arial", "font.size": 8, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6})

# ---- configuração e funções de análise do notebook 03 (células 1 e 7) -------------------------------
cells = ["".join(c["source"]) for c in json.load(open(NB03, encoding="utf-8"))["cells"]]
G = {}
exec(cells[1], G)                      # Configuração HU-EEQI v6 (constantes)
exec(cells[7], G)                      # Funções de análise (numpy/pandas)
globals().update({k: v for k, v in G.items() if not k.startswith("__")})
MC_DRAWS, MC_SEED = 500, 42            # célula 4 do notebook

# ---- dados -------------------------------------------------------------------------------------------
df = pd.read_csv(os.path.join(HERE, "dados", "panel_v6.csv"))
n_raw = len(df)
df = df.replace([np.inf, -np.inf, -9999], np.nan).dropna(subset=["HU_EEQI"] + DESCRIPTORS)
df["year"] = df["year"].astype(int)
CALIB = json.load(open(os.path.join(HERE, "dados", "calibration_v6.json"), encoding="utf-8"))
BOUNDS, WEIGHTS = CALIB["bounds"], CALIB["weights_all"][WEIGHT_METHOD]
CITIES = sorted(df.city.unique())
YRS = np.array(sorted(df.year.unique()))
cc = pd.Categorical(df.city, categories=CITIES).codes
yc = np.searchsorted(YRS, df.year.to_numpy())
NC, NY = len(CITIES), len(YRS)
JDEG = sorted(df.loc[df.j_valid == 0, "city"].unique())
JVAL = sorted(set(CITIES) - set(JDEG))
INFO = {"rows_raw": n_raw, "rows": len(df), "pixels": df.pid.nunique(), "cities": NC, "years": NY,
        "y0": int(YRS.min()), "y1": int(YRS.max()), "j_degenerate": len(JDEG)}
print(INFO, flush=True)

LABEL = {"HU_EEQI": "HU-EEQI", "EQ": "EQ", "E_local": "E (local equity)", "J_local": "J (local justice)",
         "NI_NDVI": "NDVI", "NI_Wet": "Wetness", "NI_NDBSI": "NDBSI", "NI_HEAT": "Heat index",
         "NI_AQ": "AOD (air quality)", "lnHU": "ln HU-EEQI"}


def save_table(t, name, index=True):
    t.to_csv(os.path.join(TAB, f"{name}.csv"), index=index, encoding="utf-8")
    t.to_excel(os.path.join(TAB, f"{name}.xlsx"), index=index)
    return t


def save_fig(fig, name):
    p = os.path.join(FIG, f"{name}.png")
    salvar(fig, p, dpi=DPI, )
    plt.close(fig)
    return p


# =====================================================================================================
# S2 — Reprodutibilidade: índice recalculado == índice exportado; decomposição exata
# =====================================================================================================
hu0, eq0 = compute_hu(df, BOUNDS, WEIGHTS, ALPHA, BETA, GAMMA, NI_FLOOR, "geo")
dhu = np.abs(hu0 - df.HU_EEQI.to_numpy())
deq = np.abs(eq0 - df.EQ.to_numpy())
lnsum = log_contributions(df, WEIGHTS, ALPHA, BETA, GAMMA).sum(axis=1)
dln = np.abs(np.log(df.HU_EEQI.clip(lower=1e-6)) - lnsum)
s2 = save_table(pd.DataFrame([
    {"Check": "HU-EEQI recomputed vs exported", "Max |difference|": dhu.max(), "Median |difference|": np.median(dhu),
     "Pearson r": np.corrcoef(hu0, df.HU_EEQI)[0, 1]},
    {"Check": "EQ recomputed vs exported", "Max |difference|": deq.max(), "Median |difference|": np.median(deq),
     "Pearson r": np.corrcoef(eq0, df.EQ)[0, 1]},
    {"Check": "ln HU-EEQI vs sum of log-contributions", "Max |difference|": dln.max(),
     "Median |difference|": np.median(dln), "Pearson r": np.corrcoef(np.log(df.HU_EEQI.clip(lower=1e-6)), lnsum)[0, 1]},
]), "TableS2_1_reproducibility", index=False)
fig, axs = plt.subplots(1, 2, figsize=(17.4 / 2.54, 7.5 / 2.54))
idx = np.random.default_rng(1).choice(len(df), min(20000, len(df)), replace=False)
axs[0].scatter(df.HU_EEQI.to_numpy()[idx], hu0[idx], s=1, alpha=0.3, color="#2c7fb8", rasterized=True)
axs[0].plot([0, 1], [0, 1], color="k", lw=0.6); axs[0].set_xlabel("HU-EEQI exported (GEE)")
axs[0].set_ylabel("HU-EEQI recomputed (Python)"); axs[0].set_title("a) Index", loc="left")
axs[1].hist(np.log10(np.clip(dhu, 1e-12, None)), bins=60, color="#2c7fb8")
axs[1].set_xlabel("log10 |recomputed − exported|"); axs[1].set_ylabel("Pixel-years"); axs[1].set_title("b) Absolute difference", loc="left")
for a in axs:
    a.spines[["top", "right"]].set_visible(False)
f_s2 = save_fig(fig, "FigureS2_1_reproducibility")
print("S2 ok", flush=True)

# =====================================================================================================
# S3 — Consistência temporal: sinal comum do ano e quebras estruturais (Pettitt)
# =====================================================================================================
COMP = ["HU_EEQI", "EQ", "E_local", "J_local"] + [f"NI_{d}" for d in DESCRIPTORS]
MATS = {c: city_year_matrix(df[c].to_numpy(float), cc, yc, NC, NY) for c in COMP}
share = pd.Series({LABEL[c]: year_effect_share(M) for c, M in MATS.items()}, name="Year-effect share")
s3a = save_table(share.to_frame(), "TableS3_1_common_year_signal")
fig, axes = plt.subplots(2, 5, figsize=(17.4 / 2.54, 8.5 / 2.54), sharex=True)
for ax, c in zip(axes.flat, COMP):
    M = MATS[c]
    R = M - np.nanmean(M, axis=1, keepdims=True)
    ax.plot(YRS, R.T, color="0.8", lw=0.4)
    ax.plot(YRS, np.nanmedian(R, axis=0), color="crimson", lw=1.2)
    ax.axvspan(2011.5, 2013.5, color="orange", alpha=0.18, lw=0)
    ax.axhline(0, color="k", lw=0.4)
    ax.set_title(LABEL[c], fontsize=7)
    ax.tick_params(labelsize=6)
    ax.spines[["top", "right"]].set_visible(False)
for ax in axes[1]:
    ax.set_xticks([2000, 2010, 2020])
for ax in axes.flat[len(COMP):]:
    ax.set_visible(False)
fig.supylabel("Anomaly (city median − city mean)", fontsize=7)
fig.tight_layout()
f_s3 = save_fig(fig, "FigureS3_1_common_year_signal")
rows = []
for c in COMP:
    for i, city in enumerate(CITIES):
        yr, p = pettitt(YRS, MATS[c][i])
        rows.append({"Variable": LABEL[c], "City": city, "Break year": yr, "p": p})
pt = pd.DataFrame(rows)
pt["Significant (p<0.05)"] = pt.p < 0.05
pt["Break in 2012–2014"] = pt["Significant (p<0.05)"] & pt["Break year"].between(2012, 2014)
save_table(pt, "TableS3_3_pettitt_by_city", index=False)
s3b = save_table(pt.groupby("Variable", sort=False)[["Significant (p<0.05)", "Break in 2012–2014"]].sum()
                 .astype(int).rename(columns={"Significant (p<0.05)": "Cities with significant break",
                                              "Break in 2012–2014": "Of which in 2012–2014"}),
                 "TableS3_2_pettitt_summary")
fig, ax = plt.subplots(figsize=(17.4 / 2.54, 6 / 2.54))
sig = pt[pt["Significant (p<0.05)"]]
order = [LABEL[c] for c in COMP]
cnt = sig.groupby(["Variable", "Break year"]).size().unstack(0).reindex(index=YRS, columns=order).fillna(0)
bottom = np.zeros(len(YRS))
cmap = plt.get_cmap("tab10")
for k, c in enumerate(order):
    ax.bar(YRS, cnt[c].to_numpy(), bottom=bottom, color=cmap(k), width=0.8, label=c)
    bottom += cnt[c].to_numpy()
ax.axvspan(2011.5, 2013.5, color="orange", alpha=0.18, lw=0)
ax.set_xlabel("First year of the new regime (Pettitt)"); ax.set_ylabel("City × variable breaks (p<0.05)")
ax.legend(fontsize=6, ncol=2, frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
f_s3b = save_fig(fig, "FigureS3_2_pettitt_break_years")
print("S3 ok", flush=True)

# =====================================================================================================
# S4 — Decomposição exata de Δ ln HU-EEQI
# =====================================================================================================
C = log_contributions(df, WEIGHTS, ALPHA, BETA, GAMMA)
C["lnHU"] = C.sum(axis=1)
C[["pid", "city", "year"]] = df[["pid", "city", "year"]]
C = C.sort_values(["pid", "year"])
parts = [c for c in C.columns if c.startswith(("NI_", "E_", "J_"))]
D = C.groupby("pid")[parts + ["lnHU", "year"]].diff()
D[["pid", "city"]] = C[["pid", "city"]]
D = D[D.year == 1].drop(columns="year")


def var_shares(g):
    v = g["lnHU"].var()
    return pd.Series({p: g[p].cov(g["lnHU"]) / v for p in parts}) if v > 0 else pd.Series(dtype=float)


shares = D.groupby("city")[parts + ["lnHU"]].apply(var_shares)
shares.loc["All capitals"] = var_shares(D)
s4a = save_table(shares.rename(columns=LABEL), "TableS4_1_interannual_variance_shares")
fig, ax = plt.subplots(figsize=(17.4 / 2.54, 12 / 2.54))
sh = shares.rename(columns=LABEL)
left_p, left_n = np.zeros(len(sh)), np.zeros(len(sh))
for k, c in enumerate(sh.columns):
    v = sh[c].to_numpy()
    ax.barh(np.arange(len(sh)), np.where(v > 0, v, 0), left=left_p, color=cmap(k), label=c, height=0.75)
    ax.barh(np.arange(len(sh)), np.where(v < 0, v, 0), left=left_n, color=cmap(k), height=0.75)
    left_p += np.where(v > 0, v, 0); left_n += np.where(v < 0, v, 0)
ax.set_yticks(np.arange(len(sh))); ax.set_yticklabels(sh.index, fontsize=6.5); ax.invert_yaxis()
ax.axvline(0, color="k", lw=0.5)
ax.set_xlabel("Share of the variance of Δ ln HU-EEQI (consecutive years)")
ax.legend(fontsize=6.5, frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
f_s4 = save_fig(fig, "FigureS4_1_interannual_variance_shares")
y0, y1 = int(YRS.min()), int(YRS.max())
a_ = C[C.year == y0].set_index("pid"); b_ = C[C.year == y1].set_index("pid")
common = a_.index.intersection(b_.index)
delta = b_.loc[common, parts + ["lnHU"]] - a_.loc[common, parts + ["lnHU"]]
delta["city"] = a_.loc[common, "city"]
tot = delta.groupby("city").mean()
tot["n_pixels"] = delta.groupby("city").size()
s4b = save_table(tot[["lnHU"] + parts + ["n_pixels"]].rename(columns=LABEL), f"TableS4_2_change_{y0}_{y1}")
fig, ax = plt.subplots(figsize=(17.4 / 2.54, 12 / 2.54))
tt = tot[parts].rename(columns=LABEL)
lp, ln_ = np.zeros(len(tt)), np.zeros(len(tt))
for k, c in enumerate(tt.columns):
    v = tt[c].to_numpy()
    ax.barh(np.arange(len(tt)), np.where(v > 0, v, 0), left=lp, color=cmap(k), label=c, height=0.75)
    ax.barh(np.arange(len(tt)), np.where(v < 0, v, 0), left=ln_, color=cmap(k), height=0.75)
    lp += np.where(v > 0, v, 0); ln_ += np.where(v < 0, v, 0)
ax.scatter(tot["lnHU"], np.arange(len(tt)), color="k", s=8, zorder=3, label="Δ ln HU-EEQI (total)")
ax.set_yticks(np.arange(len(tt))); ax.set_yticklabels(tt.index, fontsize=6.5); ax.invert_yaxis()
ax.axvline(0, color="k", lw=0.5)
ax.set_xlabel(f"Mean change {y0}→{y1} in ln HU-EEQI and contributions (positive = improvement)")
ax.legend(fontsize=6.5, frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
f_s4b = save_fig(fig, f"FigureS4_2_change_{y0}_{y1}")
print("S4 ok", flush=True)

# =====================================================================================================
# S5 — Falsificação com MapBiomas (pixels estáveis vs. que mudaram de classe)
# =====================================================================================================
P = df.pivot_table(index="pid", columns="year", values="HU_EEQI").reindex(columns=YRS)
meta = df.drop_duplicates("pid").set_index("pid")[["city", "mb_stable", "mb_first", "mb_last"]]
slope = sen_slope(YRS, P.to_numpy())
pval = mk_p(P.to_numpy())
nobs = P.notna().sum(axis=1).to_numpy()
res = meta.loc[P.index].assign(slope=slope, p=pval, sig=pval < 0.05, n_years=nobs)
res["group"] = np.where(res.mb_stable == 1, "Stable land cover", "Land-cover change")
save_table(res, "TableS5_2_pixel_trends_mapbiomas")
summ = res.groupby("group").agg(n_pixels=("slope", "size"), median_slope=("slope", "median"),
                                median_abs_slope=("slope", lambda s: s.abs().median()),
                                pct_significant=("sig", "mean"))
summ["pct_significant"] *= 100
s5 = save_table(summ, "TableS5_1_falsification_summary")
by_city = res.groupby(["city", "group"]).agg(n=("slope", "size"), median_slope=("slope", "median"),
                                             pct_sig=("sig", "mean")).unstack("group")
save_table(by_city, "TableS5_3_falsification_by_city")
fig, axs = plt.subplots(1, 2, figsize=(17.4 / 2.54, 7 / 2.54))
grp = ["Stable land cover", "Land-cover change"]
data = [res.loc[res.group == g, "slope"].dropna().to_numpy() for g in grp]
lo_, hi_ = np.nanpercentile(np.concatenate(data), [1, 99])
for g, d_, col in zip(grp, data, ["#1b9e77", "#d95f02"]):
    axs[0].hist(np.clip(d_, lo_, hi_), bins=60, range=(lo_, hi_), density=True, alpha=0.55, color=col, label=f"{g} (n={len(d_)})")
axs[0].axvline(0, color="k", lw=0.5); axs[0].set_xlabel("Sen slope of HU-EEQI (yr⁻¹)"); axs[0].set_ylabel("Density")
axs[0].legend(fontsize=6, frameon=False); axs[0].set_title("a) Distribution of pixel trends", loc="left")
axs[1].bar(grp, summ.loc[grp, "pct_significant"], color=["#1b9e77", "#d95f02"])
axs[1].set_ylabel("Pixels with significant trend (%)"); axs[1].set_title("b) Mann–Kendall p < 0.05", loc="left")
axs[1].tick_params(axis="x", labelsize=6.5)
for a in axs:
    a.spines[["top", "right"]].set_visible(False)
f_s5 = save_fig(fig, "FigureS5_1_falsification_mapbiomas")
print("S5 ok", flush=True)

# =====================================================================================================
# S6 — Incerteza e sensibilidade (Monte Carlo; OECD/JRC 2008; Saisana et al. 2005)
# =====================================================================================================
rng = np.random.default_rng(MC_SEED)
WSETS, BSETS = CALIB["weights_all"], CALIB["bounds_by_pct"]
hu_b, _ = compute_hu(df, BOUNDS, WEIGHTS, ALPHA, BETA, GAMMA, NI_FLOOR, "geo")
M0 = city_year_matrix(hu_b, cc, yc, NC, NY)
S0 = sen_slope(YRS, M0)
fac, Ms = [], []
for k in range(MC_DRAWS):
    f = {"wset": rng.choice(list(WSETS)), "alpha": rng.uniform(0.4, 0.8),
         "split_beta": rng.uniform(0.25, 0.75), "bset": rng.choice(list(BSETS)),
         "floor": rng.choice([0.01, 0.05]), "agg": rng.choice(["geo", "arith"])}
    beta = (1 - f["alpha"]) * f["split_beta"]
    gamma = (1 - f["alpha"]) - beta
    hu, _ = compute_hu(df, BSETS[f["bset"]], WSETS[f["wset"]], f["alpha"], beta, gamma, f["floor"], f["agg"])
    Ms.append(city_year_matrix(hu, cc, yc, NC, NY))
    fac.append(f)
    if (k + 1) % 100 == 0:
        print(f"  Monte Carlo {k + 1}/{MC_DRAWS}", flush=True)
Ms = np.array(Ms)
F = pd.DataFrame(fac)
save_table(F, "TableS6_5_monte_carlo_draws", index=False)


def ranks(M):
    return pd.DataFrame(M).rank(ascending=False, axis=0).to_numpy()


R0 = ranks(M0)
Rk = np.array([ranks(M) for M in Ms])
spear = np.array([[spearman(M0[:, t], Ms[d][:, t]) for t in range(NY)] for d in range(MC_DRAWS)])
s6a = save_table(pd.DataFrame({"Median": np.nanmedian(spear, 0), "P5": np.nanpercentile(spear, 5, 0),
                               "P95": np.nanpercentile(spear, 95, 0)}, index=pd.Index(YRS, name="Year")),
                 "TableS6_1_rank_spearman_by_year")
Sd = sen_slope(YRS, Ms)
city_tab = pd.DataFrame({
    "Mean rank (base)": np.nanmean(R0, 1),
    "Mean rank P5": np.nanpercentile(Rk.mean(2), 5, 0), "Mean rank P95": np.nanpercentile(Rk.mean(2), 95, 0),
    "Sen slope (base)": S0, "Sen slope P5": np.nanpercentile(Sd, 5, 0), "Sen slope P95": np.nanpercentile(Sd, 95, 0),
    "Sign agreement (%)": 100 * np.nanmean(np.sign(Sd) == np.sign(S0)[None, :], 0),
}, index=pd.Index(CITIES, name="City"))
s6b = save_table(city_tab, "TableS6_2_city_rank_and_trend_uncertainty")
FACTORS = ["wset", "alpha", "split_beta", "bset", "floor", "agg"]
FLAB = {"wset": "Weighting scheme", "alpha": "α (EQ exponent)", "split_beta": "β/γ split",
        "bset": "Normalization bounds", "floor": "NI floor", "agg": "Aggregation (geo/arith)"}
Smean = np.nanmean(Ms, axis=2)
sens = {}
for nome, Y, fn in [("Trend (Sen slope)", Sd, "TableS6_3_sensitivity_trend_by_city"),
                    ("Mean level", Smean, "TableS6_4_sensitivity_level_by_city")]:
    tab = pd.DataFrame({FLAB[fct]: [first_order_index(Y[:, c], F[fct].to_numpy()) for c in range(NC)]
                        for fct in FACTORS}, index=pd.Index(CITIES, name="City"))
    save_table(tab, fn)
    sens[nome] = tab.median()
s6c = save_table(pd.DataFrame(sens), "TableS6_0_first_order_sensitivity_median")
# figuras
fig, ax = plt.subplots(figsize=(17.4 / 2.54, 6.5 / 2.54))
s6c.plot.bar(ax=ax, color=["#7570b3", "#e7298a"], width=0.75)
ax.set_ylabel("First-order index Sᵢ (median across capitals)"); ax.set_xlabel("")
ax.tick_params(axis="x", rotation=25, labelsize=6.5); ax.legend(fontsize=6.5, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
f_s6a = save_fig(fig, "FigureS6_1_first_order_sensitivity")
fig, axs = plt.subplots(1, 2, figsize=(17.4 / 2.54, 11 / 2.54), sharey=True)
o = city_tab.sort_values("Mean rank (base)").index
yy = np.arange(len(o))
ct = city_tab.loc[o]
axs[0].errorbar(ct["Mean rank (base)"], yy, xerr=[ct["Mean rank (base)"] - ct["Mean rank P5"], ct["Mean rank P95"] - ct["Mean rank (base)"]],
                fmt="o", ms=3, color="#2c7fb8", ecolor="0.5", elinewidth=0.8, capsize=1.5)
axs[0].set_yticks(yy); axs[0].set_yticklabels(o, fontsize=6.5); axs[0].invert_yaxis()
axs[0].set_xlabel("Mean rank 2000–2025 (1 = best)"); axs[0].set_title("a) Ranking", loc="left")
axs[1].errorbar(ct["Sen slope (base)"] * 10, yy, xerr=[(ct["Sen slope (base)"] - ct["Sen slope P5"]) * 10, (ct["Sen slope P95"] - ct["Sen slope (base)"]) * 10],
                fmt="o", ms=3, color="#d95f02", ecolor="0.5", elinewidth=0.8, capsize=1.5)
axs[1].axvline(0, color="k", lw=0.5); axs[1].set_xlabel("Sen slope of the city median (per decade)")
axs[1].set_title("b) Trend", loc="left")
for a in axs:
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
f_s6b = save_fig(fig, "FigureS6_2_rank_and_trend_uncertainty")
fig, ax = plt.subplots(figsize=(17.4 / 2.54, 5.5 / 2.54))
ax.fill_between(YRS, s6a["P5"], s6a["P95"], color="#2c7fb8", alpha=0.25, lw=0, label="P5–P95")
ax.plot(YRS, s6a["Median"], color="#2c7fb8", lw=1.2, label="Median")
ax.set_ylim(min(0.5, float(s6a["P5"].min()) - 0.05), 1.0)
ax.set_xlabel("Year"); ax.set_ylabel("Spearman ρ (ranking vs base)"); ax.legend(fontsize=6.5, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
f_s6c = save_fig(fig, "FigureS6_3_rank_spearman_by_year")
print("S6 ok", flush=True)

# =====================================================================================================
# Documentos .docx (um por análise)
# =====================================================================================================
def new_doc(title):
    D = docx.Document()
    st = D.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
    s = D.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.left_margin = s.right_margin = Cm(2.0); s.top_margin = s.bottom_margin = Cm(2.0)
    D.add_heading(title, 1)
    return D


def para(D, text, bold_lead=None, size=10):
    p = D.add_paragraph()
    if bold_lead:
        r = p.add_run(bold_lead); r.bold = True; r.font.size = Pt(size)
    r = p.add_run(text); r.font.size = Pt(size)
    return p


def figure(D, path, label, caption, width=16.5):
    D.add_picture(path, width=Cm(width))
    D.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    para(D, caption, f"{label}. ", size=9)


def table(D, t, label, caption, fmt="{:.3f}", index=True, max_rows=40):
    para(D, caption, f"{label}. ", size=9)
    t = t.copy()
    if index:
        t = t.reset_index()
    t = t.head(max_rows)
    tb = D.add_table(rows=1, cols=len(t.columns))
    tb.style = "Light Grid Accent 1"
    for j, c in enumerate(t.columns):
        tb.rows[0].cells[j].text = str(c)
    for _, row in t.iterrows():
        cells_ = tb.add_row().cells
        for j, v in enumerate(row):
            if isinstance(v, (float, np.floating)):
                txt = "" if not np.isfinite(v) else (f"{v:.2e}" if (abs(v) < 1e-3 and v != 0) else fmt.format(v))
            else:
                txt = str(v)
            cells_[j].text = txt
    for r_ in tb.rows:
        for c_ in r_.cells:
            for p_ in c_.paragraphs:
                for run in p_.runs:
                    run.font.size = Pt(7.5)
    D.add_paragraph()


COMMON = (f"All analyses use the fixed pixel panel of notebook 03: {INFO['pixels']:,} pixels "
          f"({N_PANEL_PER_CITY} per capital, stratified within the fixed urban domain, the same pixels in every year) "
          f"in {INFO['cities']} capitals, {INFO['y0']}–{INFO['y1']}, taken from the OBSERVED (not gap-filled) HU-EEQI v6 "
          f"series; {INFO['rows']:,} pixel-years with the index and all five descriptors. "
          f"Index: HU-EEQI = EQ^{ALPHA}·E^{BETA}·J^{GAMMA}, EQ = {WEIGHT_METHOD.upper()}-weighted geometric mean of the "
          f"normalized descriptors (bounds p{BOUNDS_PCT[0]}–p{BOUNDS_PCT[1]} pooled over capitals and years). "
          f"With the state-level GDP proxy used for vulnerability (V_SOURCE = '{V_SOURCE}'), V is constant within "
          f"{INFO['j_degenerate']} of the {INFO['cities']} capitals (j_valid = 0): there J carries no information, J_local = 1 "
          f"and its exponent is redistributed to EQ and E ({J_FALLBACK}), so J contributes zero. In {', '.join(JVAL)}, "
          "the municipal polygon reaches pixels of a neighbouring state, so V varies along the state border and the "
          "degeneracy test marks J as informative (j_valid = 1); in these capitals J reflects the GDP difference between "
          "states at the border rather than intra-urban vulnerability and should be interpreted with caution.")

# S2
D = new_doc("Supplementary Material S2. Reproducibility of the HU-EEQI computation")
para(D, "To verify that the index stored in the Earth Engine assets can be reproduced independently, the HU-EEQI "
        "was recomputed in Python from the raw descriptors, the calibration file (bounds and weights) and the exported "
        "E and J layers of each panel pixel, and compared with the exported value. The additive log-decomposition used in "
        "Supplementary Material S4 was also checked against ln HU-EEQI.", "Objective and method. ")
para(D, COMMON, "Data. ")
r = s2.set_index("Check")
para(D, f"The recomputed index matches the exported one with a maximum absolute difference of "
        f"{r.loc['HU-EEQI recomputed vs exported', 'Max |difference|']:.2e} (median "
        f"{r.loc['HU-EEQI recomputed vs exported', 'Median |difference|']:.2e}; r = "
        f"{r.loc['HU-EEQI recomputed vs exported', 'Pearson r']:.6f}). The sum of the log-contributions reproduces "
        f"ln HU-EEQI to within {r.loc['ln HU-EEQI vs sum of log-contributions', 'Max |difference|']:.2e}. Differences are "
        "at the level of single-precision (float32) storage.", "Results. ")
table(D, s2, "Table S2.1", "Agreement between the exported and the recomputed index (all panel pixel-years).", fmt="{:.6f}", index=False)
figure(D, f_s2, "Figure S2.1", "Reproducibility check. (a) Exported versus recomputed HU-EEQI (random sample of 20,000 "
       "pixel-years; line = 1:1). (b) Distribution of the absolute differences (log10).")
D.save(os.path.join(DOC, "S2_Reproducibility_check.docx"))

# S3
D = new_doc("Supplementary Material S3. Temporal consistency: common year signal and structural breaks")
para(D, "Year-to-year variations shared by all capitals point to regional climate or to sensor effects rather than "
        "to local change. For each variable, the city-year medians were centred on each city's mean, and the share of the "
        "remaining variance explained by a common year effect was computed. Structural breaks in each city's series were "
        "located with the Pettitt test (p < 0.05), with attention to 2012–2014, when the Landsat record switches from "
        "TM/ETM+ to OLI (harmonized with Roy et al., 2016).", "Objective and method. ")
para(D, COMMON, "Data. ")
hi = share.drop(LABEL["J_local"]).sort_values(ascending=False)
para(D, f"The common year effect explains {share[LABEL['HU_EEQI']]:.0%} of the interannual variance of the city "
        f"medians of HU-EEQI. Among the components, it is highest for {hi.index[0]} ({hi.iloc[0]:.0%}) and "
        f"{hi.index[1]} ({hi.iloc[1]:.0%}) and lowest for {hi.index[-1]} ({hi.iloc[-1]:.0%}). Significant Pettitt breaks "
        f"in HU-EEQI occur in {int(s3b.loc[LABEL['HU_EEQI'], 'Cities with significant break'])} of {NC} capitals, "
        f"{int(s3b.loc[LABEL['HU_EEQI'], 'Of which in 2012–2014'])} of them in 2012–2014. "
        f"The equity component E shows the strongest common year signal ({share[LABEL['E_local']]:.0%}) and breaks in "
        f"{int(s3b.loc[LABEL['E_local'], 'Cities with significant break'])} capitals, "
        f"{int(s3b.loc[LABEL['E_local'], 'Of which in 2012–2014'])} of them in 2012–2014, consistent with the change in "
        "local texture introduced by the Landsat 7 SLC-off gaps and the transition to OLI (E measures the local dispersion "
        "of EQ). J has no common year variance and no significant break (see Data).", "Results. ")
table(D, s3a, "Table S3.1", "Share of the interannual variance of city medians explained by a year effect common to all capitals (high values indicate climate- or sensor-driven variation).")
table(D, s3b, "Table S3.2", f"Number of capitals with a significant Pettitt break (p < 0.05) per variable and how many fall in 2012–2014 (n = {NC} capitals). Per-city break years and p-values: TableS3_3_pettitt_by_city.csv.", fmt="{:.0f}")
figure(D, f_s3, "Figure S3.1", "City anomalies (grey; city-year median minus city mean) and common year signal (red; median across capitals) for HU-EEQI, its components and the normalized descriptors. Orange band: 2012–2013 sensor transition (TM/ETM+ to OLI).")
figure(D, f_s3b, "Figure S3.2", "Year of the significant Pettitt breaks (first year of the new regime), stacked by variable. Orange band: 2012–2013 sensor transition.")
D.save(os.path.join(DOC, "S3_Temporal_consistency_common_signal_breaks.docx"))

# S4
D = new_doc("Supplementary Material S4. Exact decomposition of HU-EEQI changes")
para(D, "Because the HU-EEQI is a weighted geometric mean, ln HU-EEQI is exactly the sum of the weighted logarithms of "
        "its parts (five normalized descriptors within EQ, E and J). Two decompositions are reported: (i) the share of the "
        "variance of year-to-year changes (Δ ln HU-EEQI between consecutive years, same pixel) attributable to each part, "
        "computed as cov(Δpart, Δln HU)/var(Δln HU), which sums to one; and (ii) the mean change between the first and last "
        f"years ({y0}→{y1}) for pixels present in both years, split into the same parts.", "Objective and method. ")
para(D, COMMON, "Data. ")
al = shares.loc["All capitals"].rename(LABEL).sort_values(ascending=False)
imp = (tot["lnHU"] > 0).sum()
para(D, f"Pooling all capitals, year-to-year changes in HU-EEQI are driven mainly by {al.index[0]} ({al.iloc[0]:.0%} of "
        f"the variance) and {al.index[1]} ({al.iloc[1]:.0%}), followed by {al.index[2]} ({al.iloc[2]:.0%}). Between {y0} "
        f"and {y1}, the mean ln HU-EEQI increased in {imp} of {len(tot)} capitals and decreased in {len(tot) - imp}. "
        f"J contributes only in {', '.join(JVAL)} (see Data).", "Results. ")
table(D, shares.rename(columns=LABEL), "Table S4.1", "Share of the variance of Δ ln HU-EEQI between consecutive years explained by each part, per capital and pooled (rows sum to one; negative values offset other parts).", fmt="{:.2f}")
table(D, tot[["lnHU"] + parts + ["n_pixels"]].rename(columns=LABEL), "Table S4.2", f"Mean change in ln HU-EEQI between {y0} and {y1} and its exact split by part (positive = improvement), per capital.", fmt="{:.3f}")
figure(D, f_s4, "Figure S4.1", "Share of the variance of year-to-year changes in ln HU-EEQI explained by each part, per capital and pooled.")
figure(D, f_s4b, "Figure S4.2", f"Mean change in ln HU-EEQI between {y0} and {y1} (dots) and its exact decomposition (bars), per capital.")
D.save(os.path.join(DOC, "S4_Decomposition_of_changes.docx"))

# S5
D = new_doc("Supplementary Material S5. Falsification test with MapBiomas land cover")
st_, ch_ = summ.loc["Stable land cover"], summ.loc["Land-cover change"]
para(D, "If pixel trends in HU-EEQI reflected real local change, pixels whose land cover did not change should show "
        "weaker and less frequently significant trends than pixels that changed class. Panel pixels were split into "
        f"'stable' (same MapBiomas class in every year {MB_YEARS[0]}–{MB_YEARS[1]}) and 'changed'. For each pixel, the Sen "
        "slope and a two-sided Mann–Kendall test (no autocorrelation correction; diagnostic only) were computed on the "
        "observed annual series.", "Objective and method. ")
para(D, COMMON, "Data. ")
para(D, f"Stable pixels (n = {int(st_.n_pixels):,}) have a median slope of {st_.median_slope:.2e} yr⁻¹ (median |slope| "
        f"{st_.median_abs_slope:.2e}) and {st_.pct_significant:.1f}% significant trends; pixels that changed land cover "
        f"(n = {int(ch_.n_pixels):,}) have {ch_.median_slope:.2e} yr⁻¹ (median |slope| {ch_.median_abs_slope:.2e}) and "
        f"{ch_.pct_significant:.1f}% significant trends. "
        + ("Trends are as frequent (or more frequent) and as strong in stable pixels as in pixels that changed land cover, "
           "which indicates that most of the HU-EEQI trends are driven by region-wide factors (climate, aerosols, sensor "
           "transition) rather than by local land-cover change."
           if st_.pct_significant >= ch_.pct_significant - 5 else
           "Trends are clearly more frequent in pixels that changed land cover, which supports a local origin of the "
           "HU-EEQI trends."), "Results. ")
table(D, summ, "Table S5.1", "Pixel trends of HU-EEQI in pixels with stable versus changed MapBiomas land cover. Per-capital values: TableS5_3_falsification_by_city.csv; per-pixel values: TableS5_2_pixel_trends_mapbiomas.csv.", fmt="{:.4f}")
figure(D, f_s5, "Figure S5.1", "(a) Distribution of pixel Sen slopes (clipped to the 1st–99th percentiles) and (b) share of pixels with a significant Mann–Kendall trend, for stable and changed MapBiomas land cover.")
D.save(os.path.join(DOC, "S5_MapBiomas_falsification_test.docx"))

# S6
D = new_doc("Supplementary Material S6. Uncertainty and sensitivity analysis")
para(D, f"Following OECD/JRC (2008) and Saisana et al. (2005), {MC_DRAWS} Monte Carlo replicates of the index were "
        "generated by drawing, independently: the weighting scheme (CRITIC, entropy, PCA or equal weights), the EQ "
        "exponent α ~ U(0.4, 0.8), the split of the remainder between E and J (β/γ ~ U(0.25, 0.75)), the normalization "
        "bounds (p1–p99, p2–p98 or p5–p95), the floor of the normalized descriptors (0.01 or 0.05) and the aggregation "
        "rule (geometric or arithmetic). For each replicate, the city-year medians, the ranking of capitals in each year "
        "and the Sen slope of each capital were computed. First-order sensitivity indices (Var[E(Y|Xᵢ)]/Var(Y), by "
        f"partition) quantify the influence of each factor on the trend and on the mean level (seed {MC_SEED}). E and J "
        "are kept as exported (computed with the base weights); since they depend on EQ only through its local "
        "dispersion, this is a second-order approximation.", "Objective and method. ")
para(D, COMMON, "Data. ")
top_t = s6c["Trend (Sen slope)"].sort_values(ascending=False)
top_l = s6c["Mean level"].sort_values(ascending=False)
para(D, f"The ranking of capitals is robust: the median Spearman correlation with the base ranking ranges from "
        f"{s6a['Median'].min():.2f} to {s6a['Median'].max():.2f} across years (lowest P5 = {s6a['P5'].min():.2f}). "
        f"The sign of the trend is kept in a median of {city_tab['Sign agreement (%)'].median():.0f}% of the replicates "
        f"(range {city_tab['Sign agreement (%)'].min():.0f}–{city_tab['Sign agreement (%)'].max():.0f}% across capitals). "
        f"The factor that most affects the trends is {top_t.index[0]} (median Sᵢ = {top_t.iloc[0]:.2f}), followed by "
        f"{top_t.index[1]} ({top_t.iloc[1]:.2f}); for the mean level, {top_l.index[0]} ({top_l.iloc[0]:.2f}) and "
        f"{top_l.index[1]} ({top_l.iloc[1]:.2f}).", "Results. ")
table(D, s6c, "Table S6.1", "First-order sensitivity indices of the capital trends (Sen slope) and mean levels to each uncertain factor (median across capitals). Per-capital values: TableS6_3 and TableS6_4.", fmt="{:.3f}")
table(D, city_tab, "Table S6.2", "Mean rank (1 = best) and Sen slope of the city median HU-EEQI under the base specification, with the 5th–95th percentiles across Monte Carlo replicates, and percentage of replicates that keep the sign of the base trend.", fmt="{:.4f}")
table(D, s6a, "Table S6.3", "Spearman correlation between the base ranking of capitals and the Monte Carlo rankings, per year (median and 5th–95th percentiles).", fmt="{:.3f}")
figure(D, f_s6a, "Figure S6.1", "First-order sensitivity indices of the capital trends and mean levels to each uncertain factor (median across capitals).")
figure(D, f_s6b, "Figure S6.2", "Uncertainty of (a) the mean rank (1 = best) and (b) the Sen slope (per decade) of each capital: base specification (dots) and 5th–95th percentiles across Monte Carlo replicates (bars).")
figure(D, f_s6c, "Figure S6.3", "Spearman correlation between the base and the Monte Carlo rankings of capitals, per year: median (line) and 5th–95th percentiles (band).")
D.save(os.path.join(DOC, "S6_Uncertainty_and_sensitivity.docx"))
json.dump(INFO, open(os.path.join(TAB, "panel_info.json"), "w"), indent=1)
print("concluído", flush=True)
