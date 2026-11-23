# -*- coding: utf-8 -*-
"""
Mapas anuais do HU-EEQI v6 (série PREENCHIDA, 2000–2025) para as 27 capitais.
Adaptado de 19_figure_s1_annual_rsei_maps.py (sessão RSEI_Paper_luana_Review), com o mesmo desenho:
  Parte A: baixa cada imagem anual (HU_EEQI + fill_type) recortada no limite municipal oficial
           (IBGE, data/Capitais.shp) em escala de visualização (30 m nas capitais pequenas; mais
           grossa nas grandes, até ~1,5 milhão de pixels por mapa).
  Parte B: monta 1 página por capital (26 painéis + barra de cores, paleta RdYlGn, 0–1) e um .docx
           com todas as páginas.
Diferenças em relação ao RSEI:
  - Fonte: projects/mapbiomas-caatinga-cloud04/assets/HU-EEQI_v6_filled (série sem lacunas no domínio).
  - Enquadramento: o HU-EEQI só existe no domínio urbano fixo; cada mapa é enquadrado na extensão
    dos pixels com dado (margem de ~1 km) dentro do município. Isso evita mapas quase vazios nos
    municípios grandes (ex.: Porto Velho) e exclui ilhas oceânicas sem dado (Vitória).
  - Sem reorientação de PC1 e sem substituição por ano vizinho: a série já vem preenchida. Cada
    painel mostra a % de pixels preenchidos naquele ano (fill_type > 0); ano sem imagem = "no image".
Uso: python mapas_anuais_HU_EEQI_v6_filled.py
  variáveis de ambiente opcionais: EE_PROJECT (projeto para processar; padrão <your-project>),
  ONLY_CITY="Aracaju,Recife" e ONLY_YEARS="2000,2012" (testes), MAX_PIX (padrão 1.5e6).
"""
import os
import sys
import csv
import math
import json
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from rasterio.windows import from_bounds
import ee
import geopandas as gpd
from shapely.geometry import box

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
ASSET = "projects/mapbiomas-caatinga-cloud04/assets/HU-EEQI_v6_filled"
SHP = os.environ.get("CAPITAIS_SHP", os.path.join(HERE, "data", "Capitais.shp"))
RDIR = os.path.join(HERE, "rasters")
FDIR = os.path.join(HERE, "figuras")
YEARS = list(range(2000, 2026))
MAX_PIX = float(os.environ.get("MAX_PIX", 1.5e6))
ONLY_CITY = [c.strip() for c in os.environ.get("ONLY_CITY", "").split(",") if c.strip()]
ONLY_YEARS = [int(y) for y in os.environ.get("ONLY_YEARS", "").split(",") if y.strip()]
MARGIN_DEG = 0.003           # ~300 m de margem ao redor das manchas urbanas mapeadas (zoom)
PATCH_MIN_SHARE = 0.05       # manchas urbanas contínuas com < 5% do domínio não entram no enquadramento
PATCH_ALWAYS = 0.20          # manchas com >= 20% do domínio entram sempre
FRAME_GROW_MAX = 2.0         # manchas de 5–20% só entram se não aumentarem a caixa em mais de 2×
LANDSCAPE_ASPECT = 1.15      # largura/altura do enquadramento acima disso -> página na horizontal
DPI = 600                    # resolução das figuras
FRAME_INFO = {}
os.makedirs(RDIR, exist_ok=True)
os.makedirs(FDIR, exist_ok=True)


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
if ONLY_CITY:
    gdf = gdf[gdf.NM_MUN.isin(ONLY_CITY)]
col = ee.ImageCollection(ASSET)
info = col.map(lambda im: ee.Feature(None, {"id": im.get("system:id"), "city": im.get("city"),
                                            "year": im.get("year")})).getInfo()["features"]
info = [f["properties"] for f in info if f["properties"]["city"] in set(gdf.NM_MUN)]
if ONLY_YEARS:
    info = [p for p in info if int(p["year"]) in ONLY_YEARS]
have = {(p["city"], int(p["year"])) for p in info}
missing = sorted((c, y) for c in gdf.NM_MUN for y in (ONLY_YEARS or YEARS) if (c, y) not in have)
print(f"{len(info)} imagens no asset para {len(gdf)} capitais | ausentes: {missing or 'nenhuma'}", flush=True)


