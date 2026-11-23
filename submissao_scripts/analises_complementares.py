# -*- coding: utf-8 -*-
"""Análises complementares pedidas na revisão especializada (painel fixo do notebook 03, série observada):
  A. Decomposição da mudança de ln HU-EEQI entre as médias de 2000–2004 e 2021–2025 (menos sensível aos anos
     extremos que a comparação 2000 × 2025), por capital e descritor  -> Table S9.3
  B. Degrau do componente E na transição de sensores (média 2013–2015 − média 2009–2011)   -> Table S8.4
  C. % de pixels do painel com tendência significativa (Hamed–Rao) no HU-EEQI, em EQ e no HU-EEQI com E fixo na
     média do pixel                                                                             -> Table S5.2
  D. Diferença Sul − Norte da série média do domínio urbano (Sen e Hamed–Rao); robustez nas 26 capitais com série
     completa; parcela da variância entre capitais do nível médio explicada por NI_HEAT; estabilidade do CRITIC.
Saídas em tabelas_complementares/ e numeros_complementares.json (06_Validation).
Uso: python analises_complementares.py"""
import os
import json
import warnings
import numpy as np
import pandas as pd
import pymannkendall as pmk
from scipy import stats

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
M3 = os.path.join(V6, "material_suplementar_03")
TR = os.path.join(V6, "trends_HU_EEQI_v6", "tabelas")
OUT = os.path.join(HERE, "tabelas_complementares")
VAL = os.path.join(V6, "Submissao_HU_EEQI_v1", "06_Validation")
os.makedirs(OUT, exist_ok=True)
cal = json.load(open(os.path.join(M3, "dados", "calibration_v6.json"), encoding="utf-8"))
W = cal["weights"]
REG = {"Belém": "North", "Boa Vista": "North", "Macapá": "North", "Manaus": "North", "Palmas": "North",
       "Porto Velho": "North", "Rio Branco": "North", "Aracaju": "Northeast", "Fortaleza": "Northeast",
       "João Pessoa": "Northeast", "Maceió": "Northeast", "Natal": "Northeast", "Recife": "Northeast",
       "Salvador": "Northeast", "São Luís": "Northeast", "Teresina": "Northeast", "Brasília": "Central-West",
       "Campo Grande": "Central-West", "Cuiabá": "Central-West", "Goiânia": "Central-West",
       "Belo Horizonte": "Southeast", "Rio de Janeiro": "Southeast", "São Paulo": "Southeast", "Vitória": "Southeast",
       "Curitiba": "South", "Florianópolis": "South", "Porto Alegre": "South"}
P = pd.read_csv(os.path.join(M3, "dados", "panel_v6.csv"))
P = P[(P.HU_EEQI > 0) & P.EQ.notna() & P.E_local.notna()].copy()
P["year"] = P.year.astype(int)
jv = P.j_valid.fillna(0)
P["a"] = np.where(jv > 0, 0.6, 0.75)
P["b"] = np.where(jv > 0, 0.2, 0.25)
P["c"] = np.where(jv > 0, 0.2, 0.0)
N = {}

# ------------------------------------------------------------------ A. decomposição por janelas
D = {"NDVI": "NI_NDVI", "Wetness": "NI_Wet", "NDBSI": "NI_NDBSI", "Heat index": "NI_HEAT", "AOD": "NI_AQ"}
WK = {"NDVI": "NDVI", "Wetness": "Wet", "NDBSI": "NDBSI", "Heat index": "HEAT", "AOD": "AQ"}
for k, c in D.items():
    P["c_" + k] = P.a * W[WK[k]] * np.log(P[c].clip(lower=0.01))
P["c_E (local equity)"] = P.b * np.log(P.E_local.clip(lower=0.01))
P["c_J (local justice)"] = P.c * np.log(P.J_local.clip(lower=0.01))
P["lnHU"] = np.log(P.HU_EEQI)
cols = ["lnHU"] + [c for c in P.columns if c.startswith("c_")]
early = P[P.year.between(2000, 2004)].groupby(["city", "pid"])[cols].mean()
late = P[P.year.between(2021, 2025)].groupby(["city", "pid"])[cols].mean()
dd = (late - early).dropna().groupby("city").mean()
dd.columns = ["Δ ln HU-EEQI"] + [c[2:] for c in dd.columns[1:]]
dd["Sum of contributions"] = dd.iloc[:, 1:].sum(axis=1)
dd.insert(0, "Region", dd.index.map(REG))
dd = dd.reset_index().rename(columns={"city": "Capital"})
dd.round(4).to_csv(os.path.join(OUT, "TableS9_3_change_decomposition_5yr_windows.csv"), index=False)
comp = ["NDVI", "Wetness", "NDBSI", "Heat index", "AOD", "E (local equity)"]
N["win_neg_lnHU"] = int((dd["Δ ln HU-EEQI"] < 0).sum())
N["win_median_all"] = dd[comp].median().round(3).to_dict()
N["win_n_negative"] = {c: int((dd[c] < 0).sum()) for c in comp}
N["win_median_region"] = dd.groupby("Region")[comp + ["Δ ln HU-EEQI"]].median().round(3).to_dict("index")
N["win_top_driver"] = dict(zip(dd.Capital, dd[comp].idxmin(axis=1)))
N["win_caps"] = dd.set_index("Capital")[comp + ["Δ ln HU-EEQI"]].round(3).to_dict("index")
N["win_closure_maxerr"] = float((dd["Δ ln HU-EEQI"] - dd["Sum of contributions"]).abs().max())

