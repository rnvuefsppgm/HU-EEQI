# -*- coding: utf-8 -*-
"""Monta o material suplementar da submissão com a numeração final S1–S11 (mesma lógica de ordem do paper
do RSEI) a partir dos produtos já gerados, renomeando arquivos e trocando os rótulos dentro dos .docx
(Table/Figure Sx.y, Supplementary Material Sx e nomes de arquivo TableSx_y/FigureSx_y).
Numeração antiga -> nova:
  S1 mapas anuais -> S1 | S10 completude -> S2 | S11 calibração -> S3 | S7 direção da tendência -> S4
  S8 robustez -> S5 | S9 demografia -> S6 | S2 reprodutibilidade -> S7 | S3 consistência temporal -> S8
  S4 decomposição -> S9 | S5 MapBiomas -> S10 | S6 incerteza -> S11
Uso: python montar_suplementar.py"""
import os
import re
import shutil
import zipfile

V6 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(V6, "Submissao_HU_EEQI_v1", "04_Supplementary_Material")
MAP = {1: 1, 10: 2, 11: 3, 7: 4, 8: 5, 9: 6, 2: 7, 3: 8, 4: 9, 5: 10, 6: 11}
M3, TR, FT, MA = (os.path.join(V6, d) for d in ("material_suplementar_03", "trends_HU_EEQI_v6",
                                               "figura2_tabelas_complementares", "mapas_anuais_filled"))
DOCS = {  # nº antigo -> (docx de origem, nome novo sem número)
    10: (os.path.join(FT, "documentos", "S10_Data_completeness_gap_filling.docx"), "Data_completeness_gap_filling"),
    11: (os.path.join(FT, "documentos", "S11_Normalization_bounds_weights.docx"), "Normalization_bounds_weights"),
    7: (os.path.join(TR, "documentos", "S7_Trend_direction_municipal_series.docx"), "Trend_direction_municipal_series"),
    8: (os.path.join(TR, "documentos", "S8_Trend_robustness_tests_autocorrelation.docx"), "Trend_robustness_tests_autocorrelation"),
    9: (os.path.join(TR, "documentos", "S9_Spearman_demographics.docx"), "Spearman_demographics"),
    2: (os.path.join(M3, "documentos", "S2_Reproducibility_check.docx"), "Reproducibility_check"),
    3: (os.path.join(M3, "documentos", "S3_Temporal_consistency_common_signal_breaks.docx"), "Temporal_consistency_common_signal_breaks"),
    4: (os.path.join(M3, "documentos", "S4_Decomposition_of_changes.docx"), "Decomposition_of_changes"),
    5: (os.path.join(M3, "documentos", "S5_MapBiomas_falsification_test.docx"), "MapBiomas_falsification_test"),
    6: (os.path.join(M3, "documentos", "S6_Uncertainty_and_sensitivity.docx"), "Uncertainty_and_sensitivity"),
}
LABEL = re.compile(r"(?<![A-Za-z0-9])S(\d{1,2})(?=[.\s,;:)\-–_]|$)")
FILE = re.compile(r"(Table|Figure)S(\d{1,2})_")


def renum(txt):
    txt = FILE.sub(lambda m: f"{m.group(1)}S{MAP.get(int(m.group(2)), int(m.group(2)))}_", txt)
    return LABEL.sub(lambda m: f"S{MAP.get(int(m.group(1)), int(m.group(1)))}", txt)


def renum_docx(src, dst):
    """Troca os rótulos só dentro dos textos (w:t) do document.xml; imagens e estilos ficam iguais."""
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for it in zi.infolist():
            data = zi.read(it.filename)
            if it.filename == "word/document.xml":
                x = data.decode("utf-8")
                x = re.sub(r"(<w:t(?: [^>]*)?>)([^<]*)(</w:t>)", lambda m: m.group(1) + renum(m.group(2)) + m.group(3), x)
                data = x.encode("utf-8")
            zo.writestr(it, data)
    os.replace(tmp, dst)


