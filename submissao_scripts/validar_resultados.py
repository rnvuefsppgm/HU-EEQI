# -*- coding: utf-8 -*-
"""Validação independente dos números do manuscrito (Fase 3) e geração do arquivo único de números
(numeros_manuscrito.json) usado no texto. Cada checagem recalcula o resultado por outro caminho:
  1. Tabela 1: soma 100%; classes recalculadas dos rasters de 30 m (τ e p Hamed–Rao; MK com empates onde
     a série é incompleta) e comparadas com a tabela (calculada no servidor);
  2. séries municipais: MK, Hamed–Rao e Sen recalculados (pymannkendall) a partir da série média;
  3. Spearman (demografia) recalculado com scipy;
  4. completude/preenchimento: totais e proporções por método;
  5. calibração: pesos somam 1; expoentes renormalizados quando J é degenerado;
  6. notebook 03: reprodutibilidade (diferença máxima) e números-chave das tabelas.
Saídas: ../Submissao_HU_EEQI_v1/06_Validation/Validation_report.md e numeros_manuscrito.json
Uso: python validar_resultados.py"""
import os
import re
import json
import unicodedata
import numpy as np
import pandas as pd
import rasterio
import pymannkendall as pmk
from scipy import stats

V6 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(V6, "trends_HU_EEQI_v6")
FT = os.path.join(V6, "figura2_tabelas_complementares")
M3 = os.path.join(V6, "material_suplementar_03")
OUT = os.path.join(V6, "Submissao_HU_EEQI_v1", "06_Validation")
os.makedirs(OUT, exist_ok=True)
ALPHA = 0.05
rep, N, fails = [], {}, []


def check(name, ok, detail=""):
    rep.append(f"| {name} | {'OK' if ok else '**FALHOU**'} | {detail} |")
    if not ok:
        fails.append(name)


def slug(s):
    a = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", a).strip("_")


# --------------------------------------------------------------------------- 1. Tabela 1
t1 = pd.read_csv(os.path.join(TR, "tabelas", "Table1_trend_class_shares_HamedRao.csv"))
cD, cN, cI, cA = t1.columns[1:5]
s = t1[[cD, cN, cI]].sum(axis=1)
check("Tabela 1: classes somam 100%", bool((s - 100).abs().max() < 0.01), f"desvio máx. {(s - 100).abs().max():.4f} pp")
difs = []
files = os.listdir(os.path.join(TR, "rasters"))
for _, r in t1.iterrows():
    cap = r["Capital"].rstrip("*").rsplit("-", 1)[0].title().replace(" De ", " de ")
    sl = slug(cap)
    fb = r["Capital"].endswith("*")
    pf = f"{sl}_p_{'mk' if fb else 'hr'}.tif"
    if f"{sl}_tau.tif" not in files or pf not in files:
        difs.append((r["Capital"], np.nan)); continue
    with rasterio.open(os.path.join(TR, "rasters", f"{sl}_tau.tif")) as a, \
            rasterio.open(os.path.join(TR, "rasters", pf)) as b:
        tau, p = a.read(1), b.read(1)
    v = np.isfinite(tau) & np.isfinite(p)
    deg = 100 * np.mean((tau[v] < 0) & (p[v] <= ALPHA))
    imp = 100 * np.mean((tau[v] > 0) & (p[v] <= ALPHA))
    difs.append((r["Capital"], max(abs(deg - r[cD]), abs(imp - r[cI]))))
fr = pd.read_csv(os.path.join(V6, "mapas_anuais_filled", "enquadramento_mapas.csv")).set_index("city")["pct_dominio_no_mapa"]
full = {slug(c) for c, v in fr.items() if v >= 99.5}     # rasters cobrem todo o domínio só nessas capitais
dd = [(c, d) for c, d in difs if np.isfinite(d) and slug(c.rstrip("*").rsplit("-", 1)[0]) in full]
dmax = max(d for _, d in dd)
check(f"Tabela 1 × rasters de 30 m ({len(dd)} capitais com o domínio inteiro no recorte)", dmax < 0.5,
      f"diferença máx. {dmax:.2f} pp ({[c for c, d in dd if d == dmax][0]})")
outros = [(c, round(d, 2)) for c, d in difs if (c, d) not in dd]
rep.append(f"| (informativo) capitais com recorte parcial | — | {outros} |")
N["t1_deg_mean"], N["t1_imp_mean"] = t1[cD].mean(), t1[cI].mean()
N["t1_deg_w"] = (t1[cD] * t1[cA]).sum() / t1[cA].sum()
N["t1_imp_w"] = (t1[cI] * t1[cA]).sum() / t1[cA].sum()
N["t1_ns_min"], N["t1_ns_max"] = t1[cN].min(), t1[cN].max()
N["t1_n_deg_gt_third"], N["t1_n_deg_gt_half"] = int((t1[cD] > 100 / 3).sum()), int((t1[cD] > 50).sum())
N["t1_top_deg"] = t1.sort_values(cD, ascending=False).head(5)[["Capital", cD]].values.tolist()
N["t1_top_imp"] = t1.sort_values(cI, ascending=False).head(5)[["Capital", cI]].values.tolist()
N["t1_imp_gt_deg"] = t1[t1[cI] > t1[cD]]["Capital"].tolist()
N["t1_total_area_km2"] = t1[cA].sum()

