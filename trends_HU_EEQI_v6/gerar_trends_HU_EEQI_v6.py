# -*- coding: utf-8 -*-
"""
Resultados de tendência do HU-EEQI v6 no mesmo formato do paper do RSEI (RSEI_Paper_luana_Review):
  - Tabela 1: % da área (domínio urbano, dentro do município) com degradação significativa, sem tendência e
    melhora significativa (teste principal: Hamed–Rao, p <= 0,05; o principal_test gravado no asset).
  - Figuras 3–11: 5 painéis por capital (sinal do τ, tendência significativa, média, mediana e desvio-padrão
    temporal do HU-EEQI), 3 capitais por figura, 600 dpi (layout do script 16 do RSEI).
  - S7: % de τ negativo/positivo e série municipal média (Mann–Kendall, Hamed–Rao, Sen; Figura S7.1).
  - S8: robustez — MK original, MK com empates, Hamed–Rao e TFPW sobre TODOS os pixels; autocorrelação lag-1.
  - S9: Spearman entre % degradação/melhora e densidade 2022, crescimento 1991–2022 e população 2022 (IBGE).
  - Texto de resultados (em inglês) com os números gerados.
Fontes: projects/mapbiomas-caatinga-cloud04/assets/TRENDS_HU-EEQI_v6 e HU-EEQI_v6_filled.
Capitais ainda sem tendência no asset ficam marcadas como pendentes; ao rodar de novo, só o que falta é
calculado/baixado (cache em tabelas/cache e rasters/).
Uso: python gerar_trends_HU_EEQI_v6.py      (EE_PROJECT opcional; padrão <your-project>)
"""
import os
import sys
import csv
import json
import math
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import ee
import geopandas as gpd
from shapely.geometry import box
import rasterio

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
sys.path.insert(0, HERE)
V6 = os.path.dirname(HERE)
T_ASSET = "projects/mapbiomas-caatinga-cloud04/assets/TRENDS_HU-EEQI_v6"
F_ASSET = "projects/mapbiomas-caatinga-cloud04/assets/HU-EEQI_v6_filled"
SHP = os.path.join(V6, "mapas_anuais_filled", "data", "Capitais.shp")
FRAMES = os.path.join(V6, "mapas_anuais_filled", "enquadramento_mapas.csv")
SOCIO = os.path.join(HERE, "dados", "socioeconomico_IBGE_capitais.csv")
RDIR, FIG, TAB, DOC = (os.path.join(HERE, d) for d in ("rasters", "figuras", "tabelas", "documentos"))
CACHE = os.path.join(TAB, "cache")
for d in (RDIR, FIG, TAB, DOC, CACHE):
    os.makedirs(d, exist_ok=True)
ALPHA = 0.05
DPI = 600
Y0, Y1 = 2000, 2025
DL_BANDS = {"tau": "HU_EEQI_tau", "p_hr": "HU_EEQI_p_value_hr", "p_mk": "HU_EEQI_p_value_ties", "mean": "HU_EEQI_mean",
            "median": "HU_EEQI_median", "sd": "HU_EEQI_stdDev"}
TESTS = {"MK original": ("HU_EEQI_p_value", "HU_EEQI_tau"), "MK ties": ("HU_EEQI_p_value_ties", "HU_EEQI_tau"),
         "Hamed–Rao": ("HU_EEQI_p_value_hr", "HU_EEQI_tau"), "TFPW": ("HU_EEQI_p_value_tfpw", "HU_EEQI_S_tfpw")}
PRINCIPAL = "Hamed–Rao"
FALLBACK_TEST = "MK ties"   # só onde o Hamed–Rao não existe (série incompleta no asset; ex.: Teresina sem 2016)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


project = os.environ.get("EE_PROJECT")
try:
    ee.Initialize(project=project)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=project)
print("Earth Engine | projeto", project, flush=True)

gdf = gpd.read_file(SHP).to_crs(4326)
UF = dict(zip(gdf.NM_MUN, gdf.SIGLA_UF))
CAPS = sorted(gdf.NM_MUN)
FR = pd.read_csv(FRAMES).set_index("city")


def ee_geom(geom):
    gj = json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]
    return ee.Geometry(gj, "EPSG:4326", False)


MUN = {m: gdf[gdf.NM_MUN == m].geometry.iloc[0] for m in CAPS}
tcol = ee.ImageCollection(T_ASSET)
tinfo = tcol.map(lambda im: ee.Feature(None, {"id": im.get("system:id"), "city": im.get("city")})).getInfo()["features"]
TID = {f["properties"]["city"]: f["properties"]["id"] for f in tinfo}
UPD = {m: ee.data.getAsset(TID[m]).get("updateTime", "") for m in TID}
meta_path = os.path.join(RDIR, "versoes_assets.json")
meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
for m in TID:
    if meta.get(m) not in (None, UPD[m]):                 # asset refeito: refaz só esta capital
        for f_ in os.listdir(RDIR):
            if f_.startswith(slug(m) + "_"):
                os.remove(os.path.join(RDIR, f_))
        for f_ in (f"stats_{slug(m)}.json", f"series_{slug(m)}.json"):
            if os.path.exists(os.path.join(CACHE, f_)):
                os.remove(os.path.join(CACHE, f_))
        print("asset atualizado, refazendo:", m, flush=True)
    meta[m] = UPD[m]
json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
READY = [m for m in CAPS if m in TID]
PENDING = [m for m in CAPS if m not in TID]
print(f"tendências prontas: {len(READY)} | pendentes: {PENDING or 'nenhuma'}", flush=True)