# ------------------------------------------------------------------ B. degrau de E
pre = P[P.year.between(2009, 2011)].groupby("city").E_local.mean()
post = P[P.year.between(2013, 2015)].groupby("city").E_local.mean()
st = (post - pre).rename("ΔE (2013–2015 minus 2009–2011)")
eq_pre = P[P.year.between(2009, 2011)].groupby("city").EQ.mean()
eq_post = P[P.year.between(2013, 2015)].groupby("city").EQ.mean()
tb = pd.DataFrame({"E 2009–2011": pre, "E 2013–2015": post, "ΔE": st, "ΔEQ": eq_post - eq_pre}).round(4)
tb.reset_index().rename(columns={"city": "Capital"}).to_csv(os.path.join(OUT, "TableS8_4_E_step_sensor_transition.csv"), index=False)
N["E_step_median"], N["E_step_n_neg"] = float(st.median()), int((st < 0).sum())
N["EQ_step_median"] = float((eq_post - eq_pre).median())

# ------------------------------------------------------------------ C. tendências HU × EQ × E fixo
P["E_mean"] = P.groupby("pid").E_local.transform("mean")
P["HU_fixE"] = np.exp(P.a * np.log(P.EQ.clip(lower=0.01)) + P.b * np.log(P.E_mean.clip(lower=0.01)) +
                      P.c * np.log(P.J_local.clip(lower=0.01)))
rows = []
for (city, pid), g in P.sort_values("year").groupby(["city", "pid"]):
    if len(g) < 20:
        continue
    r = {"city": city}
    for v in ("HU_EEQI", "EQ", "HU_fixE"):
        try:
            h = pmk.hamed_rao_modification_test(g[v].values)
            r[v] = "dec" if (h.p <= 0.05 and h.Tau < 0) else ("inc" if (h.p <= 0.05 and h.Tau > 0) else "ns")
        except Exception:      # noqa: BLE001
            r[v] = np.nan
    rows.append(r)
T = pd.DataFrame(rows)
res = []
for city, g in T.groupby("city"):
    d = {"Capital": city, "Pixels (≥ 20 observed years)": len(g)}
    for v, lab in (("HU_EEQI", "HU-EEQI"), ("EQ", "EQ only"), ("HU_fixE", "HU-EEQI with E fixed")):
        d[f"{lab}: decline (%)"] = 100 * (g[v] == "dec").mean()
        d[f"{lab}: improvement (%)"] = 100 * (g[v] == "inc").mean()
    res.append(d)
R = pd.DataFrame(res)
tot = {"Capital": "All capitals", "Pixels (≥ 20 observed years)": int(R.iloc[:, 1].sum())}
for c in R.columns[2:]:
    tot[c] = R[c].mean()
R = pd.concat([R, pd.DataFrame([tot])], ignore_index=True).round(1)
R.to_csv(os.path.join(OUT, "TableS5_2_panel_trends_HU_EQ_fixedE.csv"), index=False)
N["panel_trends_mean"] = {k: v for k, v in tot.items() if k != "Capital"}

# ------------------------------------------------------------------ D. outros números
ser = pd.read_csv(os.path.join(TR, "TableS7_2_municipal_mean_series.csv"), index_col=0)
south = ser[["Curitiba", "Florianópolis", "Porto Alegre"]].mean(axis=1)
north = ser[[c for c in ser.columns if REG.get(c) == "North"]].mean(axis=1)
gap = (south - north).dropna()
h, s = pmk.hamed_rao_modification_test(gap.values), pmk.sens_slope(gap.values)
N["gap_SN"] = {"2000": float(gap.iloc[0]), "2025": float(gap.iloc[-1]), "sen": float(s.slope), "p_hr": float(h.p)}
rb = pd.read_csv(os.path.join(TR, "TableS8_1_tests_and_autocorrelation.csv"))
rb26 = rb[~rb.Capital.str.startswith("TERESINA")]
N["rb26"] = {k: float((rb26[f"{k}: degradation (%)"] + rb26[f"{k}: improvement (%)"]).mean())
             for k in ("MK original", "Hamed–Rao", "TFPW")}
N["rb26_r1gt03"] = float(rb26["Pixels with r1 > 0.3 (%)"].mean())
cm = P.groupby("city")[["HU_EEQI", "NI_HEAT", "EQ", "E_local"]].mean()
N["r2_level_heat"] = float(stats.pearsonr(cm.HU_EEQI, cm.NI_HEAT)[0] ** 2)
cb = pd.DataFrame(cal["critic_by_year"]).T.astype(float)
N["critic_by_year_range"] = {k: [float(cb[k].min()), float(cb[k].max())] for k in cb.columns}
N["sat_heat_max"] = max((v["HEAT"], int(y)) for y, v in cal["saturation_pct_by_year"].items())
fs = pd.read_csv(os.path.join(M3, "tabelas", "TableS5_1_falsification_summary.csv"))
N["falsification"] = fs.round(5).to_dict("records")
dem = pd.read_csv(os.path.join(TR, "TableS9_1_spearman_demographics.csv"))
N["spearman"] = dem.round(3).to_dict("records")
json.dump(N, open(os.path.join(VAL, "numeros_complementares.json"), "w", encoding="utf-8"), ensure_ascii=False,
          indent=1, default=float)
print(json.dumps({k: v for k, v in N.items() if k not in ("win_caps", "falsification", "spearman")}, ensure_ascii=False,
                 indent=1, default=float))
