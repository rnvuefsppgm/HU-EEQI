# -*- coding: utf-8 -*-
"""Monta os documentos Word dos mapas anuais a partir das figuras já geradas, com UMA legenda para
todas as figuras (texto em legenda_paper.md, seção English) e uma identificação curta por página.
  - Mapas_anuais_HU_EEQI_v6_filled.docx       -> figuras de 600 dpi (figuras/)
  - Mapas_anuais_HU_EEQI_v6_filled_leve.docx  -> cópias de 300 dpi em JPEG (figuras_300dpi/), para compartilhar
Uso: python montar_docx.py
"""
import os
import re
import glob
import geopandas as gpd
import docx
from docx.shared import Cm, Pt
from docx.enum.section import WD_ORIENT, WD_SECTION
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FIG, FIG300 = os.path.join(HERE, "figuras"), os.path.join(HERE, "figuras_300dpi")
os.makedirs(FIG300, exist_ok=True)
Image.MAX_IMAGE_PIXELS = None

md = open(os.path.join(HERE, "legenda_paper.md"), encoding="utf-8").read()
legenda = re.search(r"## English \(manuscript\)\n(.+?)\n\n", md, re.S).group(1).strip()
corpo = legenda.split("**Figure S1.**", 1)[1].strip()

gdf = gpd.read_file(os.path.join(HERE, "data", "Capitais.shp"))
uf = dict(zip(gdf.NM_MUN, gdf.SIGLA_UF))
slug = lambda s: "".join(c if c.isalnum() else "_" for c in __import__("unicodedata").normalize(
    "NFKD", s).encode("ascii", "ignore").decode().lower()).strip("_")
caps = sorted(uf)
pngs = [(m, os.path.join(FIG, f"HU_EEQI_v6_filled_{slug(m)}.png")) for m in caps]
faltam = [m for m, p in pngs if not os.path.exists(p)]
assert not faltam, f"figuras ausentes: {faltam}"

# cópias de 300 dpi (metade da resolução) em JPEG de alta qualidade
for m, p in pngs:
    out = os.path.join(FIG300, os.path.basename(p).replace(".png", ".jpg"))
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(p):
        im = Image.open(p).convert("RGB")
        im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save(out, "JPEG", quality=92, dpi=(300, 300))


def build(path, leve):
    D = docx.Document()
    st = D.styles["Normal"]; st.font.name = "Arial"; st.font.size = Pt(10)
    s0 = D.sections[0]
    s0.page_width, s0.page_height = Cm(21.0), Cm(29.7)
    s0.left_margin = s0.right_margin = Cm(1.6); s0.top_margin = s0.bottom_margin = Cm(1.8)
    D.add_heading("Annual HU-EEQI maps of the 27 Brazilian state capitals (2000–2025)", 1)
    p = D.add_paragraph(); r = p.add_run("Figure S1. "); r.bold = True
    p.add_run(corpo)
    for k, (m, png) in enumerate(pngs, 1):
        img = png.replace(FIG, FIG300).replace(".png", ".jpg") if leve else png
        w, h = Image.open(img).size
        land = w > h
        s_ = D.add_section(WD_SECTION.NEW_PAGE)
        s_.orientation = WD_ORIENT.LANDSCAPE if land else WD_ORIENT.PORTRAIT
        s_.page_width, s_.page_height = (Cm(29.7), Cm(21.0)) if land else (Cm(21.0), Cm(29.7))
        s_.left_margin = s_.right_margin = Cm(1.8 if land else 1.6)
        s_.top_margin = s_.bottom_margin = Cm(1.6 if land else 1.8)
        D.add_picture(img, width=Cm(25.7 if land else 17.4))
        c = D.add_paragraph(); r = c.add_run(f"Figure S1 ({k}/{len(pngs)}). "); r.bold = True
        c.add_run(f"{m} ({uf[m]}).")
        for r in c.runs:
            r.font.size = Pt(9)
    D.save(path)
    print(os.path.basename(path), f"{os.path.getsize(path) / 2**20:.0f} MB")


build(os.path.join(HERE, "Mapas_anuais_HU_EEQI_v6_filled_leve.docx"), leve=True)
build(os.path.join(HERE, "Mapas_anuais_HU_EEQI_v6_filled.docx"), leve=False)