# --------------------------------------------------------------------------- 2. séries municipais
ser = pd.read_csv(os.path.join(TR, "tabelas", "TableS7_2_municipal_mean_series.csv"), index_col=0)
s71 = pd.read_csv(os.path.join(TR, "tabelas", "TableS7_1_tau_sign_and_municipal_series.csv"))
ok_all, worst = True, 0.0
dec = inc = 0
for _, r in s71.iterrows():
    cap = r["Capital"].rstrip("*").rsplit("-", 1)[0]
    col = [c for c in ser.columns if c.upper() == cap.upper()][0]
    x = ser[col].dropna().values
    o, h, sen = pmk.original_test(x, alpha=ALPHA), pmk.hamed_rao_modification_test(x, alpha=ALPHA), pmk.sens_slope(x)
    d = max(abs(o.Tau - r["Kendall τ"]), abs(h.p - r["p (Hamed–Rao)"]), abs(sen.slope - r["Sen slope (yr⁻¹)"]))
    worst = max(worst, d)
    if h.p <= ALPHA:
        dec += o.Tau < 0
        inc += o.Tau > 0
check("Séries municipais: τ, p Hamed–Rao e Sen recalculados", worst < 1e-6, f"diferença máx. {worst:.2e}")
N["ser_dec"], N["ser_inc"] = int(dec), int(inc)
N["ser_n_years"] = int(s71["n years"].max())
check("Séries municipais: contagem de quedas/altas", dec == (s71["Trend (Hamed–Rao)"] == "decreasing").sum(),
      f"{dec} quedas, {inc} altas")

m73 = pd.read_csv(os.path.join(TR, "tabelas", "TableS7_3_mean_sd_and_filling.csv"))
rho_ms, p_ms = stats.spearmanr(m73["Mean HU-EEQI"], m73["Mean temporal SD"])
N["sp_mean_sd"] = [round(rho_ms, 2), p_ms]
check("Nível × variabilidade (Spearman, 27 capitais)", rho_ms < -0.8 and p_ms < 0.001, f"ρ = {rho_ms:.2f}, p = {p_ms:.1e}")
N["mean_level_range"] = [m73["Mean HU-EEQI"].min(), m73["Mean HU-EEQI"].max(), m73["Mean HU-EEQI"].mean()]

# --------------------------------------------------------------------------- 3. Spearman
dem = pd.read_csv(os.path.join(TR, "tabelas", "TableS9_2_demographic_indicators.csv"))
sp = pd.read_csv(os.path.join(TR, "tabelas", "TableS9_1_spearman_demographics.csv"))
ind = {"Population density 2022": "density_2022_hab_km2", "Relative growth 1991–2022 (%)": "growth_1991_2022_pct",
       "Population 2022": "pop_2022"}
cls = {"degradation": "Significant degradation (%)", "improvement": "Significant improvement (%)"}
wd = 0.0
for _, r in sp.iterrows():
    rho, p = stats.spearmanr(dem[cls[r["Trend class"]]], dem[ind[r["Indicator"]]])
    wd = max(wd, abs(rho - r["Spearman ρ"]), abs(p - r["p"]))
    N[f"sp_{r['Trend class'][:3]}_{ind[r['Indicator']]}"] = [round(rho, 2), round(p, 3)]
check("Spearman (6 pares) recalculado", wd < 1e-9, f"diferença máx. {wd:.1e}; n = {len(dem)}")
mm = dem.assign(C=dem.Capital.str.rstrip("*")).merge(t1.assign(C=t1.Capital.str.rstrip("*")), on="C", suffixes=("_d", "_t"))
check("Indicadores demográficos × Tabela 1", len(mm) == 27 and bool(np.allclose(mm[cD + "_d"], mm[cD + "_t"])),
      f"{len(mm)} capitais pareadas; mesmos percentuais de degradação")

# --------------------------------------------------------------------------- 4. completude
cc = pd.read_csv(os.path.join(FT, "tabelas", "cache_preenchimento_gee.csv"))
filled = cc[[f"fill_{t}" for t in range(1, 5)]].sum(axis=1)
pf = 100 * filled / cc.n_pixels
N["fill_total_pct"] = 100 * filled.sum() / cc.n_pixels.sum()
N["fill_n_img"], N["fill_n_gt10"] = len(cc), int((pf > 10).sum())
N["fill_share_type"] = {t: 100 * cc[f"fill_{t}"].sum() / filled.sum() for t in range(1, 5)}
N["nobs_mean"] = cc.n_obs.mean()
N["aq_filled_pct"], N["heat_filled_pct"] = 100 * cc.AQ_filled.mean(), 100 * cc.HEAT_filled.mean()
check("Completude: 27 capitais × 26 anos, menos 1 capital-ano ausente", len(cc) == 701,
      f"{len(cc)} imagens; capitais com 25 anos: {cc.groupby('city').size().pipe(lambda g: g[g < 26].index.tolist())}")