# ---------------------------------------------------------------------------------------------------
# 1) Estatísticas de área e autocorrelação no servidor (raster inteiro, domínio dentro do município)
# ---------------------------------------------------------------------------------------------------
def city_stats(m):
    cf = os.path.join(CACHE, f"stats_{slug(m)}.json")
    if os.path.exists(cf):
        return json.load(open(cf, encoding="utf-8"))
    img, g = ee.Image(TID[m]), ee_geom(MUN[m])
    tau = img.select("HU_EEQI_tau")
    pa = ee.Image.pixelArea()
    red = lambda im: im.reduceRegion(ee.Reducer.sum().group(1), g, 30, maxPixels=1e13, tileScale=4)
    out = {}
    for t, (pb, sb) in TESTS.items():
        p, s = img.select(pb), img.select(sb)
        cls = (ee.Image(1).where(p.lte(ALPHA).And(s.lt(0)), 0).where(p.lte(ALPHA).And(s.gt(0)), 2)
               .updateMask(tau.mask()).updateMask(p.mask()).rename("c"))   # sem p-valor = sem classe
        out[t] = red(pa.addBands(cls))
    sgn = ee.Image(1).where(tau.lt(0), 0).where(tau.gt(0), 2).updateMask(tau.mask()).rename("c")
    out["tau_sign"] = red(pa.addBands(sgn))
    r1 = img.select("HU_EEQI_r1_resid")
    out["r1"] = (r1.addBands(r1.gt(0.3).rename("gt03")).reduceRegion(
        ee.Reducer.median().combine(ee.Reducer.mean(), sharedInputs=True), g, 30, maxPixels=1e13, tileScale=4, bestEffort=True))
    out["levels"] = (img.select(["HU_EEQI_mean", "HU_EEQI_stdDev", "HU_EEQI_sen_slope", "HU_EEQI_n_filled"])
                     .reduceRegion(ee.Reducer.mean(), g, 30, maxPixels=1e13, tileScale=4, bestEffort=True))
    r = ee.Dictionary(out).getInfo()
    res = {"city": m}
    for t in list(TESTS) + ["tau_sign"]:
        a = {int(x["group"]): x["sum"] for x in r[t]["groups"]}
        tot = sum(a.values())
        res[t] = ({"neg": 100 * a.get(0, 0) / tot, "ns": 100 * a.get(1, 0) / tot, "pos": 100 * a.get(2, 0) / tot,
                   "area_km2": tot / 1e6} if tot > 0 else
                  {"neg": float("nan"), "ns": float("nan"), "pos": float("nan"), "area_km2": 0.0})
    res["r1_median"] = r["r1"].get("HU_EEQI_r1_resid_median")
    res["r1_pct_gt03"] = 100 * (r["r1"].get("gt03_mean") or 0)
    res["mean_HU"] = r["levels"].get("HU_EEQI_mean")
    res["mean_SD"] = r["levels"].get("HU_EEQI_stdDev")
    res["mean_sen"] = r["levels"].get("HU_EEQI_sen_slope")
    res["mean_n_filled"] = r["levels"].get("HU_EEQI_n_filled")
    res["updateTime"] = UPD[m]
    json.dump(res, open(cf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


# ---------------------------------------------------------------------------------------------------
# 2) Série municipal média (série preenchida) — mesma lógica da Figura S2 do RSEI
# ---------------------------------------------------------------------------------------------------
def city_series(m):
    cf = os.path.join(CACHE, f"series_{slug(m)}.json")
    if os.path.exists(cf):
        return json.load(open(cf, encoding="utf-8"))
    g = ee_geom(MUN[m])
    fc = (ee.ImageCollection(F_ASSET).filter(ee.Filter.eq("city", m))
          .map(lambda im: ee.Feature(None, {"year": im.get("year"), "mean": im.select("HU_EEQI").reduceRegion(
              ee.Reducer.mean(), g, 30, maxPixels=1e13, tileScale=4).get("HU_EEQI")})))
    v = {int(f["properties"]["year"]): f["properties"]["mean"] for f in fc.getInfo()["features"]}
    json.dump(v, open(cf, "w"), indent=1)
    return {str(k): x for k, x in v.items()}


def run_parallel(fn, items, label):
    out = {}
    with ThreadPoolExecutor(6) as ex:
        for m, r in zip(items, ex.map(lambda x: _retry(fn, x), items)):
            out[m] = r
    print(label, "ok", flush=True)
    return out


def _retry(fn, x):
    for k in range(4):
        try:
            return fn(x)
        except Exception as e:
            err = str(e)
            time.sleep(15 * (k + 1))
    print("FALHOU", fn.__name__, x, err[:150], flush=True)
    return None


STATS = run_parallel(city_stats, READY, "estatísticas de área")
SERIES = run_parallel(city_series, list(CAPS), "séries municipais")


# ---------------------------------------------------------------------------------------------------
# 3) Rasters para as figuras (enquadramento dos mapas anuais; recorte no município)
# ---------------------------------------------------------------------------------------------------
def frame_geom(m):
    f = FR.loc[m]
    return MUN[m].intersection(box(f.lon_min, f.lat_min, f.lon_max, f.lat_max)), int(f.scale_m)


def fetch(job):
    m, key = job
    path = os.path.join(RDIR, f"{slug(m)}_{key}.tif")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return 0
    geom, scale = frame_geom(m)
    g = ee_geom(geom)
    img = ee.Image(TID[m]).select(DL_BANDS[key]).clip(g).toFloat()
    url = img.getDownloadURL({"region": g.bounds(1), "scale": scale, "format": "GEO_TIFF", "crs": "EPSG:4326"})
    with urllib.request.urlopen(url, timeout=600) as r:
        data = r.read()
    open(path + ".part", "wb").write(data)
    os.replace(path + ".part", path)
    return 1


jobs = [(m, k) for m in READY for k in DL_BANDS]
with ThreadPoolExecutor(6) as ex:
    n = sum(r or 0 for r in ex.map(lambda j: _retry(fetch, j), jobs))
print("rasters baixados:", n, "novos", flush=True)

# ---------------------------------------------------------------------------------------------------
# 4) Tabelas
# ---------------------------------------------------------------------------------------------------
import pymannkendall as pmk
from scipy.stats import spearmanr


def save_table(t, name, index=True):
    t.to_csv(os.path.join(TAB, f"{name}.csv"), index=index, encoding="utf-8")
    t.to_excel(os.path.join(TAB, f"{name}.xlsx"), index=index)
    return t


lab = lambda m: f"{m.upper()}-{UF[m]}"
ok = [m for m in READY if STATS.get(m)]
PRIN = {m: (PRINCIPAL if STATS[m][PRINCIPAL]["area_km2"] > 0 else FALLBACK_TEST) for m in ok}
FALLBACK = [m for m in ok if PRIN[m] != PRINCIPAL]
if FALLBACK:
    print("sem Hamed–Rao no asset (série incompleta) -> MK com empates:", FALLBACK, flush=True)
lab1 = lambda m: lab(m) + ("*" if m in FALLBACK else "")
T1 = pd.DataFrame({"Capital": [lab1(m) for m in ok],
                   "Significant degradation (%)": [STATS[m][PRIN[m]]["neg"] for m in ok],
                   "No significant trend (%)": [STATS[m][PRIN[m]]["ns"] for m in ok],
                   "Significant improvement (%)": [STATS[m][PRIN[m]]["pos"] for m in ok],
                   "Urban domain area (km²)": [STATS[m][PRIN[m]]["area_km2"] for m in ok]})
save_table(T1, "Table1_trend_class_shares_HamedRao", index=False)
TS = pd.DataFrame({"Capital": [lab(m) for m in ok],
                   "Negative τ (%)": [STATS[m]["tau_sign"]["neg"] for m in ok],
                   "Null τ (%)": [STATS[m]["tau_sign"]["ns"] for m in ok],
                   "Positive τ (%)": [STATS[m]["tau_sign"]["pos"] for m in ok]})
rows = []
for m in CAPS:
    s = SERIES.get(m) or {}
    ys = sorted(int(y) for y in s if s[y] is not None)
    x = np.array([s[str(y)] if str(y) in s else s.get(y) for y in ys], float)
    if len(x) >= 10:
        o, h, sen = pmk.original_test(x, alpha=ALPHA), pmk.hamed_rao_modification_test(x, alpha=ALPHA), pmk.sens_slope(x)
        rows.append({"Capital": lab(m), "n years": len(x), "Mean HU-EEQI": x.mean(), "Kendall τ": o.Tau,
                     "p (MK)": o.p, "p (Hamed–Rao)": h.p, "Sen slope (yr⁻¹)": sen.slope,
                     "Trend (Hamed–Rao)": ("decreasing" if h.p <= ALPHA and sen.slope < 0 else
                                           "increasing" if h.p <= ALPHA and sen.slope > 0 else "no trend")})
SM = pd.DataFrame(rows)
TS2 = TS.merge(SM, on="Capital", how="outer")
save_table(TS2, "TableS7_1_tau_sign_and_municipal_series", index=False)
SER = pd.DataFrame({m: SERIES.get(m) or {} for m in CAPS}).sort_index()
SER.index = SER.index.astype(int)
save_table(SER.sort_index(), "TableS7_2_municipal_mean_series")
RB = []
for m in ok:
    r = {"Capital": lab(m)}
    for t in TESTS:
        r[f"{t}: degradation (%)"] = STATS[m][t]["neg"]
        r[f"{t}: improvement (%)"] = STATS[m][t]["pos"]
    r["Median lag-1 autocorrelation"] = STATS[m]["r1_median"]
    r["Pixels with r1 > 0.3 (%)"] = STATS[m]["r1_pct_gt03"]
    RB.append(r)
RB = save_table(pd.DataFrame(RB), "TableS8_1_tests_and_autocorrelation", index=False)
LV = save_table(pd.DataFrame({"Capital": [lab(m) for m in ok], "Mean HU-EEQI": [STATS[m]["mean_HU"] for m in ok],
                              "Mean temporal SD": [STATS[m]["mean_SD"] for m in ok],
                              "Mean Sen slope (yr⁻¹)": [STATS[m]["mean_sen"] for m in ok],
                              "Mean filled years per pixel": [STATS[m]["mean_n_filled"] for m in ok]}),
                "TableS7_3_mean_sd_and_filling", index=False)
so = pd.read_csv(SOCIO)
so["Capital"] = [lab1(m) if m in STATS else lab(m) for m in so.municipio]
so = so.merge(T1, on="Capital")
SP = []
for y, yl in [("Significant degradation (%)", "degradation"), ("Significant improvement (%)", "improvement")]:
    for x, xl in [("density_2022_hab_km2", "Population density 2022"), ("growth_1991_2022_pct", "Relative growth 1991–2022 (%)"),
                  ("pop_2022", "Population 2022")]:
        rho, p = spearmanr(so[y], so[x])
        SP.append({"Trend class": yl, "Indicator": xl, "Spearman ρ": rho, "p": p, "n": len(so)})
SP = save_table(pd.DataFrame(SP), "TableS9_1_spearman_demographics", index=False)
save_table(so[["Capital", "area_km2_ibge", "pop_1991", "pop_2022", "density_2022_hab_km2", "growth_1991_2022_pct",
               "Significant degradation (%)", "Significant improvement (%)"]], "TableS9_2_demographic_indicators", index=False)
print("tabelas ok", flush=True)

# ---------------------------------------------------------------------------------------------------
# 5) Figuras 3–11 (layout do script 16 do RSEI) e figuras suplementares
# ---------------------------------------------------------------------------------------------------
from matplotlib.patches import Patch
from figure_style import (plt, CM, LANDSCAPE_W_CM as WIDTH_CM, LANDSCAPE_H_CM as MAX_HEIGHT_CM, FS, FS_SMALL,
                          FIG_GROUPS, CMAP_TREND, NORM_TREND, CMAP_SIG, NORM_SIG, CMAP_SD, NORM_SD, CMAP_RSEI,
                          C_NEG, C_NULL, C_POS, C_NS, SD_COLORS, add_scale_bar, set_geo_aspect)


def read(m, key):
    with rasterio.open(os.path.join(RDIR, f"{slug(m)}_{key}.tif")) as src:
        a = src.read(1).astype("float32")
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        b = src.bounds
    a[~np.isfinite(a)] = np.nan
    return a, [b.left, b.right, b.bottom, b.top]


def valid_extent(a, ext, pad=0.01):
    rows_ = np.where(np.isfinite(a).any(1))[0]; cols = np.where(np.isfinite(a).any(0))[0]
    h, w = a.shape; dx = (ext[1] - ext[0]) / w; dy = (ext[3] - ext[2]) / h
    x0, x1 = ext[0] + cols[0] * dx, ext[0] + (cols[-1] + 1) * dx
    y1, y0 = ext[3] - rows_[0] * dy, ext[3] - (rows_[-1] + 1) * dy
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    return [x0 - px, x1 + px, y0 - py, y1 + py]


TITLES = ["Kendall's τ sign", "Significant trend\n(Hamed–Rao, p ≤ 0.05)", "Mean HU-EEQI", "Median HU-EEQI",
          "Standard deviation\nof HU-EEQI"]
LEFT, LABEL_W, GAP, LEGCOL = 0.05, 0.5, 0.1, 3.3
HEAD, LEG, ROWGAP = 0.75, 0.45, 0.5
PANEL = (WIDTH_CM - LEFT - LABEL_W - 4 * GAP - LEGCOL) / 5
PANEL_H = (MAX_HEIGHT_CM - HEAD - LEG - 2 * ROWGAP) / 3
FIGS = {}
for fig_no, cities in FIG_GROUPS.items():
    n = len(cities)
    H = HEAD + n * PANEL_H + (n - 1) * ROWGAP + LEG
    fig = plt.figure(figsize=(WIDTH_CM * CM, H * CM))
    fx = lambda cm: cm / WIDTH_CM
    fy = lambda cm: cm / H
    for i, city in enumerate(cities):
        y = H - HEAD - (i + 1) * PANEL_H - i * ROWGAP
        fig.text(fx(LEFT + 0.2), fy(y + PANEL_H / 2), f"{city} ({UF[city]})", rotation=90, ha="center", va="center",
                 fontsize=FS, fontweight="bold")
        if city not in READY:
            fig.text(fx(LEFT + LABEL_W + 2.5 * (PANEL + GAP)), fy(y + PANEL_H / 2), "Trend product pending",
                     ha="center", va="center", fontsize=FS, color="0.4")
            if i == 0:
                for j in range(5):
                    fig.text(fx(LEFT + LABEL_W + j * (PANEL + GAP) + PANEL / 2), fy(H - 0.12), TITLES[j], ha="center",
                             va="top", fontsize=FS, fontweight="bold")
            continue
        tau, ext = read(city, "tau"); p, _ = read(city, "p_mk" if city in FALLBACK else "p_hr")
        mean, _ = read(city, "mean"); med, _ = read(city, "median"); sd, _ = read(city, "sd")
        vext = valid_extent(tau, ext)
        bnd = gpd.GeoSeries([MUN[city]]).intersection(box(vext[0], vext[2], vext[1], vext[3]))
        cls = np.where(np.isnan(tau), np.nan, np.where(tau < 0, 0, np.where(tau > 0, 2, 1)))
        sig = np.where(np.isnan(tau), np.nan, np.where((p <= ALPHA) & (tau < 0), 0, np.where((p <= ALPHA) & (tau > 0), 2, 1)))
        sdc = np.where(np.isnan(sd), np.nan, np.where(sd < 0.05, 0, np.where(sd <= 0.10, 1, 2)))
        panels = [(cls, CMAP_TREND, NORM_TREND), (sig, CMAP_SIG, NORM_SIG), (mean, CMAP_RSEI, None),
                  (med, CMAP_RSEI, None), (sdc, CMAP_SD, NORM_SD)]
        for j, (arr, cmap, nrm) in enumerate(panels):
            x = LEFT + LABEL_W + j * (PANEL + GAP)
            ax = fig.add_axes([fx(x), fy(y), fx(PANEL), fy(PANEL_H)])
            kw = dict(norm=nrm) if nrm is not None else dict(vmin=0, vmax=1)
            ax.imshow(arr, extent=ext, cmap=cmap, interpolation="nearest", **kw)
            bnd.boundary.plot(ax=ax, color="#333333", linewidth=0.35)
            ax.set_xlim(vext[0], vext[1]); ax.set_ylim(vext[2], vext[3]); set_geo_aspect(ax, vext)
            ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values():
                s.set_visible(False)
            if i == 0:
                fig.text(fx(x + PANEL / 2), fy(H - 0.12), TITLES[j], ha="center", va="top", fontsize=FS, fontweight="bold")
            if j == 0:
                add_scale_bar(ax, vext)
    lx = LEFT + LABEL_W + 5 * PANEL + 4 * GAP + 0.35
    lw = LEGCOL - 0.4

    def legend_at(top, handles, title):
        lax = fig.add_axes([fx(lx), fy(H - top - 2.0), fx(lw), fy(2.0)]); lax.axis("off")
        lax.legend(handles=handles, title=title, loc="upper left", frameon=False, fontsize=FS_SMALL,
                   title_fontsize=FS_SMALL, handlelength=1.1, handleheight=0.9, borderaxespad=0, labelspacing=0.3,
                   alignment="left")

    edge = dict(edgecolor="#666666", linewidth=0.3)
    legend_at(HEAD + 0.1, [Patch(facecolor=C_NEG, label="Negative", **edge), Patch(facecolor=C_NULL, label="Null", **edge),
                           Patch(facecolor=C_POS, label="Positive", **edge)], "Trend direction (τ)")
    legend_at(HEAD + 2.1, [Patch(facecolor=C_NEG, label="Degradation", **edge), Patch(facecolor=C_NS, label="Not significant", **edge),
                           Patch(facecolor=C_POS, label="Improvement", **edge)], "Hamed–Rao (p ≤ 0.05)")
    fig.text(fx(lx), fy(H - HEAD - 4.25), "Mean / median HU-EEQI", ha="left", va="top", fontsize=FS_SMALL)
    cax = fig.add_axes([fx(lx), fy(H - HEAD - 4.95), fx(lw - 0.2), fy(0.25)])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=CMAP_RSEI, norm=plt.Normalize(0, 1)), cax=cax, orientation="horizontal",
                      ticks=[0, 0.5, 1.0])
    cb.outline.set_linewidth(0.4); cb.ax.tick_params(labelsize=FS_SMALL, width=0.4, length=2)
    fig.text(fx(lx), fy(H - HEAD - 5.55), "0 = low, 1 = high", ha="left", va="top",
             fontsize=FS_SMALL, linespacing=1.2)
    legend_at(HEAD + 6.5, [Patch(facecolor=SD_COLORS[0], label="< 0.05 (low)", **edge),
                           Patch(facecolor=SD_COLORS[1], label="0.05–0.10 (moderate)", **edge),
                           Patch(facecolor=SD_COLORS[2], label="> 0.10 (high)", **edge)], "Standard deviation")
    out = os.path.join(FIG, f"Figure_{fig_no}_HU-EEQI_trends.png")
    salvar(fig, out, dpi=DPI); salvar(fig, out.replace(".png", ".svg")); plt.close(fig)
    FIGS[fig_no] = (out, cities)
    print(f"Figura {fig_no} ok", flush=True)