TC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tabelas_complementares")
EXTRAS = {  # tabela complementar (análises da revisão) -> (pasta S, rótulo, legenda)
    "TableS5_2_panel_trends_HU_EQ_fixedE": ("S5_", "Table S5.2",
        "Share of the diagnostic-panel pixels (observed series with at least 20 years) with significant degradation "
        "and improvement (Hamed–Rao, p ≤ 0.05) for the HU-EEQI, for EQ alone and for the HU-EEQI with local equity "
        "(E) held at its pixel mean, by capital."),
    "TableS8_4_E_step_sensor_transition": ("S8_", "Table S8.4",
        "Mean local equity (E) in 2009–2011 and 2013–2015, its change across the Landsat sensor transition (ΔE) and "
        "the change in environmental quality (ΔEQ) over the same periods, by capital (diagnostic panel)."),
    "TableS9_3_change_decomposition_5yr_windows": ("S9_", "Table S9.3",
        "Exact decomposition of the change in ln HU-EEQI between the means of 2000–2004 and 2021–2025 into the "
        "contributions of each descriptor and component (α·w_i·Δ ln NI_i, β·Δ ln E, γ·Δ ln J), by capital "
        "(diagnostic panel)."),
}


def extras():
    import docx
    import pandas as pd
    from docx.shared import Pt
    for name, (pref, lab, cap) in EXTRAS.items():
        dd = [os.path.join(SUB, d) for d in os.listdir(SUB) if d.startswith(pref)][0]
        t = pd.read_csv(os.path.join(TC, name + ".csv"))
        os.makedirs(os.path.join(dd, "tables"), exist_ok=True)
        t.to_csv(os.path.join(dd, "tables", name + ".csv"), index=False, encoding="utf-8-sig")
        t.to_excel(os.path.join(dd, "tables", name + ".xlsx"), index=False)
        f = [os.path.join(dd, x) for x in os.listdir(dd) if x.endswith(".docx")][0]
        D = docx.Document(f)
        p = D.add_paragraph()
        r = p.add_run(lab + ". "); r.bold = True; r.font.size = Pt(9)
        r = p.add_run(cap); r.font.size = Pt(9)
        tb = D.add_table(rows=1, cols=len(t.columns))
        tb.style = "Light Grid Accent 1"
        for j, c in enumerate(t.columns):
            tb.rows[0].cells[j].text = str(c)
        for _, row in t.iterrows():
            cells = tb.add_row().cells
            for j, v in enumerate(row):
                cells[j].text = f"{v:.3f}" if isinstance(v, float) and abs(v) < 10 else (f"{v:.1f}" if isinstance(v, float) else str(v))
        for rw in tb.rows:
            for c in rw.cells:
                for pp in c.paragraphs:
                    for rr in pp.runs:
                        rr.font.size = Pt(7)
        D.save(f)


def main():
    if os.path.isdir(SUB):
        shutil.rmtree(SUB)
    os.makedirs(SUB)
    # S1: mapas anuais (docx leve, 300 dpi) + figuras de 600 dpi
    d1 = os.path.join(SUB, "S1_Annual_HU-EEQI_maps")
    os.makedirs(os.path.join(d1, "figures_600dpi"))
    shutil.copy2(os.path.join(MA, "Mapas_anuais_HU_EEQI_v6_filled_leve.docx"),
                 os.path.join(d1, "S1_Annual_HU-EEQI_maps.docx"))
    for f in sorted(os.listdir(os.path.join(MA, "figuras"))):
        if f.endswith(".png"):
            shutil.copy2(os.path.join(MA, "figuras", f),
                         os.path.join(d1, "figures_600dpi", f.replace("HU_EEQI_v6_filled_", "FigureS1_")))
    # S2–S11
    for old, (src, name) in DOCS.items():
        new = MAP[old]
        dd = os.path.join(SUB, f"S{new}_{name}")
        os.makedirs(dd)
        renum_docx(src, os.path.join(dd, f"S{new}_{name}.docx"))
        for folder in ("figuras", "tabelas"):
            base = os.path.join(os.path.dirname(os.path.dirname(src)), folder)
            for f in sorted(os.listdir(base)):
                m = FILE.match(f)
                if m and int(m.group(2)) == old and f.endswith((".png", ".svg", ".csv", ".xlsx")):
                    sub = "figures" if f.startswith("Figure") else "tables"
                    os.makedirs(os.path.join(dd, sub), exist_ok=True)
                    shutil.copy2(os.path.join(base, f), os.path.join(dd, sub, renum(f)))
    extras()
    for d in sorted(os.listdir(SUB)):
        n = sum(len(fs) for _, _, fs in os.walk(os.path.join(SUB, d)))
        print(f"{d}: {n} arquivos")


if __name__ == "__main__":
    main()