# ---- enquadramento: manchas urbanas principais (∩ município oficial) + margem -----------------
# O domínio urbano de algumas capitais tem núcleos distantes (ex.: distritos de Porto Velho a ~200 km da
# sede). Manchas contínuas (8-conectadas, a 300 m): parte da maior; inclui as com >= PATCH_ALWAYS do domínio
# e as com PATCH_MIN_SHARE–PATCH_ALWAYS que não aumentem a caixa em mais de FRAME_GROW_MAX vezes.
# Núcleos fora da caixa não aparecem no mapa; a % do domínio mostrada vai em enquadramento_mapas.csv.
def city_frame(mun):
    geom = gdf[gdf.NM_MUN == mun].geometry.iloc[0]
    gj = json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]
    eg = ee.Geometry(gj, "EPSG:4326", False)
    img = col.filter(ee.Filter.eq("city", mun)).first().select("HU_EEQI")
    vec = (img.mask().gt(0).selfMask().toInt()
           .reduceToVectors(geometry=eg, scale=300, geometryType="polygon", eightConnected=True,
                            maxPixels=1e10, bestEffort=True)
           .map(lambda f: f.set("a", f.geometry().area(100))))
    gj_all = vec.getInfo()["features"]
    if not gj_all:
        frame, shown = geom, 100.0
    else:
        polys = gpd.GeoDataFrame({"a": [f["properties"]["a"] for f in gj_all]},
                                 geometry=gpd.GeoDataFrame.from_features(gj_all).geometry, crs=4326)
        tot = polys.a.sum()
        polys = polys.sort_values("a", ascending=False)
        bx = lambda b: (b[2] - b[0]) * (b[3] - b[1])
        b_ = list(polys.geometry.iloc[0].bounds)
        for k in range(1, len(polys)):
            sh, pb = polys.a.iloc[k] / tot, polys.geometry.iloc[k].bounds
            if sh < PATCH_MIN_SHARE:
                continue
            nb = [min(b_[0], pb[0]), min(b_[1], pb[1]), max(b_[2], pb[2]), max(b_[3], pb[3])]
            if sh >= PATCH_ALWAYS or bx(nb) <= FRAME_GROW_MAX * bx(b_):
                b_ = nb
        inside = polys.geometry.apply(lambda g_: box(*b_).contains(g_.representative_point()))
        shown = 100.0 * polys.a[inside].sum() / tot
        frame = geom.intersection(box(b_[0] - MARGIN_DEG, b_[1] - MARGIN_DEG, b_[2] + MARGIN_DEG, b_[3] + MARGIN_DEG))
    FRAME_INFO[mun] = round(shown, 1)
    fj = json.loads(gpd.GeoSeries([frame]).to_json())["features"][0]["geometry"]
    area = gpd.GeoSeries([frame], crs=4326).to_crs(5880).area.iloc[0]
    scale = max(30, int(math.ceil(math.sqrt(area / MAX_PIX) / 10.0)) * 10)
    return ee.Geometry(fj, "EPSG:4326", False), scale, tuple(frame.bounds)


FRAME = {}
for m in sorted(gdf.NM_MUN):
    FRAME[m] = city_frame(m)
    print(f"  enquadramento {m}: escala {FRAME[m][1]} m | {FRAME_INFO[m]}% do domínio no mapa", flush=True)