# Figura S7.1 — séries municipais médias com reta de Sen
fig, axs = plt.subplots(7, 4, figsize=(17.4 * CM, 23.4 * CM), sharex=True)
for ax, m in zip(axs.flat, CAPS):
    s = SER[m].dropna()
    ax.plot(s.index, s.values, color="#2c7fb8", lw=0.9, marker="o", ms=1.6)
    r = SM[SM.Capital == lab(m)]
    if len(r):
        r = r.iloc[0]
        x = np.asarray(s.index, float) - float(s.index[0]); med_ = np.median(s.values - r["Sen slope (yr⁻¹)"] * x)
        col = "#c51b29" if r["Trend (Hamed–Rao)"] == "decreasing" else "#1a9641" if r["Trend (Hamed–Rao)"] == "increasing" else "0.5"
        ax.plot(s.index, med_ + r["Sen slope (yr⁻¹)"] * x, color=col, lw=1.0, ls="--")
        ax.set_title(f"{m} ({UF[m]}) p={r['p (Hamed–Rao)']:.3f}", fontsize=6.5, pad=2)
    ax.tick_params(labelsize=6); ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(Y0 - 1, Y1 + 1); ax.set_xticks([2000, 2010, 2020])
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
for ax in axs.flat[len(CAPS):]:
    ax.set_visible(False)
