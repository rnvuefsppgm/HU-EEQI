# -*- coding: utf-8 -*-
"""Coleta no GEE, para cada imagem (capital-ano) de HU-EEQI_v6_filled, a contagem de pixels do domínio
por tipo de preenchimento (fill_type 0-4), os sensores usados (sensor_flag) e as médias de n_obs,
n_obs_thermal, n_aod, AQ_filled e HEAT_filled. Grava tabelas/cache_preenchimento_gee.csv.
Refaz só as capitais que faltam no cache (apague o CSV para refazer tudo).
Uso: EE_PROJECT=<projeto> python coletar_preenchimento_gee.py"""
import os
import json
import concurrent.futures as cf
import ee
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tabelas", "cache_preenchimento_gee.csv")
FILLED = "projects/mapbiomas-caatinga-cloud04/assets/HU-EEQI_v6_filled"
ee.Initialize(project=os.environ.get("EE_PROJECT"))

col = ee.ImageCollection(FILLED)
cities = sorted(set(col.aggregate_array("city").getInfo()))
done = set(pd.read_csv(OUT)["city"]) if os.path.exists(OUT) else set()
todo = [c for c in cities if c not in done]
print(len(cities), "capitais;", len(todo), "a coletar", flush=True)

MEAN_BANDS = ["n_obs", "n_obs_thermal", "n_aod", "AQ_filled", "HEAT_filled"]


def stats(img):
    img = ee.Image(img)
    proj = img.select("HU_EEQI").projection()
    scale = ee.Number(img.get("export_scale_m"))
    kw = dict(geometry=img.geometry(), crs=proj, scale=scale, maxPixels=1e10, tileScale=4)
    hist = img.select(["fill_type", "sensor_flag"]).toInt().reduceRegion(ee.Reducer.frequencyHistogram(), **kw)
    mean = img.select(MEAN_BANDS).toFloat().reduceRegion(ee.Reducer.mean(), **kw)
    return ee.Feature(None, {"city": img.get("city"), "year": img.get("year"),
                             "year_observed": img.get("year_observed"), "scale_m": scale,
                             "fill_hist": hist.get("fill_type"), "sensor_hist": hist.get("sensor_flag"),
                             **{b: mean.get(b) for b in MEAN_BANDS}})


def run(city, lote=4):
    """Uma capital, em lotes de poucos anos (o GEE limita as agregações simultâneas do projeto)."""
    import time
    cc = col.filter(ee.Filter.eq("city", city))
    anos = sorted(cc.aggregate_array("year").getInfo())
    feats = []
    for i in range(0, len(anos), lote):
        sub = cc.filter(ee.Filter.inList("year", anos[i:i + lote]))
        for k in range(8):
            try:
                feats += ee.FeatureCollection(sub.map(stats)).getInfo()["features"]
                break
            except ee.EEException as e:
                if k == 7:
                    raise
                print("  nova tentativa", city, anos[i], str(e)[:50], flush=True)
                time.sleep(15 * (k + 1))
    rows = []
    for f in feats:
        p = f["properties"]
        fh = {int(float(k)): v for k, v in (p.pop("fill_hist") or {}).items()}
        sh = {int(float(k)): v for k, v in (p.pop("sensor_hist") or {}).items()}
        p["n_pixels"] = sum(fh.values())
        for t in range(5):
            p[f"fill_{t}"] = fh.get(t, 0)
        p["sensor_hist"] = json.dumps(sh)
        rows.append(p)
    return city, rows


def gravar(rows):                              # grava a cada capital (o que já veio não se perde)
    df = pd.DataFrame(rows)
    if os.path.exists(OUT):
        df = pd.concat([pd.read_csv(OUT), df], ignore_index=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.sort_values(["city", "year"]).to_csv(OUT, index=False)


with cf.ThreadPoolExecutor(1) as ex:
    for fut in cf.as_completed([ex.submit(run, c) for c in todo]):
        city, rows = fut.result()
        gravar(rows)
        print(" ok", city, len(rows), "anos", flush=True)
print("gravado:", OUT)