with open(os.path.join(HERE, "enquadramento_mapas.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["city", "scale_m", "pct_dominio_no_mapa", "lon_min", "lat_min", "lon_max", "lat_max"])
    for m in sorted(FRAME):
        w.writerow([m, FRAME[m][1], FRAME_INFO[m]] + [round(v, 5) for v in FRAME[m][2]])
if os.environ.get("FRAME_ONLY") == "1":      # só o enquadramento (diagnóstico)
    sys.exit(0)


# ---- Parte A: download (6 em paralelo; pula o que já existe) ----------------------------------
def fetch(p):
    mun, ano = p["city"], int(p["year"])
    path = os.path.join(RDIR, f"{slug(mun)}_{ano}.tif")
    geom, scale, _ = FRAME[mun]
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with rasterio.open(path) as src:
                res_m = src.res[0] * 111319.49
                src.read(1, window=rasterio.windows.Window(0, 0, 1, 1))
            if abs(res_m - scale) < 1:
                return 0                               # já baixado na escala certa
        except Exception:
            pass                                       # arquivo incompleto/corrompido: baixa de novo
    
    img = ee.Image(p["id"]).select(["HU_EEQI", "fill_type"]).clip(geom).toFloat()
    err = ""
    for attempt in range(5):
        try:
            url = img.getDownloadURL({"region": geom.bounds(1), "scale": scale, "format": "GEO_TIFF",
                                      "crs": "EPSG:4326"})
            with urllib.request.urlopen(url, timeout=600) as r:
                data = r.read()
            open(path + ".part", "wb").write(data)
            os.replace(path + ".part", path)   # grava inteiro ou nada
            return 1
        except Exception as e:
            err = str(e)
            time.sleep(20 * (attempt + 1))
    print("FALHOU", mun, ano, err[:150], flush=True)
    return 0


n_done = 0
with ThreadPoolExecutor(6) as ex:
    for k in ex.map(fetch, info):
        n_done += k
        if k and n_done % 50 == 0:
            print(n_done, "baixadas", flush=True)
print("download concluído:", n_done, "novas", flush=True)

# ---- Parte B: páginas por capital + resumo + .docx ---------------------------------------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import docx
from docx.shared import Cm
from figure_style import CM, WIDTH_CM, FS, FS_SMALL, set_geo_aspect, add_scale_bar


def read_map(mun, ano):
    """(HU_EEQI, % preenchido, extensão) ou None se o arquivo não existe ou não tem dado."""
    path = os.path.join(RDIR, f"{slug(mun)}_{ano}.tif")
    if not os.path.exists(path):
        return None
    with rasterio.open(path) as src:
        win = from_bounds(*FRAME[mun][2], transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        a = src.read(1, window=win).astype("float32")
        ft = src.read(2, window=win).astype("float32")
        nod = src.nodata
        b = rasterio.windows.bounds(win, src.transform)
        b = type("B", (), {"left": b[0], "bottom": b[1], "right": b[2], "top": b[3]})
    if nod is not None:
        a[a == nod] = np.nan
        ft[ft == nod] = np.nan
    a[~np.isfinite(a)] = np.nan
    ok = np.isfinite(a)
    if not ok.any():
        return None
    pct = 100.0 * np.mean(ft[ok] > 0) if np.isfinite(ft[ok]).any() else float("nan")
    return a, pct, [b.left, b.right, b.bottom, b.top]


rows_csv, pages = [], []
years_page = ONLY_YEARS or YEARS
for _, row in gdf.sort_values("NM_MUN").iterrows():
    mun, uf = row.NM_MUN, row.SIGLA_UF
    fb = FRAME[mun][2]
    asp = (fb[2] - fb[0]) * math.cos(math.radians((fb[1] + fb[3]) / 2)) / max(fb[3] - fb[1], 1e-9)
    land = asp > LANDSCAPE_ASPECT
    W, H = (25.7, 17.4) if land else (WIDTH_CM, 23.4)
    cols, nrow, gap, top, bottom = (7, 4, 0.1, 1.0, 0.3) if land else (5, 6, 0.1, 1.0, 0.3)
    pw = (W - 0.2 - (cols - 1) * gap) / cols
    ph = (H - top - bottom - (nrow - 1) * 0.8) / nrow
    fig = plt.figure(figsize=(W * CM, H * CM))
    ext0 = None
    for k, ano in enumerate(years_page):
        r_, c_ = divmod(k, cols)
        ax = fig.add_axes([(0.1 + c_ * (pw + gap)) / W, (H - top - (r_ + 1) * ph - r_ * 0.8) / H,
                           pw / W, ph / H])
        m = read_map(mun, ano)
        if m is not None:
            a, pct, ext = m
            ax.imshow(a, extent=ext, cmap="RdYlGn", vmin=0, vmax=1, interpolation="nearest")
            set_geo_aspect(ax, ext)
            if ext0 is None:
                ext0 = ext
                add_scale_bar(ax, ext, fontsize=6)
            lab = str(ano)
            v = a[np.isfinite(a)]
            rows_csv.append({"city": mun, "uf": uf, "year": ano, "scale_m": FRAME[mun][1],
                             "pct_filled": round(pct, 2), "n_pixels": int(v.size),
                             "p5": round(float(np.percentile(v, 5)), 4), "median": round(float(np.median(v)), 4),
                             "p95": round(float(np.percentile(v, 95)), 4)})
        else:
            ax.text(0.5, 0.5, "no image", ha="center", va="center", fontsize=FS_SMALL, transform=ax.transAxes)
            lab = str(ano)
            rows_csv.append({"city": mun, "uf": uf, "year": ano, "scale_m": FRAME[mun][1], "pct_filled": "",
                             "n_pixels": 0, "p5": "", "median": "", "p95": ""})
        ax.set_title(lab, fontsize=FS_SMALL, pad=2)
        ax.set_xticks([]); ax.set_yticks([])
        for s_ in ax.spines.values():
            s_.set_visible(False)
    r_, c_ = divmod(len(years_page), cols)
    cax = fig.add_axes([(0.1 + c_ * (pw + gap) + 0.15 * pw) / W,
                        (H - top - (r_ + 1) * ph - r_ * 0.8 + 0.4 * ph) / H,
                        0.7 * pw / W, 0.12 * ph / H])
    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal", ticks=[0, 0.5, 1])
    cb.set_label("HU-EEQI", fontsize=FS_SMALL); cb.ax.tick_params(labelsize=6, width=0.4, length=2)
    cb.outline.set_linewidth(0.4)
    fig.text(0.1 / W, (H - 0.25) / H,
             f"{mun} ({uf}). Annual HU-EEQI, {years_page[0]}–{years_page[-1]}",
             fontsize=FS + 1, fontweight="bold", va="top")
    png = os.path.join(FDIR, f"HU_EEQI_v6_filled_{slug(mun)}.png")
    salvar(fig, png, dpi=DPI)
    plt.close(fig)
    pages.append((mun, uf, png, land))
    print("página", mun, "(horizontal)" if land else "(vertical)", flush=True)

with open(os.path.join(HERE, "resumo_mapas_HU_EEQI_v6_filled.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]))
    w.writeheader(); w.writerows(rows_csv)

D = docx.Document()
sec = D.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(1.6)
sec.top_margin = sec.bottom_margin = Cm(1.8)
D.add_heading("Annual HU-EEQI maps (v6)", 1)
D.add_paragraph(
    "Annual maps of the Hybrid Urban Environmental-Equity Quality Index (HU-EEQI, version 6) for the 27 Brazilian "
    f"state capitals, {years_page[0]}–{years_page[-1]}, from the gap-filled series (asset HU-EEQI_v6_filled), within the "
    "official municipal boundaries (IBGE). Values range from 0 (lowest) to 1 (highest). The index exists only within the "
    "fixed urban analysis domain (GHS-SMOD urban or suburban in 2000–2025, excluding permanent water). "
    "Missing pixel-years were filled pixel by pixel (linear interpolation in time, nearest year at the ends of the "
    "record, mean of the pixels with data within a 2-km window in the same year, or the capital median). Each map is "
    "framed on the contiguous urban patches holding at least 5% of the capital's domain (about 300 m margin); small, "
    "isolated urban nuclei outside that frame are not shown. Maps are ordered alphabetically by capital. The rendering "
    "scale is 30 m for most capitals and coarser for the largest urban areas."
    + (f" Capital-years without an image in the asset: {', '.join(f'{c} {y}' for c, y in missing)}." if missing else ""))
from docx.enum.section import WD_ORIENT, WD_SECTION
for mun, uf, png, land in pages:
    s_ = D.add_section(WD_SECTION.NEW_PAGE)
    s_.orientation = WD_ORIENT.LANDSCAPE if land else WD_ORIENT.PORTRAIT
    s_.page_width, s_.page_height = (Cm(29.7), Cm(21.0)) if land else (Cm(21.0), Cm(29.7))
    s_.left_margin = s_.right_margin = Cm(1.6 if not land else 1.8)
    s_.top_margin = s_.bottom_margin = Cm(1.8 if not land else 1.6)
    D.add_picture(png, width=Cm(25.7 if land else 17.4))
    k_ = [p_[0] for p_ in pages].index(mun) + 1
    falta = [y for c, y in missing if c == mun]
    cap = D.add_paragraph()
    cap.add_run(f"Figure {k_}. ").bold = True
    cap.add_run(
        f"Annual HU-EEQI maps of {mun} ({uf}), {years_page[0]}–{years_page[-1]} (HU-EEQI v6). "
        "Values from 0 (lowest) to 1 (highest) within the fixed urban analysis domain; white = outside the domain. "
        f"Frame: main contiguous urban patches ({FRAME_INFO[mun]:.0f}% of the capital's urban domain shown); "
        f"rendering scale {FRAME[mun][1]} m."
        + (f" No image in the asset for {', '.join(map(str, falta))}." if falta else ""))
    for r_ in cap.runs:
        r_.font.size = docx.shared.Pt(9)
D.save(os.path.join(HERE, "Mapas_anuais_HU_EEQI_v6_filled.docx"))
print("ausentes:", missing)
print("concluído")