fig.supylabel("Municipal mean HU-EEQI (urban domain)", fontsize=8)
fig.tight_layout(h_pad=0.8, w_pad=1.2)
F_S7 = os.path.join(FIG, "FigureS7_1_municipal_mean_series.png"); salvar(fig, F_S7, dpi=DPI); plt.close(fig)
# Figura S7.2 — barras de degradação/melhora (Hamed–Rao) por capital
t = T1.sort_values("Significant degradation (%)")
fig, ax = plt.subplots(figsize=(17.4 * CM, 12 * CM))
yy = np.arange(len(t))
ax.barh(yy, -t["Significant degradation (%)"], color=C_NEG, label="Significant degradation")
ax.barh(yy, t["Significant improvement (%)"], color=C_POS, label="Significant improvement")
ax.set_yticks(yy); ax.set_yticklabels(t.Capital, fontsize=6.5); ax.axvline(0, color="k", lw=0.5)
ax.set_xlabel("% of the urban domain (Hamed–Rao, p ≤ 0.05); degradation to the left"); ax.legend(fontsize=7, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
F_S72 = os.path.join(FIG, "FigureS7_2_degradation_improvement_by_capital.png"); salvar(fig, F_S72, dpi=DPI, ); plt.close(fig)
# Figura S8.1 — % significativo por teste
fig, ax = plt.subplots(figsize=(17.4 * CM, 7 * CM))
sigs = pd.DataFrame({t: [STATS[m][t]["neg"] + STATS[m][t]["pos"] for m in ok] for t in TESTS}, index=[lab(m) for m in ok]).dropna()
sigs.plot.box(ax=ax, color=dict(boxes="#2c7fb8", whiskers="0.4", medians="#c51b29", caps="0.4"))
ax.set_ylabel("% of the urban domain with a significant trend"); ax.spines[["top", "right"]].set_visible(False)
F_S8 = os.path.join(FIG, "FigureS8_1_significance_by_test.png"); salvar(fig, F_S8, dpi=DPI, ); plt.close(fig)
print("figuras suplementares ok", flush=True)

# ---------------------------------------------------------------------------------------------------
# 6) Documentos .docx
# ---------------------------------------------------------------------------------------------------
import docx
from docx.shared import Cm, Pt
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH


def new_doc(title, landscape=False):
    D = docx.Document(); st = D.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
    s = D.sections[0]
    if landscape:
        s.orientation = WD_ORIENT.LANDSCAPE; s.page_width, s.page_height = Cm(29.7), Cm(21.0)
    else:
        s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(1.8)
    D.add_heading(title, 1)
    return D


def para(D, text, lead=None, size=10):
    p = D.add_paragraph()
    if lead:
        r = p.add_run(lead); r.bold = True; r.font.size = Pt(size)
    r = p.add_run(text); r.font.size = Pt(size)
    return p


def table(D, t, label, caption, fmt="{:.2f}"):
    para(D, caption, f"{label}. ", size=9)
    tb = D.add_table(rows=1, cols=len(t.columns)); tb.style = "Light Grid Accent 1"
    for j, c in enumerate(t.columns):
        tb.rows[0].cells[j].text = str(c)
    for _, row in t.iterrows():
        cs = tb.add_row().cells
        for j, v in enumerate(row):
            cs[j].text = ("" if (isinstance(v, float) and not np.isfinite(v)) else
                          (f"{v:.2e}" if isinstance(v, (float, np.floating)) and 0 < abs(v) < 1e-3 else
                           fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)))
    for r_ in tb.rows:
        for c_ in r_.cells:
            for p_ in c_.paragraphs:
                for run in p_.runs:
                    run.font.size = Pt(7.5)
    D.add_paragraph()


