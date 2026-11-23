# -*- coding: utf-8 -*-
"""Tabelas complementares do HU-EEQI v6 e documentos .docx (em inglês, para o paper):
  S10: completude e preenchimento por capital-ano (equivale à Tabela S1 do RSEI), a partir de
       tabelas/cache_preenchimento_gee.csv (coletar_preenchimento_gee.py);
  S11: calibração (limites de normalização, pesos CRITIC e alternativos, PCA, saturação; equivale à
       Tabela S4 do RSEI), a partir de ../material_suplementar_03/dados/calibration_v6.json;
  Figura 2: documento com a figura de localização (figura2_localizacao.py).
Uso: python gerar_tabelas_docx.py"""
import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import docx
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
TAB = os.path.join(HERE, "tabelas")
DOC = os.path.join(HERE, "documentos")
FIG = os.path.join(HERE, "figuras")
for d in (TAB, DOC):
    os.makedirs(d, exist_ok=True)
CACHE = os.path.join(TAB, "cache_preenchimento_gee.csv")
CALIB = os.path.join(V6, "material_suplementar_03", "dados", "calibration_v6.json")
CAP_SHP = os.path.join(V6, "mapas_anuais_filled", "data", "Capitais.shp")
UF = dict(gpd.read_file(CAP_SHP)[["NM_MUN", "SIGLA_UF"]].values)
SENSORS = [(1, "TM"), (2, "ETM+"), (4, "OLI"), (8, "OLI-2")]


def save_table(t, name):
    t.to_csv(os.path.join(TAB, name + ".csv"), index=False, encoding="utf-8-sig")
    t.to_excel(os.path.join(TAB, name + ".xlsx"), index=False)


# ---------------------------------------------------------------- docx helpers (mesmo estilo do S2–S9)
def new_doc(title, landscape=False):
    D = docx.Document()
    st = D.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
    s = D.sections[0]
    if landscape:
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = Cm(29.7), Cm(21.0)
    else:
        s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.left_margin = s.right_margin = Cm(1.8); s.top_margin = s.bottom_margin = Cm(1.8)
    D.add_heading(title, 1)
    return D


def para(D, text, bold_lead=None, size=10):
    p = D.add_paragraph()
    if bold_lead:
        r = p.add_run(bold_lead); r.bold = True; r.font.size = Pt(size)
    r = p.add_run(text); r.font.size = Pt(size)
    return p


def table(D, t, label, caption, fs=7.5):
    para(D, caption, f"{label}. ", size=9)
    tb = D.add_table(rows=1, cols=len(t.columns))
    tb.style = "Light Grid Accent 1"
    for j, c in enumerate(t.columns):
        tb.rows[0].cells[j].text = str(c)
    for _, row in t.iterrows():
        cells = tb.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = "" if (isinstance(v, float) and not np.isfinite(v)) else str(v)
    for r_ in tb.rows:
        for c_ in r_.cells:
            for p_ in c_.paragraphs:
                for run in p_.runs:
                    run.font.size = Pt(fs)
    D.add_paragraph()


def save_doc(D, name):
    path = os.path.join(DOC, name + ".docx")
    tmp = path + ".tmp.docx"
    D.save(tmp)
    os.replace(tmp, path)
    print("gravado:", path)


# =================================================================================== Figura 2
def doc_figura2():
    png = os.path.join(FIG, "Figure_2_location.png")
    D = new_doc("Figure 2")
    D.add_picture(png, width=Cm(17.0))
    D.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    para(D, "Location of the 27 Brazilian state capitals (26 state capitals and Brasília, Federal District) "
            "and of the five geographic macro-regions of Brazil; the inset shows Brazil in South America. "
            "Data: IBGE (2024) state and municipal boundaries; country boundaries from the LSIB (2017); "
            "datum SIRGAS 2000.",
         "Figure 2. ", size=9)
    save_doc(D, "Figure_2_location")


