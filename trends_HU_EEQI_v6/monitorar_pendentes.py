# -*- coding: utf-8 -*-
"""Monitora o asset TRENDS_HU-EEQI_v6 e roda gerar_trends_HU_EEQI_v6.py de novo (o cache refaz só o que mudou) quando:
  - uma capital pendente (sem tendência) aparece; ou
  - o asset de uma capital com série incompleta (sem Hamed–Rao; ex.: Teresina sem 2016) é refeito.
Lê tabelas/status.json. Verifica a cada INTERVALO_MIN minutos, por até MAX_HORAS horas.
Uso: python monitorar_pendentes.py"""
import os
import sys
import json
import time
import subprocess
import ee

HERE = os.path.dirname(os.path.abspath(__file__))
T_ASSET = "projects/mapbiomas-caatinga-cloud04/assets/TRENDS_HU-EEQI_v6"
INTERVALO_MIN, MAX_HORAS = 15, 72
ee.Initialize(project=os.environ.get("EE_PROJECT"))
status = lambda: json.load(open(os.path.join(HERE, "tabelas", "status.json"), encoding="utf-8"))


def rodar():
    r = subprocess.run([sys.executable, os.path.join(HERE, "gerar_trends_HU_EEQI_v6.py")], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=os.environ.copy())
    open(os.path.join(HERE, "log_execucao.txt"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    print(time.strftime("%d/%m %H:%M"), "reprocessado (código", r.returncode, ")", flush=True)


st = status()
print("pendentes:", st["pending"], "| série incompleta:", list(st.get("fallback", {})), flush=True)
t0 = time.time()
while (st["pending"] or st.get("fallback")) and time.time() - t0 < MAX_HORAS * 3600:
    novo = []
    try:
        info = ee.ImageCollection(T_ASSET).map(lambda im: ee.Feature(None, {"c": im.get("city"), "id": im.get("system:id")})).getInfo()["features"]
        ids = {f["properties"]["c"]: f["properties"]["id"] for f in info}
        novo += [c for c in st["pending"] if c in ids]
        for c, upd in st.get("fallback", {}).items():
            if c in ids and ee.data.getAsset(ids[c]).get("updateTime", "") != upd:
                novo.append(c)
    except Exception as e:
        print(time.strftime("%H:%M"), "erro ao consultar:", str(e)[:100], flush=True)
    print(time.strftime("%d/%m %H:%M"), "novidades:", novo or "nenhuma", flush=True)
    if novo:
        time.sleep(120)          # dá tempo do asset terminar de ser indexado
        rodar()
        st = status()
        print("pendentes:", st["pending"] or "nenhuma", "| série incompleta:", list(st.get("fallback", {})) or "nenhuma", flush=True)
        continue
    time.sleep(INTERVALO_MIN * 60)
print("fim do monitoramento | pendentes:", st["pending"] or "nenhuma", "| série incompleta:",
      list(st.get("fallback", {})) or "nenhuma", flush=True)
