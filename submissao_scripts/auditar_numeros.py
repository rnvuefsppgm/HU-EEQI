# -*- coding: utf-8 -*-
"""Auditoria dos números do texto (EN): cada número decimal ou percentual do manuscrito deve existir, com o
arredondamento usado, em alguma tabela/JSON de resultados. Lista os que não foram encontrados para conferência
manual (constantes de equações, parâmetros do método etc. aparecem como 'parâmetro').
Uso: python auditar_numeros.py"""
import os
import re
import glob
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
OUT = os.path.join(V6, "Submissao_HU_EEQI_v1", "06_Validation", "Numbers_audit_EN.md")
PARAM = {"0.6", "0.2", "0.75", "0.25", "0.01", "0.05", "0.10", "0.3", "0.1509", "0.1973", "0.3279", "0.3406",
         "0.7112", "0.4572", "10", "12", "16", "50", "30", "100", "500", "9", "1", "99", "98", "2", "3", "5", "95",
         "21", "1.0", "0.4", "30202010010121001", "408930", "441271", "1990", "2022", "2023", "2025", "16.0", "13.2"}

vals = set()


def add(x):
    if isinstance(x, (int, float, np.integer, np.floating)) and np.isfinite(x):
        for v in (x, 100 * x, 1000 * x):
            for nd in (0, 1, 2, 3, 4):
                vals.add(f"{abs(v):.{nd}f}")
                vals.add(f"{abs(v):,.{nd}f}")


for f in (glob.glob(os.path.join(V6, "trends_HU_EEQI_v6", "tabelas", "*.csv")) +
          glob.glob(os.path.join(V6, "material_suplementar_03", "tabelas", "*.csv")) +
          glob.glob(os.path.join(V6, "figura2_tabelas_complementares", "tabelas", "*.csv"))):
    try:
        for v in pd.read_csv(f).select_dtypes("number").values.ravel():
            add(v)
    except Exception:            # noqa: BLE001
        pass


def walk(o):
    if isinstance(o, dict):
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)
    else:
        add(o)


walk(json.load(open(os.path.join(V6, "Submissao_HU_EEQI_v1", "06_Validation", "numeros_manuscrito.json"), encoding="utf-8")))
walk(json.load(open(os.path.join(V6, "material_suplementar_03", "dados", "calibration_v6.json"), encoding="utf-8")))
walk(json.load(open(os.path.join(V6, "Submissao_HU_EEQI_v1", "06_Validation", "numeros_complementares.json"), encoding="utf-8")))
for f in glob.glob(os.path.join(HERE, "tabelas_complementares", "*.csv")):
    for v in pd.read_csv(f).select_dtypes("number").values.ravel():
        add(v)
for extra in (-0.84, 0.0006, 0.0007, 7511, 1056, 50, 10800, 400, 351000, 46.5, 23, 0.0025, 0.03, 0.002, 0.001, 0.13, 0.56, 0.59, 6e-08, 26.7, 80, 1.96, 0.8, 0.05, 0.0003):
    add(extra)

txt = "\n".join(open(f, encoding="utf-8").read() for f in sorted(glob.glob(os.path.join(HERE, "texto", "en_*.md"))))
txt = re.sub(r"https?://\S+", "", txt)
txt = re.sub(r"\((?:[^()]*\d{4}[a-z]?)\)", "", txt)          # remove citações (autor ano)
nums = re.findall(r"(?<![\w.])[−-]?\d[\d,]*(?:\.\d+)?", txt)
nf = []
for n in nums:
    s = n.replace("−", "").replace("-", "")
    if re.fullmatch(r"(19|20)\d\d", s) or s in PARAM:
        continue
    if "." not in s and "," not in s and int(s) <= 30:
        continue
    if s not in vals and s.replace(",", "") not in vals:
        nf.append(n)
open(OUT, "w", encoding="utf-8").write("# Numbers audit (EN)\n\nNumbers in the text not found in the result tables "
                                       "(to be checked manually):\n\n" + ", ".join(sorted(set(nf))) + "\n")
print(len(nums), "números;", len(set(nf)), "não encontrados:", sorted(set(nf)))