def figure(D, path, label, caption, width=16.5):
    D.add_picture(path, width=Cm(width)); D.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    para(D, caption, f"{label}. ", size=9)


FB_TXT = (f" For {', '.join(FALLBACK)} (marked with *), the trend product has an incomplete series (one year missing "
          "in the gap-filled collection), for which the Hamed–Rao and TFPW tests are not computed; the tie-corrected "
          "Mann–Kendall test is used instead until the series is completed." if FALLBACK else "")
PEND_TXT = (f" Trend products were not yet available for {', '.join(PENDING)}, which is therefore omitted." if PENDING else "")
DATA_TXT = (f"Pixel-wise trends of the gap-filled annual HU-EEQI v6 series ({Y0}–{Y1}, n = 26 years in every pixel) "
            "computed in Google Earth Engine (asset TRENDS_HU-EEQI_v6): Mann–Kendall original, tie-corrected, Hamed–Rao "
            "(1998) variance-corrected and trend-free pre-whitening (TFPW; Yue and Wang 2002) tests, Kendall's τ and "
            f"Sen's slope; significance level {ALPHA}. The principal test is Hamed–Rao. Areas are computed from the 30-m "
            "pixel area within the fixed urban analysis domain inside the official municipal boundary (IBGE)." + FB_TXT + PEND_TXT)

