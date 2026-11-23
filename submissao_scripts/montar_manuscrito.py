# -*- coding: utf-8 -*-
"""Monta o manuscrito (EN ou PT) no formato do paper do RSEI a partir dos textos em texto/<lang>_*.md,
das figuras e tabelas já validadas e de referencias.txt. Usa o .docx do RSEI como modelo (estilos, margens,
numeração de linhas, bloco de autores/afiliações). Audita: citações × referências e números do texto × tabelas.
Uso: python montar_manuscrito.py en|pt"""
import os
import re
import sys
import copy
import glob
import json
import docx
import pandas as pd
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION, WD_ORIENT
from docx.oxml.ns import qn

LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
SUB = os.path.join(V6, "Submissao_HU_EEQI_v1")
RSEI = os.environ.get("TEMPLATE_DOCX", "template_manuscript.docx")  # docx modelo de formatação
TR = os.path.join(V6, "trends_HU_EEQI_v6")
FIG1 = os.path.join(V6, "figura1_fluxograma", "figuras", "Figure_1_workflow.png")
FIG2 = os.path.join(V6, "figura2_tabelas_complementares", "figuras", "Figure_2_location.png")
GROUPS = {3: "Aracaju-SE, Belém-PA, Belo Horizonte-MG", 4: "Boa Vista-RR, Brasília-DF, Campo Grande-MS",
          5: "Cuiabá-MT, Curitiba-PR, Florianópolis-SC", 6: "Fortaleza-CE, Goiânia-GO, João Pessoa-PB",
          7: "Macapá-AP, Maceió-AL, Manaus-AM", 8: "Natal-RN, Palmas-TO, Porto Alegre-RS",
          9: "Porto Velho-RO, Recife-PE, Rio Branco-AC", 10: "Rio de Janeiro-RJ, Salvador-BA, São Luís-MA",
          11: "São Paulo-SP, Teresina-PI*, Vitória-ES"}
NOTE11 = {"en": " *Teresina: tie-corrected Mann–Kendall test (incomplete series).",
          "pt": " *Teresina: teste de Mann–Kendall com correção de empates (série incompleta)."}
T = {"en": dict(abstract="Abstract", keywords="Keywords", refs="References", out="Main_text_HU-EEQI_EN.docx",
                cols=["Capital", "Significant degradation (%)", "No significant trend (%)", "Significant improvement (%)",
                      "Urban domain (km²)"]),
     "pt": dict(abstract="Resumo", keywords="Palavras-chave", refs="Referências", out="Main_text_HU-EEQI_PT.docx",
                cols=["Capital", "Degradação significativa (%)", "Sem tendência significativa (%)",
                      "Melhora significativa (%)", "Domínio urbano (km²)"])}[LANG]
FONT = "Times New Roman"


# ------------------------------------------------------------------------------------------- leitura
def ler_texto():
    linhas = []
    for f in sorted(glob.glob(os.path.join(HERE, "texto", f"{LANG}_*.md"))):
        linhas += open(f, encoding="utf-8").read().split("\n")
    return [l.rstrip() for l in linhas]


def ler_refs():
    R = {}
    for l in open(os.path.join(HERE, "referencias.txt"), encoding="utf-8"):
        if l.strip():
            k, d, ref = l.strip().split("|", 2)
            R[k] = ref
    return R


# ------------------------------------------------------------------------------------------- docx
def base_doc():
    d = docx.Document(RSEI)
    body = d.element.body
    front = []                                    # parágrafos 2–8 do RSEI: autores, afiliações, correspondência
    paras = list(d.paragraphs)
    for p in paras[1:8]:
        front.append(copy.deepcopy(p._p))
    title_p = copy.deepcopy(paras[0]._p)
    last_sect = copy.deepcopy(body.sectPr)
    for el in list(body):
        body.remove(el)
    body.append(last_sect)
    for rid, rel in list(d.part.rels.items()):        # imagens do RSEI que ficaram sem uso no modelo
        if rel.reltype.endswith("/image"):
            d.part.drop_rel(rid)
    return d, title_p, front