# =================================================================================== S10 completude
def sensores(js, thr=0.01):
    h = {int(k): v for k, v in json.loads(js).items() if int(k) > 0}
    n = sum(h.values())
    if not n:
        return "—"
    return ", ".join(nm for bit, nm in SENSORS if sum(v for k, v in h.items() if k & bit) / n >= thr)


def s10():
    d = pd.read_csv(CACHE)
    d["uf"] = d.city.map(UF)
    n = d.n_pixels.astype(float)
    pct = lambda c: 100 * d[c] / n                                     # noqa: E731
    full = pd.DataFrame({
        "Capital": d.city, "UF": d.uf, "Year": d.year.astype(int),
        "Sensors": d.sensor_hist.map(sensores),
        "Urban-domain pixels": d.n_pixels.round().astype(int), "Pixel size (m)": d.scale_m.astype(int),
        "Observed (%)": pct("fill_0").round(2),
        "Filled: temporal interpolation (%)": pct("fill_1").round(2),
        "Filled: nearest observed year (%)": pct("fill_2").round(2),
        "Filled: 2-km window mean (%)": pct("fill_3").round(2),
        "Filled: capital median (%)": pct("fill_4").round(2),
        "Mean clear Landsat observations": d.n_obs.round(1),
        "Mean clear thermal observations": d.n_obs_thermal.round(1),
        "Mean MAIAC AOD retrievals": d.n_aod.round(1),
        "AOD from capital median (%)": (100 * d.AQ_filled).round(1),
        "Heat index from neighbouring ERA5-Land cell (%)": (100 * d.HEAT_filled).round(1),
    })
    save_table(full, "TableS10_2_completeness_by_capital_year")

    d["filled"] = d[[f"fill_{t}" for t in range(1, 5)]].sum(axis=1)
    d["pf"] = 100 * d.filled / n
    rows = []
    for c, g in d.groupby("city"):
        tot = g.filled.sum()
        imax = g.pf.idxmax()
        share = lambda t: f"{100 * g[f'fill_{t}'].sum() / tot:.0f}" if tot else "—"   # noqa: E731
        rows.append({
            "Capital": f"{c} ({UF[c]})", "Years": len(g),
            "Urban domain (km²)": f"{np.median(g.n_pixels * g.scale_m ** 2) / 1e6:,.0f}",
            "Mean clear observations": f"{g.n_obs.mean():.1f} ({g.n_obs.min():.1f}–{g.n_obs.max():.1f})",
            "Filled pixel-years (%)": f"{100 * tot / g.n_pixels.sum():.2f}",
            "Max. annual filled (%)": f"{g.pf.max():.1f} ({int(g.year[imax])})" if g.pf.max() >= 0.05 else "0.0",
            "Years > 10% filled": int((g.pf > 10).sum()),
            "Filled by type (%): interp. / nearest / window / median":
                f"{share(1)} / {share(2)} / {share(3)} / {share(4)}",
            "AOD from capital median (%)": f"{100 * g.AQ_filled.mean():.1f}",
            "Heat from neighbouring cell (%)": f"{100 * g.HEAT_filled.mean():.1f}",
        })
    summ = pd.DataFrame(rows)
    save_table(summ, "TableS10_1_completeness_by_capital")

    tot_f = d.filled.sum() / n.sum() * 100
    n_img, n_gt10 = len(d), int((d.pf > 10).sum())
    ft = {t: 100 * d[f"fill_{t}"].sum() / d.filled.sum() for t in range(1, 5)}
    years_cap = d.groupby("city").size()
    short = years_cap[years_cap < years_cap.max()]
    sens_years = full.groupby("Year")["Sensors"].agg(lambda s: s.mode().iat[0])
    stats = dict(total_filled=tot_f, n_img=n_img, n_gt10=n_gt10, ft=ft, short=short.to_dict(),
                 nobs_mean=d.n_obs.mean(), aq=100 * d.AQ_filled.mean(), heat=100 * d.HEAT_filled.mean())

    D = new_doc("Supplementary Material S10 — Data completeness and gap filling", landscape=True)
    para(D, f"Completeness and gap-filling diagnostics of the {n_img} annual HU-EEQI images "
            f"({years_cap.size} capitals × up to {years_cap.max()} years, 2000–2025) of the gap-filled collection. "
            "All statistics are computed over every pixel of the fixed urban domain of each capital at the export "
            "resolution (30 m). 'Clear observations' is the number of cloud-, shadow- and "
            "saturation-free Landsat Collection 2 Level-2 scenes entering the annual median composite of the pixel "
            "(mean over the observed pixels); the minimum of three clear observations defines an observed pixel-year. "
            "Missing pixel-years were filled pixel by pixel, in this order: (1) linear interpolation in time between "
            "the nearest preceding and following observed years; (2) at the ends of the series, the nearest observed "
            "year; (3) for pixels never observed, the mean of the valid pixels within a 2-km window in the same year; "
            "(4) otherwise, the capital median of the year. 'AOD from capital median' is the share of pixels whose "
            "MAIAC aerosol optical depth was replaced by the capital median of the year (fewer than the minimum number "
            "of best-quality retrievals); 'heat from neighbouring cell' is the share of pixels whose ERA5-Land heat "
            "index was taken from the nearest valid neighbouring cell (coastal cells without land data).")
    para(D, f"Overall, {tot_f:.2f}% of the urban-domain pixel-years were filled, and more than 10% of the pixels "
            f"were filled in {n_gt10} of the {n_img} capital-years. Of the filled pixel-years, {ft[1]:.0f}% were "
            f"filled by temporal interpolation, {ft[2]:.0f}% by the nearest observed year, {ft[3]:.0f}% by the "
            f"2-km window mean and {ft[4]:.0f}% by the capital median. The mean number of clear Landsat observations "
            f"per observed pixel-year was {d.n_obs.mean():.1f}.", size=10)
    table(D, summ, "Table S10.1",
          "Completeness and gap filling by capital, 2000–2025. Mean clear observations: mean over the years of the "
          "annual mean number of clear Landsat observations per observed pixel (range of the annual means in "
          "parentheses). Filled pixel-years: share of all urban-domain pixel-years that were filled. Max. annual "
          "filled: largest annual share of filled pixels (year). Filled by type: share of the filled pixel-years "
          "filled by each of the four methods (temporal interpolation / nearest observed year / 2-km window mean / "
          "capital median). The full table by capital and year (sensors, observed and filled shares by method, "
          "clear observations, MAIAC retrievals) is provided as Table S10.2 (file TableS10_2_completeness_by_capital_year, CSV/XLSX).",
          fs=7)
    sy = pd.DataFrame({"Years": [], "Landsat sensors in the annual composites": []})
    grp, start, prev = [], None, None
    for y, s in sens_years.items():
        if s != prev:
            if prev is not None:
                grp.append((start, last, prev))
            start, prev = y, s
        last = y
    grp.append((start, last, prev))
    sy = pd.DataFrame([{"Years": f"{a}" if a == b else f"{a}–{b}", "Landsat sensors in the annual composites": s}
                       for a, b, s in grp])
    table(D, sy, "Table S10.3",
          "Landsat sensors contributing clear observations to the annual composites (sensors present in at least 1% "
          "of the observed pixels; most frequent combination among the capitals in each year). TM and ETM+ "
          "reflectances were harmonized to OLI (Roy et al., 2016, OLS coefficients).", fs=8)
    save_doc(D, "S10_Data_completeness_gap_filling")
    return stats