# Tabela 1
D = new_doc("Table 1. HU-EEQI trend classes by state capital")
cap1 = (f"Percentage of the urban analysis domain of each Brazilian state capital with statistically significant "
        f"degradation (τ < 0, Hamed–Rao p ≤ {ALPHA}), no significant trend and statistically significant improvement "
        f"(τ > 0, p ≤ {ALPHA}) of the HU-EEQI over {Y0}–{Y1} (gap-filled series, n = 26 annual values per pixel), "
        "computed at 30 m within the official municipal boundaries. The shares of negative and positive τ irrespective "
        "of significance and the results of the other tests are given in Tables S7.1 and S8.1." + FB_TXT + PEND_TXT)
table(D, T1, "Table 1", cap1)
D.save(os.path.join(DOC, "Table1_HU-EEQI_trend_classes.docx"))
# Figuras 3–11
D = new_doc("Figures 3–11. HU-EEQI trends by state capital", landscape=True)
for k, (fig_no, (png, cities)) in enumerate(FIGS.items()):
    if k:
        D.add_page_break()
    D.add_picture(png, width=Cm(23.4)); D.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    sc = [f"{c} {int(FR.loc[c].scale_m)} m" for c in cities if c in READY and int(FR.loc[c].scale_m) != 30]
    para(D, (f"Spatiotemporal patterns of the HU-EEQI over {Y0}–{Y1} for three Brazilian state capitals: "
             f"{', '.join(f'{c}-{UF[c]}' for c in cities)}. For each capital, the five panels show, from left to right: "
             "the HU-EEQI trend (sign of Kendall's τ), the statistically significant trend (Hamed–Rao, p ≤ 0.05; "
             "non-significant pixels in grey) and the temporal mean, median and standard deviation of the HU-EEQI within "
             "the fixed urban analysis domain (white: outside the domain); the line is the official municipal boundary. "
             "Maps are framed on the main contiguous urban patches and rendered at 30 m"
             + (f" except {'; '.join(sc)}." if sc else ".")
             + ("".join(f" The trend product of {c} is pending." for c in cities if c not in READY))
             + ("".join(f" For {c}, significance is from the tie-corrected Mann–Kendall test (Hamed–Rao not available: "
                        "incomplete series)." for c in cities if c in FALLBACK))),
         f"Figure {fig_no}. ", size=9)
