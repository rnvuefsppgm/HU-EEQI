# HU-EEQI — Hybrid Urban Environmental-Equity Quality Index for the 27 Brazilian state capitals (2000–2025)

Code supporting the manuscript on the Hybrid Urban Environmental-Equity Quality Index (HU-EEQI), version 6, computed
annually at 30 m for the urban areas of the 27 Brazilian state capitals over 2000–2025 (Lima, Vasconcelos, Cebrian,
Santana and Franca Rocha; manuscript prepared for *Urban Ecosystems*). It is the companion of
[RSEI_Brazilian_Capitals](https://github.com/rnvuefsppgm/RSEI_Brazilian_Capitals).

## 1. The index
HU-EEQI = EQ^α · E^β · J^γ with α = 0.6, β = γ = 0.2 (per pixel and year).

* **EQ — environmental quality**: CRITIC-weighted geometric mean of five normalized descriptors: NDVI, Tasseled-cap
  wetness, NDBSI (Landsat Collection 2 Level-2, TM/ETM+ harmonized to OLI with the OLS coefficients of Roy et al., 2016),
  the afternoon heat index (annual median of the daily 12–16 h maximum NWS heat index from ERA5-Land hourly data) and
  aerosol optical depth at 550 nm (MODIS MAIAC). Bounds are the 1st–99th percentiles pooled over all capitals and years,
  so that the index has a common scale (`calibration_v6.json`).
* **E — local environmental equity** and **J — local environmental justice**: population-weighted (GHS-POP) focal
  statistics of EQ within a 2-km window; J relates EQ to a socioeconomic vulnerability proxy. Where the proxy is constant
  within a capital (J uninformative), the exponent of J is redistributed proportionally to EQ and E.
* **Urban domain**: the index is computed only within a fixed urban domain per capital: pixels classified as suburban or
  denser (GHS-SMOD ≥ 21, JRC/GHSL P2023A) in any year of 2000–2025, excluding pixels covered by water at least 50% of the
  time (JRC Global Surface Water occurrence), inside the official IBGE municipal boundary. The mask is applied at the
  source (stack, calibration and index), not only in the maps.

## 2. Pipeline (execution order)
| Step | Colab notebook (`colab/`) / Code Editor script (`gee/`) | What it does |
|---|---|---|
| 00 | `00_HU-EEQI_pilha_bruta_v6` | Raw annual stack per capital-year: harmonized Landsat median composites with clear-observation counts, descriptors, heat index (ERA5-Land, neighbouring-cell fill on coastal cells), MAIAC AOD (capital-median fill), population, urban domain |
| 01 | `01_HU-EEQI_calibracao_v6` | Samples the stack in the urban domain; pooled p1–p99 bounds; CRITIC, entropy, PCA and equal weights; city-block bootstrap CI of the CRITIC weights; writes `calibration_v6.json` |
| 02 | `02_HU-EEQI_indice_por_pixel_v6` | Normalization, EQ, E_local, J_local and HU-EEQI per pixel and year, read from the stack |
| 02b | `02b_HU-EEQI_preenchimento_temporal_v6` | Pixel-wise gap filling of all bands: (1) linear interpolation in time, (2) nearest observed year at the series ends, (3) 2-km window mean, (4) capital median; flags in `fill_type` |
| 03 | `03_HU-EEQI_sensibilidade_diagnostico_v6` | Fixed pixel panel; reproducibility, common-year signal and Pettitt breaks, decomposition of changes, MapBiomas falsification test, Monte Carlo uncertainty |
| 04 | `04_Trends_HU_EEQI_v6` | Pixel-wise trends: Mann–Kendall (original and tie-corrected), Hamed–Rao variance correction (principal test), TFPW, Sen's slope, temporal mean/median/SD |
| 05 | `05_Trends_robustez_revisores_v6` | Additional robustness checks of the trends |

## 3. Figures, tables and supplementary material (Python, run locally)
| Folder | Script | Output |
|---|---|---|
| `figura2_tabelas_complementares/` | `figura2_localizacao.py` | Location map (Figure 2) |
| | `coletar_preenchimento_gee.py`, `gerar_tabelas_docx.py` | Completeness/gap-filling and calibration tables |
| `mapas_anuais_filled/` | `mapas_anuais_HU_EEQI_v6_filled.py`, `montar_docx.py` | Annual maps of the 27 capitals |
| `trends_HU_EEQI_v6/` | `gerar_trends_HU_EEQI_v6.py` | Table 1, trend figures, municipal series, robustness and demographic correlations |
| `material_suplementar_03/` | `gerar_material_suplementar_03.py` | Supplementary analyses of notebook 03 (needs `panel_v6.csv` exported by notebook 03) |
| `figura1_fluxograma/` | `figura1_fluxograma.py` | Methodological workflow (Figure 1) |
| `submissao_scripts/` | `analises_complementares.py` | Window-based change decomposition, step of E at the sensor transition, panel trends with E fixed, South–North gap |
| | `validar_resultados.py`, `auditar_numeros.py`, `verificar_referencias.py` | Independent validation of the statistics, audit of the numbers in the text and Crossref check of the references |
| | `montar_suplementar.py`, `montar_manuscrito.py`, `montar_submissao.py` | Assembly of the submission package (supplementary numbering S1–S11, manuscript, title page, cover letter) |
| root | `checar_layout.py` | Automatic check of clipped or overlapping text in every figure before saving |

Data included: IBGE capitals (`mapas_anuais_filled/data/Capitais.shp`) and states (`figura2_tabelas_complementares/data/BR_UF_2024.shp`), IBGE demographic indicators (`trends_HU_EEQI_v6/dados/`) and the frozen calibration (`material_suplementar_03/dados/calibration_v6.json`).

## 4. How to run
1. Earth Engine: `earthengine authenticate`, then set `EE_PROJECT` to your own Google Cloud project (and fill `EE_PROJECT`
   in the configuration cell of each notebook). Asset paths in the configuration cell point to the published HU-EEQI v6
   collections; change them to write your own.
2. Run the notebooks in the order 00 → 01 → 02 → 02b → 03/04/05 (the configuration cell is identical in all of them).
3. `pip install -r requirements.txt` and run the Python scripts of section 3.

Comments inside the scripts are in Portuguese; manuscript-facing outputs are in English.

## 5. License and citation
Code under GPL-3.0 (see `LICENSE`). Please cite the manuscript (see `CITATION.cff`).