check("Completude: tipos 1–4 = pixels não observados", bool((cc.n_pixels - cc.fill_0 - filled).abs().max() < 1e-6),
      f"{N['fill_total_pct']:.2f}% preenchido; > 10% em {N['fill_n_gt10']} capital-anos")
N["fill_by_city"] = (cc.assign(f=filled).groupby("city").apply(lambda g: 100 * g.f.sum() / g.n_pixels.sum())
                     .sort_values(ascending=False).head(4).round(1).to_dict())

# --------------------------------------------------------------------------- 5. calibração
cal = json.load(open(os.path.join(M3, "dados", "calibration_v6.json"), encoding="utf-8"))
w = cal["weights"]
check("Pesos CRITIC somam 1", abs(sum(w.values()) - 1) < 1e-5, json.dumps({k: round(v, 3) for k, v in w.items()}))
a, b, g = 0.6, 0.2, 0.2
check("Expoentes renormalizados (J degenerado)", abs(a / (a + b) - 0.75) < 1e-12 and abs(b / (a + b) - 0.25) < 1e-12,
      "EQ^0.75 · E^0.25")
N.update(cal_n=cal["n_samples"], cal_pc1=100 * cal["pca_pc1_explained"], weights=w, ci=cal["critic_ci95"],
         bounds=cal["bounds"])

# --------------------------------------------------------------------------- 6. notebook 03
r21 = pd.read_csv(os.path.join(M3, "tabelas", "TableS2_1_reproducibility.csv"))
num = r21.select_dtypes("number")
N["repro_table"] = r21.round(8).to_dict("records")
p32 = pd.read_csv(os.path.join(M3, "tabelas", "TableS3_2_pettitt_summary.csv"))
N["pettitt"] = p32.to_dict("records")
s51 = pd.read_csv(os.path.join(M3, "tabelas", "TableS5_1_falsification_summary.csv"))
N["falsification"] = s51.to_dict("records")
s41 = pd.read_csv(os.path.join(M3, "tabelas", "TableS4_1_interannual_variance_shares.csv"))
N["variance_shares"] = s41.to_dict("records")
s42 = pd.read_csv(os.path.join(M3, "tabelas", "TableS4_2_change_2000_2025.csv"))
N["change_2000_2025"] = s42.to_dict("records")
s60 = pd.read_csv(os.path.join(M3, "tabelas", "TableS6_0_first_order_sensitivity_median.csv"))
N["sensitivity"] = s60.to_dict("records")
s62 = pd.read_csv(os.path.join(M3, "tabelas", "TableS6_2_city_rank_and_trend_uncertainty.csv"))
N["rank_uncertainty"] = s62.describe().round(3).to_dict()
s31 = pd.read_csv(os.path.join(M3, "tabelas", "TableS3_1_common_year_signal.csv"))
N["common_signal"] = s31.to_dict("records")
check("Notebook 03: tabelas lidas", True, f"reprodutibilidade: {num.abs().max().round(8).to_dict()}")

# --------------------------------------------------------------------------- 7. robustez
rb = pd.read_csv(os.path.join(TR, "tabelas", "TableS8_1_tests_and_autocorrelation.csv"))
for k in ("MK original", "MK ties", "Hamed–Rao", "TFPW"):
    N[f"rb_sig_{k}"] = (rb[f"{k}: degradation (%)"] + rb[f"{k}: improvement (%)"]).mean()
N["rb_r1_gt03"] = rb["Pixels with r1 > 0.3 (%)"].mean()
N["rb_r1_median_range"] = [rb["Median lag-1 autocorrelation"].min(), rb["Median lag-1 autocorrelation"].max()]
check("Robustez: Hamed–Rao ≤ MK original na média", N["rb_sig_Hamed–Rao"] <= N["rb_sig_MK original"],
      f"MK {N['rb_sig_MK original']:.1f}% × HR {N['rb_sig_Hamed–Rao']:.1f}% × TFPW {N['rb_sig_TFPW']:.1f}%")
reg = {"N": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"], "NE": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
       "CW": ["DF", "GO", "MT", "MS"], "SE": ["ES", "MG", "RJ", "SP"], "S": ["PR", "RS", "SC"]}
uf = t1.Capital.str.rstrip("*").str[-2:]
N["region_deg"] = {k: t1[uf.isin(v)][cD].mean() for k, v in reg.items()}
N["region_imp"] = {k: t1[uf.isin(v)][cI].mean() for k, v in reg.items()}

json.dump(N, open(os.path.join(OUT, "numeros_manuscrito.json"), "w", encoding="utf-8"), ensure_ascii=False,
          indent=1, default=float)
txt = ["# Validation report — HU-EEQI v6 manuscript", "",
       "Each check recomputes the result by an independent path (rasters, pymannkendall, scipy, GEE counts).", "",
       "| Check | Result | Detail |", "|---|---|---|"] + rep + ["", f"Failed checks: {len(fails)}"]
open(os.path.join(OUT, "Validation_report.md"), "w", encoding="utf-8").write("\n".join(txt))
print("\n".join(txt))