D.save(os.path.join(DOC, "Figures_3_11_HU-EEQI_trends.docx"))
# S7
D = new_doc("Supplementary Material S7. Trend direction, municipal series and temporal variability")
para(D, DATA_TXT, "Data and methods. ")
para(D, "For each capital, the shares of negative and positive Kendall's τ irrespective of significance (the trend-sign "
        "maps of Figures 3–11) were computed over the urban domain. The municipal mean HU-EEQI of each year (mean over the "
        "urban domain of the gap-filled series) was tested with the original Mann–Kendall and the Hamed–Rao tests, and its "
        "magnitude estimated with Sen's slope (pymannkendall; Hussain and Mahmud 2019).", "Municipal series. ")
nd = (SM["Trend (Hamed–Rao)"] == "decreasing").sum(); ni = (SM["Trend (Hamed–Rao)"] == "increasing").sum()
para(D, f"At the municipal scale, the mean HU-EEQI series showed a significant monotonic trend under the Hamed–Rao test "
        f"in {nd + ni} of {len(SM)} capitals ({nd} decreasing, {ni} increasing); Sen's slopes ranged from "
        f"{SM['Sen slope (yr⁻¹)'].min():.4f} to {SM['Sen slope (yr⁻¹)'].max():+.4f} HU-EEQI units per year. The municipal "
        f"mean of the temporal standard deviation ranged from {LV['Mean temporal SD'].min():.3f} to "
        f"{LV['Mean temporal SD'].max():.3f}.", "Results. ")
table(D, TS2, "Table S7.1", "Shares of the urban domain with negative, null and positive Kendall's τ (irrespective of significance) and trend of the municipal mean HU-EEQI series (Mann–Kendall, Hamed–Rao and Sen's slope), per capital.", fmt="{:.3f}")
table(D, LV, "Table S7.2", "Municipal means (urban domain) of the temporal mean, standard deviation and Sen slope of the HU-EEQI and mean number of gap-filled years per pixel.", fmt="{:.4f}")
figure(D, F_S7, "Figure S7.1", "Annual municipal mean HU-EEQI (urban domain, gap-filled series) of each capital, with Sen's slope line (red: significant decrease; green: significant increase; grey: no significant trend; Hamed–Rao, p ≤ 0.05). The annual values are in TableS7_2_municipal_mean_series.csv.")
figure(D, F_S72, "Figure S7.2", "Share of the urban domain with significant degradation (left) and improvement (right) of the HU-EEQI per capital (Hamed–Rao, p ≤ 0.05).")
D.save(os.path.join(DOC, "S7_Trend_direction_municipal_series.docx"))
# S8
mk_s = np.nanmean([STATS[m]["MK original"]["neg"] + STATS[m]["MK original"]["pos"] for m in ok])
hr_s = np.nanmean([STATS[m]["Hamed–Rao"]["neg"] + STATS[m]["Hamed–Rao"]["pos"] for m in ok])
tf_s = np.nanmean([STATS[m]["TFPW"]["neg"] + STATS[m]["TFPW"]["pos"] for m in ok])
mt_s = np.nanmean([STATS[m]["MK ties"]["neg"] + STATS[m]["MK ties"]["pos"] for m in ok])
D = new_doc("Supplementary Material S8. Robustness of the trends to the test and to serial autocorrelation")
para(D, DATA_TXT, "Data and methods. ")
para(D, "Unlike a sample-based assessment, all pixels of the urban domain were evaluated with the four tests computed in "
        "Earth Engine. Serial autocorrelation was summarized by the lag-1 autocorrelation of the Sen-detrended residuals "
        "(r1) of each pixel.", "Approach. ")
para(D, f"The mean share of the urban domain with a significant trend was {mk_s:.1f}% under the original Mann–Kendall "
        f"test, {mt_s:.1f}% with the tie correction, {hr_s:.1f}% under Hamed–Rao and {tf_s:.1f}% under TFPW. The median r1 "
        f"ranged from {RB['Median lag-1 autocorrelation'].min():.2f} to {RB['Median lag-1 autocorrelation'].max():.2f} across "
        f"capitals, and on average {RB['Pixels with r1 > 0.3 (%)'].mean():.1f}% of the pixels had r1 > 0.3.", "Results. ")
