# -*- coding: utf-8 -*-
"""Completa a pasta de submissão: página de título, carta ao editor (Urban Ecosystems), figuras do texto
principal (PNG 600 dpi e SVG), Tabela 1 (docx, CSV, XLSX) e README da pasta. O suplementar é montado por
montar_suplementar.py e os manuscritos por montar_manuscrito.py.
Uso: python montar_submissao.py"""
import os
import copy
import shutil
import docx
import pandas as pd
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
SUB = os.path.join(V6, "Submissao_HU_EEQI_v1")
RSEI = r"D:\Luana\Submissão_Paper_2\Review\Revised_Submission\01_Manuscript\Main_text_UEC_formatted_v4_Clean.docx"
TR = os.path.join(V6, "trends_HU_EEQI_v6")
TITLE = ("Beyond greenness: a hybrid environmental-equity index reveals widespread urban quality decline across "
         "Brazil's 27 state capitals (2000–2025)")
FONT = "Times New Roman"


def fmt(p, size=11, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p.alignment = align
    p.paragraph_format.space_after = Pt(8)
    for r in p.runs:
        r.font.name, r.font.size, r.bold = FONT, Pt(size), bold


def title_page():
    src = docx.Document(RSEI)
    d = docx.Document(RSEI)
    body = d.element.body
    sect = copy.deepcopy(body.sectPr)
    for el in list(body):
        body.remove(el)
    body.append(sect)
    for rid, rel in list(d.part.rels.items()):
        if rel.reltype.endswith("/image"):
            d.part.drop_rel(rid)
    for p in src.paragraphs[:8]:
        body.sectPr.addprevious(copy.deepcopy(p._p))
    t = d.paragraphs[0]
    for r in t.runs[1:]:
        r._element.getparent().remove(r._element)
    t.runs[0].text = TITLE
    out = os.path.join(SUB, "01_Manuscript", "Title_page_HU-EEQI.docx")
    d.save(out)
    return out


LETTER = [
    "22 November 2026",
    "Dear Professors Chi Yung Jim and Michael McKinney,\nEditors-in-Chief\nUrban Ecosystems",
    f"We are pleased to submit our manuscript entitled “{TITLE}” for consideration for publication as an original "
    "research article in Urban Ecosystems.",
    "Remote sensing indices of urban ecological quality, such as the Remote Sensing Ecological Index (RSEI), are widely "
    "used to monitor cities, but they are rescaled scene by scene, ignore air quality and say nothing about how "
    "environmental quality is distributed among residents. In this manuscript we propose the Hybrid Urban "
    "Environmental-Equity Quality Index (HU-EEQI), which combines Landsat greenness, wetness and dryness with an air "
    "temperature-based heat index (ERA5-Land) and satellite aerosol optical depth (MODIS MAIAC), normalized with fixed "
    "bounds pooled over all cities and years and weighted objectively (CRITIC), and couples this environmental "
    "quality with population-weighted local equity and justice components. We computed the index annually at 30 m "
    "for the urban areas of all 27 Brazilian state capitals over 2000–2025 in an open Google Earth Engine workflow "
    "and tested pixel-wise trends with autocorrelation-corrected Mann–Kendall tests and Sen's slope.",
    "The manuscript offers three main contributions. First, it provides the first nationally comparable, long-term "
    "assessment of urban environmental quality for Brazil's capitals, on a scale that is directly comparable among "
    "cities and years. Second, it shows a widespread decline: statistically significant degradation covered on average "
    "43.7% of the urban domain of each capital and more than half of it in nine capitals, the municipal mean index "
    "declined significantly in 18 capitals and increased in none, and the gap between southern and northern "
    "capitals widened; rising regional heat stress dominated the decline in the North and interior, which already had "
    "the lowest levels, while losses of vegetation and local equity contributed elsewhere. "
    "Third, it subjects the index to an unusually complete set of diagnostics (exact reproducibility, temporal "
    "consistency and sensor-transition breaks, a land-cover falsification test and a Monte Carlo uncertainty "
    "analysis), clarifying what such indices can and cannot reveal, including the need for intra-urban vulnerability "
    "data for environmental-justice components.",
    "The study fits the scope of Urban Ecosystems by linking urbanization, urban heat, vegetation, air quality and "
    "the social distribution of environmental quality, and by offering a reproducible tool to prioritize green "
    "infrastructure and climate-adaptation interventions in cities of the Global South. It complements our "
    "manuscript on the RSEI of the same capitals, currently under review in Urban Ecosystems, which addresses the "
    "ecological condition of the whole municipal territory; the present manuscript is a distinct study with a new "
    "index, a different analysis unit (the urban domain), different data and different research questions. All code "
    "is openly available at https://github.com/rnvuefsppgm/HU-EEQI.",
    "We confirm that this manuscript is original, has not been published previously, and is not under consideration "
    "for publication elsewhere. All authors have approved the submitted version and agree with its submission to "
    "Urban Ecosystems. There are no conflicts of interest to declare.",
    "Thank you for considering our manuscript. We hope that it will be of interest to the readership of Urban "
    "Ecosystems.",
    "Sincerely,",
    "Prof. Dr. Rodrigo Nogueira Vasconcelos\nCorresponding author, on behalf of all authors\nPostgraduate Program in "
    "Modeling in Earth and Environmental Sciences (PPGM)\nState University of Feira de Santana (UEFS), Bahia, Brazil\n"
    "E-mail: rnv@uefs.br | <your-account>",
]


def letter():
    d = docx.Document()
    s = d.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2.5)
    for k, t in enumerate(LETTER):
        p = d.add_paragraph(t)
        fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT if k in (0, 1, len(LETTER) - 1, len(LETTER) - 2) else WD_ALIGN_PARAGRAPH.JUSTIFY)
    out = os.path.join(SUB, "05_Cover_Letter", "Cover_Letter_HU-EEQI_Urban_Ecosystems.docx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    d.save(out)
    return out


def figures():
    png = os.path.join(SUB, "02_Figures", "PNG_600dpi")
    svg = os.path.join(SUB, "02_Figures", "SVG_Editable")
    os.makedirs(png, exist_ok=True)
    os.makedirs(svg, exist_ok=True)
    src = {1: os.path.join(V6, "figura1_fluxograma", "figuras", "Figure_1_workflow"),
           2: os.path.join(V6, "figura2_tabelas_complementares", "figuras", "Figure_2_location")}
    for n in range(3, 12):
        src[n] = os.path.join(TR, "figuras", f"Figure_{n}_HU-EEQI_trends")
    for n, base in src.items():
        shutil.copy2(base + ".png", os.path.join(png, f"Figure_{n}.png"))
        shutil.copy2(base + ".svg", os.path.join(svg, f"Figure_{n}.svg"))


def table1():
    d3 = os.path.join(SUB, "03_Tables")
    os.makedirs(d3, exist_ok=True)
    t = pd.read_csv(os.path.join(TR, "tabelas", "Table1_trend_class_shares_HamedRao.csv"))
    t.columns = ["Capital", "Significant degradation (%)", "No significant trend (%)", "Significant improvement (%)",
                 "Urban domain (km²)"]
    t.round(2).to_csv(os.path.join(d3, "Table_1.csv"), index=False, encoding="utf-8-sig")
    t.round(2).to_excel(os.path.join(d3, "Table_1.xlsx"), index=False)
    d = docx.Document()
    p = d.add_paragraph()
    r = p.add_run("Table 1. "); r.bold = True
    p.add_run("Percentage of the urban domain of each Brazilian state capital with statistically significant degradation "
              "(τ < 0, p ≤ 0.05), no significant trend (p > 0.05) and statistically significant improvement (τ > 0, "
              "p ≤ 0.05) of the HU-EEQI over 2000–2025 (Hamed–Rao variance-corrected Mann–Kendall test), and area of "
              "the urban domain. *Teresina: tie-corrected Mann–Kendall test (incomplete series).")
    tb = d.add_table(rows=1, cols=5)
    tb.style = "Table Grid"
    for j, c in enumerate(t.columns):
        tb.rows[0].cells[j].text = c
    for _, row in t.iterrows():
        c = tb.add_row().cells
        c[0].text = row.iloc[0]
        for j in (1, 2, 3):
            c[j].text = f"{row.iloc[j]:.1f}"
        c[4].text = f"{row.iloc[4]:,.0f}"
    for para in [p] + [pp for rw in tb.rows for cc in rw.cells for pp in cc.paragraphs]:
        for rr in para.runs:
            rr.font.name, rr.font.size = FONT, Pt(9)
    d.save(os.path.join(d3, "Table_1.docx"))


if __name__ == "__main__":
    print(title_page())
    print(letter())
    figures()
    table1()
    print("figuras e tabela 1 copiadas")