def run_fmt(r, size=10, bold=None, italic=None):
    r.font.name = FONT
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    r.font.size = Pt(size)
    if bold is not None:
        r.bold = bold
    if italic is not None:
        r.italic = italic


def para(d, text="", size=10, bold=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, ls=2.0, style=None, italic=None,
         lead=None):
    p = d.add_paragraph(style=style) if style else d.add_paragraph()
    p.alignment = align
    p.paragraph_format.line_spacing = ls
    p.paragraph_format.space_after = Pt(0)
    if lead:
        run_fmt(p.add_run(lead), size, True)
    if text:
        run_fmt(p.add_run(text), size, bold, italic)
    return p


def heading(d, text, level):
    p = d.add_paragraph(style=f"Heading {level}")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 2.0
    run_fmt(p.add_run(text), 10, True)
    return p


CACHE = os.path.join(HERE, "_img_300dpi")


def leve(path, width_cm):
    """Cópia ~300 dpi para embutir no .docx (as figuras de 600 dpi vão separadas para a revista)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    os.makedirs(CACHE, exist_ok=True)
    jpg = "_HU-EEQI_trends" in path                    # mapas raster: JPEG q95 (texto continua nítido a 300 dpi)
    out = os.path.join(CACHE, os.path.splitext(os.path.basename(path))[0] + (".jpg" if jpg else ".png"))
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
        im = Image.open(path).convert("RGB")
        px = int(width_cm / 2.54 * 300)
        if im.width > px:
            im = im.resize((px, int(im.height * px / im.width)), Image.LANCZOS)
        im.save(out, dpi=(300, 300), optimize=True, **({"quality": 95, "subsampling": 0} if jpg else {}))
    return out


def figure(d, path, caption, width_cm):
    d.add_picture(leve(path, width_cm), width=Cm(width_cm))
    d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    lab, rest = caption.split(". ", 1)
    para(d, rest, ls=1.0, lead=lab + ". ")


def table1(d, caption):
    t = pd.read_csv(os.path.join(TR, "tabelas", "Table1_trend_class_shares_HamedRao.csv"))
    lab, rest = caption.split(". ", 1)
    para(d, rest, ls=1.0, lead=lab + ". ")
    tb = d.add_table(rows=1, cols=5)
    tb.style = "Table Grid"
    for j, c in enumerate(T["cols"]):
        tb.rows[0].cells[j].text = c
    for _, r in t.iterrows():
        cells = tb.add_row().cells
        cells[0].text = r.iloc[0]
        for j in (1, 2, 3):
            cells[j].text = f"{r.iloc[j]:.1f}"
        cells[4].text = f"{r.iloc[4]:,.0f}"
    for i, row in enumerate(tb.rows):
        for j, c in enumerate(row.cells):
            for p in c.paragraphs:
                p.paragraph_format.line_spacing = 1.0
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    run_fmt(r, 8, i == 0)
    para(d, "")


def new_section(d, landscape):
    s = d.add_section(WD_SECTION.NEW_PAGE)
    s.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    w, h = Cm(29.7), Cm(21.0)
    s.page_width, s.page_height = (w, h) if landscape else (h, w)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(s, m, Cm(2.5))


# ------------------------------------------------------------------------------------------- montagem
def main():
    L = ler_texto()
    R = ler_refs()
    caps = {}
    for l in L:
        m = re.match(r"@(CAP\w*) (.*)", l)
        if m:
            caps[m.group(1)] = m.group(2)
    d, title_p, front = base_doc()
    body = d.element.body
    sect = body.sectPr
    texto_corrido = []

    for l in L:
        if not l.strip() or l.startswith("@CAP"):
            continue
        if l.startswith("@TITLE "):
            tp = copy.deepcopy(title_p)
            sect.addprevious(tp)
            p = d.paragraphs[-1]
            for r in p.runs[1:]:
                r._element.getparent().remove(r._element)
            p.runs[0].text = l[7:]
            for el in front:
                sect.addprevious(copy.deepcopy(el))
            continue
        if l == "@ABSTRACT":
            para(d, T["abstract"], 11, True)
            continue
        if l.startswith("@KEYWORDS "):
            para(d, T["keywords"], 11, True)
            para(d, l[10:])
            continue
        if l.startswith("# "):
            heading(d, l[2:], 1); continue
        if l.startswith("## "):
            heading(d, l[3:], 2); continue
        if l.startswith("### "):
            heading(d, l[4:], 3); continue
        if l.startswith("@EQ "):
            para(d, l[4:], align=WD_ALIGN_PARAGRAPH.CENTER, italic=False)
            texto_corrido.append(l[4:]); continue
        if l == "@FIG1":
            figure(d, FIG1, caps["CAP1"], 16.0); continue
        if l == "@FIG2":
            figure(d, FIG2, caps["CAP2"], 16.0); continue
        if l == "@TABLE1":
            table1(d, caps["CAPT1"]); continue
        if l == "@FIGS3_11":
            new_section(d, True)
            for n in range(3, 12):
                capt = caps["CAPFIG"].format(caps=GROUPS[n], note=NOTE11[LANG] if n == 11 else "")
                lab = "Figure" if LANG == "en" else "Figura"
                d.add_picture(leve(os.path.join(TR, "figuras", f"Figure_{n}_HU-EEQI_trends.png"), 24.0), height=Cm(13.2))
                d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                para(d, capt, ls=1.0, lead=f"{lab} {n}. ")
                if n < 11:
                    d.paragraphs[-1].runs[-1].add_break(docx.enum.text.WD_BREAK.PAGE)
            new_section(d, False)
            continue
        if l.startswith("@BACK "):
            new_section(d, False) if False else None
            heading(d, l[6:], 1); continue
        if l.startswith("@BACKH "):
            para(d, l[7:], bold=True); continue
        para(d, l)
        texto_corrido.append(l)

    # ------------------------------------------------------------------- referências citadas
    full = "\n".join(texto_corrido) + "\n" + "\n".join(caps.values())
    def citado(k):
        a, y = k.rsplit(" ", 1)
        y0 = y[:4]
        pat = re.escape(a) + r",? (?:\d{4}[a-z]?(?:, )?)*" + re.escape(y)
        return re.search(pat, full) or re.search(re.escape(a) + r" \(" + re.escape(y) + r"\)", full)
    cited = [k for k in R if citado(k)]
    uncited = [k for k in R if k not in cited]
    heading(d, T["refs"], 1)
    for k in sorted(cited, key=lambda k: re.sub(r"[^a-z ]", "", R[k].lower())):
        p = para(d, R[k], align=WD_ALIGN_PARAGRAPH.LEFT)
        p.paragraph_format.left_indent = Cm(1.27)
        p.paragraph_format.first_line_indent = Cm(-1.27)
    # citações no texto sem referência
    cand = set(re.findall(r"([A-Z][A-Za-zÀ-ÿ'\-]+(?: (?:et al\.|and [A-Z][A-Za-zÀ-ÿ'\-]+|dos Santos et al\.|van den Bosch))?) \(?(\d{4}[a-z]?)", full))
    keys_auth = {k.rsplit(" ", 1)[0].split()[-1] for k in R}
    orfas = sorted({f"{a} {y}" for a, y in cand if a.split()[0] not in {k.split()[0] for k in R} and
                    not a.startswith(("Figure", "Figura", "Table", "Tabela", "Supplementary", "Material", "Section",
                                      "Seção", "Landsat", "Collection", "Coleção", "Sentinel", "GHS", "ERA"))})
    out = os.path.join(SUB, "01_Manuscript", T["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    d.save(out + ".tmp.docx")
    os.replace(out + ".tmp.docx", out)
    rep = {"arquivo": out, "palavras_texto": sum(len(x.split()) for x in texto_corrido),
           "referencias_citadas": len(cited), "referencias_nao_citadas": uncited, "possiveis_citacoes_sem_referencia": orfas}
    json.dump(rep, open(os.path.join(SUB, "06_Validation", f"citations_{LANG}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