# =================================================================================== S11 calibração
DESC = {
    "NDVI": ("Normalized difference vegetation index", "–"),
    "Wet": ("Tasseled-cap wetness (Crist, 1985)", "reflectance"),
    "NDBSI": ("Normalized difference built-up and soil index", "–"),
    "HEAT": ("Annual median of the daily afternoon (12–16 h) maximum NWS heat index, ERA5-Land", "°C"),
    "AQ": ("Aerosol optical depth at 550 nm, MODIS MAIAC", "–"),
}


def s11():
    c = json.load(open(CALIB, encoding="utf-8"))
    ds = c["descriptors"]
    b = c["bounds"]; w = c["weights_all"]; ci = c["critic_ci95"]
    sat = pd.DataFrame(c["saturation_pct_by_year"]).T.astype(float)
    load = c["pca_loadings"]
    fmt = lambda v: f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"      # noqa: E731
    t1 = pd.DataFrame([{
        "Descriptor": k, "Definition": DESC[k][0], "Unit": DESC[k][1],
        "Direction": "benefit (+)" if c["direction"][k] == "benefit" else "cost (−)",
        "Lower bound (p1)": fmt(b[k]["min"]), "Upper bound (p99)": fmt(b[k]["max"]),
        "CRITIC weight (95% CI)": f"{w['critic'][k]:.3f} ({ci[k][0]:.3f}–{ci[k][1]:.3f})",
        "Entropy weight": f"{w['ewm'][k]:.3f}", "PCA weight": f"{w['pca'][k]:.3f}",
        "PC1 loading": f"{load[k]:.3f}",
        "Saturated pixels (%), median (max) over years": f"{sat[k].median():.1f} ({sat[k].max():.1f})",
    } for k in ds])
    save_table(t1, "TableS11_1_normalization_bounds_weights")
    byy = pd.DataFrame(c["critic_by_year"]).T.astype(float)[ds]
    byy.index = byy.index.astype(int)
    t2 = byy.round(3).reset_index().rename(columns={"index": "Year"})
    save_table(t2, "TableS11_2_critic_weights_by_year")
    t3 = sat[ds].round(1).reset_index().rename(columns={"index": "Year"})
    t3["Year"] = t3["Year"].astype(int)
    save_table(t3, "TableS11_3_saturation_by_year")

    D = new_doc("Supplementary Material S11 — Normalization bounds and descriptor weights", landscape=True)
    para(D, f"Calibration of the environmental-quality component EQ of the HU-EEQI v6, estimated once from "
            f"{c['n_samples']:,} pixel-years sampled within the fixed urban domain of the 27 capitals in "
            f"{min(c['years'])}–{max(c['years'])} (pooled over capitals and years, so that the index has a common "
            "scale). Each descriptor x is normalized as NI = (x − p1)/(p99 − p1) for benefit descriptors and "
            "NI = (p99 − x)/(p99 − p1) for cost descriptors, with the pooled 1st and 99th percentiles as bounds, and "
            f"clamped to [0.01, 1]. EQ is the weighted geometric mean of the five NI "
            "with CRITIC weights; the 95% confidence interval of each weight comes from "
            "500 bootstrap replicates resampling whole capitals. Entropy (EWM) and PCA weights, and equal weights "
            "(0.2), are the alternatives used in the uncertainty analysis (Supplementary Material S6). PCA: first "
            f"principal component of the five NI, explaining {100 * c['pca_pc1_explained']:.1f}% of the variance. "
            "Saturated pixels: share of the sampled pixels whose NI falls outside [floor, 1] before clamping.")
    table(D, t1, "Table S11.1", "Normalization bounds, direction and weights of the five descriptors of EQ.", fs=7)
    table(D, t2, "Table S11.2",
          "CRITIC weights estimated separately for each year (temporal stability of the weights); the index uses "
          "the pooled weights of Table S11.1.", fs=7)
    save_doc(D, "S11_Normalization_bounds_weights")
    return t1


if __name__ == "__main__":
    doc_figura2()
    s11()
    if os.path.exists(CACHE):
        st = s10()
        print(json.dumps(st, indent=1, default=float))
    else:
        print("cache de preenchimento ainda não existe: rode coletar_preenchimento_gee.py")