table(D, RB, "Table S8.1", "Shares of the urban domain with significant degradation and improvement under each test, median lag-1 autocorrelation of the Sen-detrended residuals and share of pixels with r1 > 0.3, per capital.", fmt="{:.1f}")
figure(D, F_S8, "Figure S8.1", "Distribution across capitals of the share of the urban domain with a significant trend under each test.")
D.save(os.path.join(DOC, "S8_Trend_robustness_tests_autocorrelation.docx"))
# S9
D = new_doc("Supplementary Material S9. Trend classes and demographic indicators")
para(D, "Spearman rank correlations between the share of the urban domain with significant degradation (or improvement) "
        "of the HU-EEQI (Hamed–Rao; Table 1) and population density in 2022, relative population growth between 1991 and "
        "2022 and total population in 2022 (IBGE censuses and municipal area; the same indicators used for the RSEI). "
        f"Given the sample size (n = {len(so)}) and the observational design, they are exploratory associations only.", "Data and methods. ")
table(D, SP, "Table S9.1", "Spearman correlations between HU-EEQI trend classes and demographic indicators.", fmt="{:.3f}")
D.save(os.path.join(DOC, "S9_Spearman_demographics.docx"))
# Texto de resultados
reg = {"North": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Northeast": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
       "Southeast": ["ES", "MG", "RJ", "SP"], "South": ["PR", "RS", "SC"], "Central-West": ["DF", "GO", "MS", "MT"]}
T1r = T1.assign(uf=[c.split("-")[-1] for c in T1.Capital])
T1r["region"] = T1r.uf.map({u: r for r, us in reg.items() for u in us})
rg = T1r.groupby("region")[["Significant degradation (%)", "Significant improvement (%)", "No significant trend (%)"]].mean()
w = T1["Urban domain area (km²)"]
wd, wi = (T1["Significant degradation (%)"] * w).sum() / w.sum(), (T1["Significant improvement (%)"] * w).sum() / w.sum()
top_d = T1.sort_values("Significant degradation (%)", ascending=False)
top_i = T1.sort_values("Significant improvement (%)", ascending=False)
D = new_doc("Results text — HU-EEQI trends (draft with generated numbers)")
para(D, f"Table 1 summarizes the area shares of the three trend classes within the urban domain. Statistically significant "
        f"degradation (τ < 0, Hamed–Rao p ≤ {ALPHA}) covered more than one third of the urban domain in "
        f"{(T1['Significant degradation (%)'] > 100 / 3).sum()} of the {len(T1)} capitals and more than half in "
        f"{(T1['Significant degradation (%)'] > 50).sum()} (largest shares: "
        + ", ".join(f"{r.Capital} ({r['Significant degradation (%)']:.1f}%)" for _, r in top_d.head(5).iterrows())
        + "). Significant improvement was most extensive in "
        + ", ".join(f"{r.Capital} ({r['Significant improvement (%)']:.1f}%)" for _, r in top_i.head(5).iterrows())
        + (lambda k: f" and exceeded the degraded share in {k} capital{'s' if k != 1 else ''}.")(
            int((T1['Significant improvement (%)'] > T1['Significant degradation (%)']).sum())) + f" The class without a significant trend occupied between {T1['No significant trend (%)'].min():.1f}% and "
        f"{T1['No significant trend (%)'].max():.1f}% of the urban domain. Averaged by macro-region, the share of significant "
        "degradation was "
        + ", ".join(f"{r} {v:.1f}%" for r, v in rg["Significant degradation (%)"].sort_values(ascending=False).items())
        + "; significant improvement was "
        + ", ".join(f"{r} {v:.1f}%" for r, v in rg["Significant improvement (%)"].sort_values(ascending=False).items())
        + f". Weighted by urban-domain area, {wd:.1f}% of the combined urban domain showed significant degradation and "
        f"{wi:.1f}% significant improvement; the unweighted means were {T1['Significant degradation (%)'].mean():.1f}% and "
        f"{T1['Significant improvement (%)'].mean():.1f}%." + FB_TXT + PEND_TXT, "3.x Trends. ")
para(D, f"The mean share of the urban domain with a significant trend was {mk_s:.1f}% with the original Mann–Kendall test and "
        f"{hr_s:.1f}% with the Hamed–Rao correction (TFPW {tf_s:.1f}%); on average "
        f"{RB['Pixels with r1 > 0.3 (%)'].mean():.1f}% of the pixels had a lag-1 autocorrelation of the residuals above 0.3 "
        f"(Table S8.1). At the municipal scale, the mean HU-EEQI series showed a significant trend in {nd + ni} of {len(SM)} "
        f"capitals ({nd} decreasing, {ni} increasing; Table S7.1, Figure S7.1). "
        + " ".join(f"The share of significant {r['Trend class']} was {'' if r['p'] <= 0.05 else 'not significantly '}"
                   f"correlated with {r['Indicator'].lower()} (ρ = {r['Spearman ρ']:.2f}, p = {r['p']:.2f})."
                   for _, r in SP.iterrows()) + " (Table S9.1).", "3.y Robustness. ")
D.save(os.path.join(DOC, "Results_text_HU-EEQI_trends.docx"))
json.dump({"ready": READY, "pending": PENDING, "fallback": {m: UPD[m] for m in FALLBACK}},
          open(os.path.join(TAB, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("pendentes:", PENDING, "| com MK no lugar do Hamed–Rao:", FALLBACK)
print("concluído")
