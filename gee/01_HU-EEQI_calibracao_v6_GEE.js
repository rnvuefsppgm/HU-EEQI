/*******************************************************************************************
 * HU-EEQI v6 | SCRIPT 01 — CALIBRAÇÃO v6 (limites agrupados, pesos e justificativa)
 * GEE Code Editor (JavaScript) — tradução do notebook 01_HU-EEQI_calibracao_v6.ipynb
 *
 * COMO USAR (code.earthengine.google.com):
 *   1. Logado com a conta que tem acesso aos assets , escolha o
 *      projeto (ex.: <your-project>) no seletor de projeto do canto superior direito.
 *   2. Cole este script, confira a CONFIGURAÇÃO e escolha a ETAPA logo abaixo.
 *   3. Clique em "Run". Exportações aparecem na aba "Tasks": clique em "RUN" em cada uma
 *      (o Code Editor não inicia tasks sozinho).
 *
 * CALIBRAÇÃO DEPOIS (duas passagens). Antes deste script: script 00, ETAPA = 'exportar_bruto', com
 * TODAS as tasks concluídas (pilha bruta de cada capital e ano em RAW_COLLECTION).
 *
 * ETAPAS (rode uma de cada vez, nesta ordem):
 *   'amostras'             -> painel FIXO de N_POINTS_PER_CITY pixels por capital (sorteado 1 vez só na máscara do domínio),
 *                          LIDO das pilhas brutas já gravadas (sem Landsat/ERA5/MAIAC): 1 task só -> calib_v6_bruto
 *                          em CALIB_FOLDER (projects/mapbiomas-caatinga-cloud04/assets/HU-EEQI_v6_calib) (+ CSV no Drive)
 *   'calibrar'             -> depois que a amostra terminar: limites (p1–p99, p2–p98, p5–p95), saturação,
 *                          medianas por ano/sensor, correlação, VIF, pesos CRITIC/EWM/PCA/iguais, IC por
 *                          bootstrap e CRITIC por ano -> grava calibration_v6 na pasta das amostras (lido pelos scripts 02 e 05)
 *   'amostras_direto'      -> (antiga, lenta) calcula os descritores nos pontos sem a pilha bruta: 1 task por ano
 * Depois: script 02, ETAPA = 'exportar' (índice calculado sobre a pilha bruta, tasks curtas).
 *
 * Tudo do notebook 01 roda aqui. Diferenças: os percentis vêm do redutor do Earth Engine (modo exato até
 * 1 milhão de valores) e o bootstrap usa outro gerador aleatório (semente 2024), então o IC pode diferir na
 * 3ª casa do notebook. A comparação com a calibração antiga (calibration2.json, no Drive) fica no notebook.
 *
 * Camadas na resolução original (sem reprojeção/agregação/interpolação) e agregação anual pela
 * mediana — idêntico aos notebooks v6. A configuração e a biblioteca são as mesmas nos scripts 00–05.
 *******************************************************************************************/
var ETAPA = 'amostras';   // 'amostras' | 'calibrar'

// =========================================================================================
// CONFIGURAÇÃO HU-EEQI v6  (mantenha IDÊNTICA nos scripts 00, 01, 02, 02b, 03, 04 e 05)
// =========================================================================================
var CITIES_ASSET      = 'projects/rnvuefsppgm/assets/Pol_capitais';
var CITY_NAME_PROP    = 'NM_MUN';
// Destino de TODAS as exportações para asset: projeto Cloud mapbiomas-caatinga-cloud04.
// (assets de projeto Cloud têm o formato projects/<projeto>/assets/<nome>)
var ASSET_ROOT        = 'projects/mapbiomas-caatinga-cloud04/assets';
var RAW_COLLECTION    = ASSET_ROOT + '/HU-EEQI_v6_raw';      // pilha bruta, 1ª passagem (script 00)
var OUT_COLLECTION    = ASSET_ROOT + '/HU-EEQI_v6';          // índice v6 (script 02, etapa exportar)
var FILLED_COLLECTION = ASSET_ROOT + '/HU-EEQI_v6_filled';   // série sem lacunas (script 02b)
var TRENDS_COLLECTION = ASSET_ROOT + '/TRENDS_HU-EEQI_v6';   // tendências (script 04)
// Amostras calib_v6_bruto (tiradas da pilha bruta do script 00) + calibration_v6 (script 01; lidas pelos scripts
// 01 'calibrar', 02 e 05).
var CALIB_FOLDER      = ASSET_ROOT + '/HU-EEQI_v6_calib';
var CALIB_FOLDERS     = [CALIB_FOLDER];   // pastas onde procurar/gravar, em ordem
var CALIB_NAME        = 'calibration_v6';   // tabela com a calibração, dentro da pasta acima
var GDP_ASSET         = 'projects/sat-io/open-datasets/GRIDDED_HDI_GDP/adm1_gdp_perCapita_1990_2022';
var MAPBIOMAS_ASSET   = 'projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1';
var CENSUS_2010_ASSET = '';
var CENSUS_2022_ASSET = '';
var DRIVE_FOLDER      = 'hu_eeqi_v6';

// ---- série temporal ----------------------------------------------------------------------
var YEAR_START = 2000, YEAR_END = 2025;
var YEARS = [];
for (var _y = YEAR_START; _y <= YEAR_END; _y++) YEARS.push(_y);

// ---- escalas -----------------------------------------------------------------------------
// Cada camada fica na resolução ORIGINAL (Landsat 30 m, ERA5-Land ~9 km, MAIAC 1 km,
// GHS-POP 100 m, PIB adm1): nenhuma reprojeção, agregação ou interpolação. O índice é
// calculado pixel a pixel na grade de exportação (30 m, a do Landsat).
var EQ_SCALE       = 30;           // escala de exportação = resolução do Landsat (m)
var EXPORT_CRS     = 'EPSG:4326';  // mesmo CRS de exportação da v3
var AQ_STATS_SCALE = 1000;         // só p/ a estatística escalar da cidade (mediana de AQ)
var V_STATS_SCALE  = 1000;         // só p/ os percentis p2/p98 de V na cidade

// ---- domínio de análise (FIXO no tempo) --------------------------------------------------
var APPLY_URBAN_MASK = true;       // união GHS-SMOD >= URBAN_SMOD_MIN em 2000-2025
var URBAN_SMOD_MIN   = 21;         // 21 suburbano, 22 semi-denso, 23 denso, 30 centro urbano
var WATER_OCC_MAX    = 50;         // % de ocorrência JRC-GSW acima da qual o pixel é água

// ---- [1] harmonização TM/ETM+ -> OLI (Roy et al., 2016) ----------------------------------
var HARMONIZE  = true;
var ROY_METHOD = 'OLS';            // 'OLS' ou 'RMA' (Tabela 2 de Roy et al., 2016)
var L7_POLICY  = 'no_oli_years';   // 'no_oli_years': ETM+ só até 2012 | 'always'

// ---- [2] qualidade Landsat ----------------------------------------------------------------
var ST_QA_MAX_K      = null;       // incerteza máxima da LST (K); null = sem limite. v6: com 2 K nenhum
                                   // pixel passava (ST_QA fica em 2,5–7 K); a LST é só diagnóstico
var MIN_OBS          = 3;          // mínimo de observações limpas no ano por pixel
var COMPOSITE_MONTHS = null;       // ex.: [6, 9] = jun-set; null = ano inteiro
var CITY_MONTHS      = {};         // janela por cidade, ex.: {'Manaus': [7, 10]}

// ---- [4]/[8] HEAT: temperatura do ar e ponto de orvalho (ERA5-Land horário) --------------
var HEAT_METHOD      = 'nws_hi';            // 'nws_hi' (Rothfusz/NWS) | 'steadman_at'
var HEAT_LOCAL_HOURS = [12, 16];            // janela da tarde, em hora LOCAL
var HEAT_STAT        = 'median_daily_max';  // mediana anual do máximo diário | 'p95_daily_max'
var HEAT_XC_THRESH_C = 32.2;                // limiar NWS "extreme caution" (90 °F)
// HEAT calculado 1 vez por célula do ERA5-Land (0,1°) e não 1 vez por pixel de 30 m. Mesmo valor
// (testado: diferença 0): cada pixel de 30 m já recebia o valor da célula em que cai. Sem
// reamostragem nem agregação; só evita repetir a mesma conta ~90 mil vezes por célula.
var NATIVE_GRID_EVAL = true;
// v6: célula do ERA5-Land sem dado (o ERA5-Land mascara o mar; ~7% de Aracaju) recebe a média das
// células vizinhas imediatas com dado (3×3, grade nativa, mesmo ano); marcada na banda HEAT_filled.
var HEAT_FILL_NEIGHBORS = true;

// ---- AQ -------------------------------------------------------------------------------------
var AQ_SOURCE          = 'maiac';           // 'maiac' (AOD 550 nm) | 'pm25'
var AQ_REQUIRE_BEST_QA = true;              // MAIAC: céu claro + sem adjacência + QA "best"
var AOD_MIN_OBS        = 10;                // mínimo de retrievals válidos no ano por pixel
var AQ_FILL            = 'city_median';     // lacuna -> mediana do ano na cidade | 'none'
var PM25_COLLECTION    = null;
var PM25_BAND          = null;

// ---- [3] população -------------------------------------------------------------------------
var POP_SOURCE = 'ghs';                     // 'ghs' (GHS-POP R2023A) | 'worldpop'
var GHS_POP_IC = 'JRC/GHSL/P2023A/GHS_POP';
var POP_W_EPS  = 1.0;      // hab por célula de 100 m somados ao peso: área vazia -> peso ~uniforme

// ---- vulnerabilidade / justiça ------------------------------------------------------------
var USE_JUSTICE        = true;
var V_SOURCE           = 'gdp_adm1';        // 'census' (RECOMENDADO) | 'gdp_adm1'
var GDP_YEAR_START = 1990, GDP_YEAR_END = 2022;
var CENSUS_INCOME_PROP = '';                // propriedade de renda nos setores censitários
var V_CENSUS = {};
if (CENSUS_2010_ASSET) V_CENSUS[2010] = {asset: CENSUS_2010_ASSET, prop: CENSUS_INCOME_PROP};
if (CENSUS_2022_ASSET) V_CENSUS[2022] = {asset: CENSUS_2022_ASSET, prop: CENSUS_INCOME_PROP};
var V_MIN_REL_RANGE = 1e-3;                 // (p98-p2)/|p98| mínimo p/ J ser informativo
var J_FALLBACK      = 'renormalize';        // J degenerado: 'renormalize' | 'to_eq'

// ---- fusão  HU-EEQI = EQ^a · E^b · J^c ------------------------------------------------------
var ALPHA = 0.6, BETA = 0.2, GAMMA = 0.2;
var WIN_RADIUS_M = 2000;
var NI_FLOOR     = 0.01;

// ---- [7] calibração -----------------------------------------------------------------------
var BOUNDS_PCT    = [1, 99];                // limites agrupados (todas as cidades e anos)
var WEIGHT_METHOD = 'critic';               // 'critic' | 'ewm' | 'pca' | 'equal'
var DESCRIPTORS = ['NDVI', 'Wet', 'NDBSI', 'HEAT', 'AQ'];
var DIRECTION   = {NDVI: 'benefit', Wet: 'benefit', NDBSI: 'cost', HEAT: 'cost', AQ: 'cost'};

// ---- [6] exportação -----------------------------------------------------------------------
var EXPORT_DIAGNOSTICS = true;              // descritores brutos + QA (necessário p/ 03 e 05)
var SKIP_EXISTING      = true;              // não exporta de novo o que já existe
var VERSION = 'v6';

// ---- painel fixo de pixels (scripts 03 e 05) ---------------------------------------------
var N_PANEL_PER_CITY = 400;                 // pixels por capital
var PANEL_SEED       = 7;                   // capital i usa PANEL_SEED + i
var MB_YEARS         = [2000, 2023];        // anos MapBiomas p/ áreas estáveis

// ---- tendências (scripts 04 e 05) ---------------------------------------------------------
var ALPHA_SIG     = 0.05;                   // nível de significância
var FDR_Q         = ALPHA_SIG;              // q de Benjamini–Hochberg
var FDR_HIST_BINS = 50000;                  // resolução do histograma de p em [0, ALPHA_SIG]
var R1_THRESHOLD  = 0.3;                    // limiar de autocorrelação lag-1

// ---- [9] preenchimento de lacunas (script 02b; usado nos 04 e 05) ---------------------------
// Lacuna = pixel do domínio sem valor no ano (nuvem/sombra, < MIN_OBS observações, ano inteiro sem
// imagem, HEAT/AQ/LST sem dado). Cascata pixel a pixel e banda a banda sobre a série anual JÁ
// exportada, em TODAS as bandas contínuas (índice, componentes, descritores, LST, POP e V):
//   fill_type 0 observado
//   fill_type 1 interpolação linear no tempo entre o último ano com dado antes e o primeiro depois
//               (lacuna de 1 ano = média dos dois; vale também para o ano inteiro vazio)
//   fill_type 2 ponta da série (só um lado tem dado): ano com dado mais próximo
//   fill_type 3 pixel sem dado em nenhum ano: média dos pixels com valor no mesmo ano numa janela
//               de WIN_RADIUS_M (a mesma janela de E e J)
//   fill_type 4 nenhum pixel com valor nessa janela: mediana da capital no ano
// filled_mask: bit i = banda FILL_BANDS[i] preenchida (não observada) naquele pixel-ano.
var FILL_BANDS      = ['HU_EEQI', 'EQ', 'E_local', 'J_local', 'NI_NDVI', 'NI_Wet', 'NI_NDBSI', 'NI_HEAT', 'NI_AQ',
                       'NDVI', 'Wet', 'NDBSI', 'HEAT', 'AQ', 'LST', 'LST_anom', 'HEAT_ndays_xc', 'POP', 'V'];
var FILL_KEY_BAND   = 'HU_EEQI';     // fill_type e gap_years descrevem esta banda
// contagens e marcas copiadas do ano (0 = sem observação/sem marca naquele ano); urban é recalculada
var FILL_COPY_BANDS = ['n_obs', 'sensor_flag', 'n_TM', 'n_ETM', 'n_OLI', 'n_obs_thermal', 'n_aod',
                       'AQ_filled', 'HEAT_filled', 'NI_clamped'];
var FILL_REPORT_GAP = 3;             // resumo: pixels preenchidos com lacuna maior que 3 anos
var TREND_SOURCE    = 'filled';      // 04/05: 'filled' = série preenchida (02b) | 'observed' = só anos observados

// =========================================================================================
// SCRIPT 01 — CALIBRAÇÃO (limites agrupados, pesos e justificativa)
// =========================================================================================
var CITY_FILTER     = null;    // ex.: ["Aracaju"] para testar; null = todas as capitais
var CALIB_YEARS     = YEARS;   // todos os anos: os limites cobrem a série inteira
var N_POINTS_PER_CITY = 500;   // pixels FIXOS por capital (30 m, no domínio), os mesmos em todos os anos
var CALIB_SEED        = 2024;  // sorteio dos pixels: capital i usa CALIB_SEED + i
var CALIB_BALANCE_N   = 400;   // máx. de amostras válidas por capital e ano (peso igual); null = todas
var YEAR_FILTER       = null;  // ex.: [2015] para testar a etapa 'amostras' (não use na calibração final)
var ALSO_DRIVE_CSV  = true;    // também grava as amostras em CSV no Drive (p/ o notebook Python)
var CALIB_RAW_TABLE = 'calib_v6_bruto';   // tabela de amostras tiradas da pilha bruta (etapa 'amostras')
var BOOT_N          = 500;     // reamostragens do bootstrap em blocos de cidade
var BOOT_SEED       = 2024;

// ---- álgebra pequena (5 x 5) no cliente ---------------------------------------------------
function zeros(n, m) { var a = []; for (var i = 0; i < n; i++) { a.push([]); for (var j = 0; j < m; j++) a[i].push(0); } return a; }
function round6(x) { return Math.round(x * 1e6) / 1e6; }
function emptyStats(k) { return {n: 0, S: new Array(k).fill(0), Q: zeros(k, k), XL: new Array(k).fill(0), SAT: new Array(k).fill(0)}; }
function addStats(a, b) {
  var k = a.S.length;
  a.n += b.n;
  for (var i = 0; i < k; i++) { a.S[i] += b.S[i]; a.XL[i] += b.XL[i]; a.SAT[i] += b.SAT[i];
    for (var j = 0; j < k; j++) a.Q[i][j] += b.Q[i][j]; }
  return a;
}
function covCorr(st) {          // covariância amostral (ddof = 1), desvios e correlação
  var k = st.S.length, n = st.n, m = st.S.map(function (s) { return s / n; }), C = zeros(k, k), sd = [], R = zeros(k, k);
  for (var i = 0; i < k; i++) for (var j = 0; j < k; j++) C[i][j] = (st.Q[i][j] - n * m[i] * m[j]) / (n - 1);
  for (i = 0; i < k; i++) sd.push(Math.sqrt(Math.max(C[i][i], 0)));
  for (i = 0; i < k; i++) for (j = 0; j < k; j++) R[i][j] = C[i][j] / (sd[i] * sd[j]);
  return {sd: sd, R: R};
}
function wCritic(st) {          // CRITIC: σ_j · Σ_k (1 − r_jk), normalizado
  var cc = covCorr(st), k = cc.sd.length, C = [], tot = 0;
  for (var i = 0; i < k; i++) { var s = 0; for (var j = 0; j < k; j++) s += 1 - cc.R[i][j]; C.push(cc.sd[i] * s); tot += C[i]; }
  return C.map(function (c) { return c / tot; });
}
function wEwm(st) {             // entropia (EWM) a partir de Σx' e Σx' ln x' (x' = x + 1e-12)
  var k = st.S.length, n = st.n, d = [], tot = 0;
  for (var i = 0; i < k; i++) {
    var Sp = st.S[i] + n * 1e-12;
    var e = -((st.XL[i] / Sp) - Math.log(Sp)) / Math.log(n);
    d.push(1 - e); tot += 1 - e;
  }
  return d.map(function (x) { return x / tot; });
}
function jacobiEigen(A) {       // autovalores/vetores de matriz simétrica (Jacobi)
  var n = A.length, a = A.map(function (r) { return r.slice(); }), V = zeros(n, n);
  for (var i = 0; i < n; i++) V[i][i] = 1;
  for (var it = 0; it < 100; it++) {
    var p = 0, q = 1, mx = 0;
    for (i = 0; i < n; i++) for (var j = i + 1; j < n; j++) if (Math.abs(a[i][j]) > mx) { mx = Math.abs(a[i][j]); p = i; q = j; }
    if (mx < 1e-15) break;
    var th = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]), c = Math.cos(th), s = Math.sin(th);
    for (var r = 0; r < n; r++) {
      var arp = a[r][p], arq = a[r][q];
      a[r][p] = c * arp - s * arq; a[r][q] = s * arp + c * arq;
    }
    for (r = 0; r < n; r++) {
      var apr = a[p][r], aqr = a[q][r];
      a[p][r] = c * apr - s * aqr; a[q][r] = s * apr + c * aqr;
    }
    for (r = 0; r < n; r++) {
      var vrp = V[r][p], vrq = V[r][q];
      V[r][p] = c * vrp - s * vrq; V[r][q] = s * vrp + c * vrq;
    }
  }
  var vals = [];
  for (i = 0; i < n; i++) vals.push(a[i][i]);
  return {vals: vals, vecs: V};    // vetor próprio k = coluna k de V
}
function wPca(R) {              // PC1 da matriz de correlação (como no RSEI)
  var eg = jacobiEigen(R), k = R.length, imax = 0, tot = 0;
  for (var i = 0; i < k; i++) { tot += eg.vals[i]; if (eg.vals[i] > eg.vals[imax]) imax = i; }
  var l = [], s = 0;
  for (i = 0; i < k; i++) { l.push(eg.vecs[i][imax]); s += eg.vecs[i][imax]; }
  if (s < 0) l = l.map(function (x) { return -x; });
  var sa = l.reduce(function (p, x) { return p + Math.abs(x); }, 0);
  return {w: l.map(function (x) { return Math.abs(x) / sa; }), loadings: l, ev1: eg.vals[imax] / tot};
}
function invert(M) {            // inversa por Gauss-Jordan (para o VIF)
  var n = M.length, A = M.map(function (r, i) { var row = r.slice(); for (var j = 0; j < n; j++) row.push(i === j ? 1 : 0); return row; });
  for (var c = 0; c < n; c++) {
    var p = c;
    for (var r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    var t = A[c]; A[c] = A[p]; A[p] = t;
    var pv = A[c][c];
    for (var j = 0; j < 2 * n; j++) A[c][j] /= pv;
    for (r = 0; r < n; r++) if (r !== c) { var f = A[r][c]; for (j = 0; j < 2 * n; j++) A[r][j] -= f * A[c][j]; }
  }
  return A.map(function (row) { return row.slice(n); });
}
function mulberry32(a) {        // gerador pseudoaleatório com semente (bootstrap reprodutível)
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    var t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function percentileLin(arr, q) { // percentil com interpolação linear (igual ao numpy)
  var s = arr.slice().sort(function (a, b) { return a - b; }), h = (s.length - 1) * q / 100, lo = Math.floor(h);
  return lo + 1 < s.length ? s[lo] + (h - lo) * (s[lo + 1] - s[lo]) : s[lo];
}
function toObj(keys, vals) { var o = {}; keys.forEach(function (k, i) { o[k] = vals[i]; }); return o; }

// ---- ETAPA 'amostras': painel fixo de pixels lido das PILHAS BRUTAS já gravadas ---------------
// Calibração depois da 1ª passagem: os descritores já estão em RAW_COLLECTION (script 00, etapa
// 'exportar_bruto'), então a amostra só LÊ esses assets nos pontos do painel — nada de Landsat,
// ERA5 ou MAIAC aqui. 1 task só (todas as capitais e anos) -> <pasta>/calib_v6_bruto.
// Mesmos pontos de antes (N_POINTS_PER_CITY por capital, sorteados 1 vez na máscara do domínio).
function calibPoints(ctx, DOM) {
  var pref = ee.String(ctx.idx + '_');
  return DOM.selfMask().rename('dom').stratifiedSample({numPoints: N_POINTS_PER_CITY, classBand: 'dom',
           region: ctx.region, scale: EQ_SCALE, seed: CALIB_SEED + ctx.idx, geometries: true, tileScale: 4})
    .randomColumn('prand', CALIB_SEED)        // ordem aleatória fixa (equilíbrio na etapa 'calibrar')
    .map(function (f) { return f.set({pid: pref.cat(f.get('system:index')), city: ctx.name}); });
}
function samplesFrom(img, y, pts) {           // pixel-ano sem algum descritor (nuvem etc.) sai
  return ee.Image(img).select(DESCRIPTORS.concat(['n_obs', 'sensor_flag']))
    .sampleRegions({collection: pts, properties: ['pid', 'city', 'prand'], scale: EQ_SCALE,
                    tileScale: 4, geometries: false}).map(setter({year: y}));
}
var CALIB_SEL = ['pid', 'prand'].concat(DESCRIPTORS).concat(['n_obs', 'sensor_flag', 'city', 'year']);
function etapaAmostras() {
  var DOM = domainMask();
  withContexts(function (all) {
    var ctxs = filterCtxs(all), years = YEAR_FILTER || CALIB_YEARS;
    existingAssets(RAW_COLLECTION, function (rawDone) {
      var have = [], missing = [];
      ctxs.forEach(function (ctx) {
        years.forEach(function (y) {
          if (rawDone[rawAssetIdFor(ctx, y)]) have.push([ctx, y]); else missing.push(ctx.name + ' ' + y);
        });
      });
      if (missing.length) {
        print('ERRO: ' + missing.length + ' capital-ano ainda sem pilha bruta em ' + RAW_COLLECTION +
              '. Rode o script 00 (ETAPA = \'exportar_bruto\') e espere TODAS as tasks terminarem: os limites ' +
              'precisam da série inteira. Nenhuma task foi criada.', missing);
        return;
      }
      print(ctxs.length + ' cidades × ' + years.length + ' anos com pilha bruta', ctxs.map(function (c) { return c.name; }));
      if (CITY_FILTER || YEAR_FILTER) {
        print('ATENÇÃO: CITY_FILTER/YEAR_FILTER ativos — a tabela calib_v6_bruto terá só esse recorte (teste). ' +
              'Apague-a antes de gerar a tabela completa.');
      }
      checkRawConfig(have.map(function (t) { return rawAssetIdFor(t[0], t[1]); }), function () {
        writableFolder(CALIB_FOLDERS, 'FOLDER', function (folder) {
          existingAssets(folder, function (done) {
            var aid = folder + '/' + CALIB_RAW_TABLE;
            if (done[aid]) {
              print('ATENÇÃO: ' + aid + ' já existe; nada foi criado. Para refazer, apague-o no painel Assets e rode de novo.');
              return;
            }
            var pts = {};
            ctxs.forEach(function (ctx) { pts[ctx.name] = calibPoints(ctx, DOM); });
            var fc = ee.FeatureCollection(have.map(function (t) {
              return samplesFrom(ee.Image(rawAssetIdFor(t[0], t[1])), t[1], pts[t[0].name]);
            })).flatten();
            Export.table.toAsset({collection: fc, description: CALIB_RAW_TABLE, assetId: aid});
            if (ALSO_DRIVE_CSV) {
              Export.table.toDrive({collection: fc, description: CALIB_RAW_TABLE + '_csv', folder: DRIVE_FOLDER,
                                    fileNamePrefix: CALIB_RAW_TABLE, fileFormat: 'CSV', selectors: CALIB_SEL});
            }
            print('1 tabela com ' + have.length + ' capital-ano -> ' + aid +
                  ' (aba Tasks: RUN). Quando terminar, rode ETAPA = \'calibrar\'.');
          });
        });
      });
    });
  });
}

// ---- ETAPA 'amostras_direto' (antiga, LENTA): calcula os descritores nos pontos ---------------
// Só para quem não vai gravar a pilha bruta: calcula Landsat/ERA5/MAIAC nos pontos, 1 task por ano.
function calibSamples(y, ctx, pts, DOM) {
  var rs = rawStack(y, ctx);
  var img = rs[0].addBands(rs[1].select(['n_obs', 'sensor_flag'])).updateMask(DOM);
  return img.sampleRegions({collection: pts, properties: ['pid', 'city', 'prand'], scale: EQ_SCALE,
                            tileScale: 4, geometries: false}).map(setter({year: y}));
}
function etapaAmostrasDireto() {
  var DOM = domainMask();
  withContexts(function (all) {
    var ctxs = filterCtxs(all);
    print(ctxs.length + ' cidades', ctxs.map(function (c) { return c.name; }));
    var pts = {};
    ctxs.forEach(function (ctx) { pts[ctx.name] = calibPoints(ctx, DOM); });
    writableFolder(CALIB_FOLDERS, 'FOLDER', function (folder) {
      existingAssets(folder, function (done) {
        var n = 0;
        (YEAR_FILTER || CALIB_YEARS).forEach(function (y) {
          var aid = folder + '/calib_v6_' + y;
          if (SKIP_EXISTING && done[aid]) return;
          var fc = ee.FeatureCollection(ctxs.map(function (ctx) {
            return calibSamples(y, ctx, pts[ctx.name], DOM);
          })).flatten();
          Export.table.toAsset({collection: fc, description: 'calib_v6_' + y, assetId: aid});
          if (ALSO_DRIVE_CSV) {
            Export.table.toDrive({collection: fc, description: 'calib_v6_csv_' + y, folder: DRIVE_FOLDER,
                                  fileNamePrefix: 'calib_v6_' + y, fileFormat: 'CSV', selectors: CALIB_SEL});
          }
          n += 1;
        });
        print(n + ' anos com exportação criada -> ' + folder + ' (aba Tasks: RUN em cada uma).');
      });
    });
  });
}

// ---- ETAPA 'calibrar': limites, diagnóstico temporal e pesos -> <pasta>/calibration_v6 --------
var CALIB_DIR = CALIB_FOLDER;   // pasta onde estão as amostras (definida em loadSamples)
// Usa a tabela calib_v6_bruto (amostras das pilhas brutas) quando ela existe; senão, as tabelas
// antigas calib_v6_AAAA (etapa 'amostras_direto'). As duas nunca são misturadas.
function sampleIds(folder, ids) {
  if (ids[folder + '/' + CALIB_RAW_TABLE]) return [folder + '/' + CALIB_RAW_TABLE];
  return Object.keys(ids).filter(function (k) { return /\/calib_v6_\d{4}$/.test(k) && k.indexOf(folder + '/') === 0; }).sort();
}
function loadSamples(callback) {
  findInFolders(CALIB_FOLDERS, function (p, ids) { return sampleIds(p, ids).length > 0; }, function (p, ids) {
    CALIB_DIR = p;
    var sids = sampleIds(p, ids);
    print(sids.length + ' tabelas de amostras em ' + p);
    var tabs = sids.map(function (i) {
      var t = ee.FeatureCollection(i).filter(ee.Filter.notNull(DESCRIPTORS));
      if (!CALIB_BALANCE_N) return t;
      // até CALIB_BALANCE_N válidas por capital e ano: as de menor 'prand' (igual ao notebook 01)
      return ee.FeatureCollection(ee.List(t.aggregate_array('city').distinct()).map(function (c) {
        return t.filter(ee.Filter.eq('city', c)).sort('prand').limit(CALIB_BALANCE_N);
      })).flatten();
    });
    callback(ee.FeatureCollection(tabs).flatten());
  }, function () {
    print('ERRO: nenhuma tabela ' + CALIB_RAW_TABLE + ' (nem calib_v6_AAAA) em ' + CALIB_FOLDERS.join(' nem em ') +
          ' (rode a etapa amostras e espere a task terminar).');
  });
}
function etapaCalibrar() {
  loadSamples(function (samples) { calibrateFrom(samples); });
}
function calibrateFrom(samples) {
  var complete = samples.filter(ee.Filter.notNull(DESCRIPTORS));        // linhas COMPLETAS
  var PCTS = [1, 2, 5, 95, 98, 99];
  [BOUNDS_PCT[0], BOUNDS_PCT[1]].forEach(function (p) { if (PCTS.indexOf(p) < 0) PCTS.push(p); });
  var pct = {};
  DESCRIPTORS.forEach(function (d) {
    pct[d] = complete.reduceColumns(ee.Reducer.percentile({percentiles: PCTS, maxRaw: 1000000}), [d]);
  });
  ee.Dictionary({pct: pct, n: complete.size(), years: complete.aggregate_array('year').distinct().sort(),
                 ncity: complete.aggregate_array('city').distinct().size()}).evaluate(function (r, err) {
    if (err) { print('ERRO nos percentis: ' + err); return; }
    print(r.n + ' amostras | ' + r.ncity + ' cidades | ' + r.years.length + ' anos');
    var bset = function (a, b) {
      var o = {};
      DESCRIPTORS.forEach(function (d) { o[d] = {min: r.pct[d]['p' + a], max: r.pct[d]['p' + b]}; });
      return o;
    };
    var BOUND_SETS = {p1_99: bset(1, 99), p2_98: bset(2, 98), p5_95: bset(5, 95)};
    var key = 'p' + BOUNDS_PCT[0] + '_' + BOUNDS_PCT[1];
    if (!BOUND_SETS[key]) BOUND_SETS[key] = bset(BOUNDS_PCT[0], BOUNDS_PCT[1]);
    var BOUNDS = BOUND_SETS[key];
    var bprint = {};
    DESCRIPTORS.forEach(function (d) { bprint[d] = [BOUNDS[d].min, BOUNDS[d].max]; });
    print('Limites ' + key, bprint);
    statsAndWeights(complete, r, BOUNDS, BOUND_SETS, key);
  });
}
function statsAndWeights(complete, info, BOUNDS, BOUND_SETS, key) {
  var K = DESCRIPTORS.length, sel = ['one'], i, j;
  for (i = 0; i < K; i++) sel.push('n' + i);
  for (i = 0; i < K; i++) for (j = i; j < K; j++) sel.push('p' + i + j);
  for (i = 0; i < K; i++) sel.push('l' + i);
  for (i = 0; i < K; i++) sel.push('s' + i);
  var feats = complete.map(function (f) {
    var props = {one: 1}, nic = [];
    DESCRIPTORS.forEach(function (d, k) {
      var x = ee.Number(f.get(d)), lo = BOUNDS[d].min, hi = BOUNDS[d].max;
      var r = DIRECTION[d] === 'benefit' ? x.subtract(lo).divide(hi - lo) : ee.Number(hi).subtract(x).divide(hi - lo);
      var c = r.max(0).min(1);                                   // NI em [0, 1] (pesos)
      nic.push(c);
      props['n' + k] = c;
      props['l' + k] = c.add(1e-12).multiply(c.add(1e-12).log());
      props['s' + k] = r.lt(NI_FLOOR).or(r.gt(1));               // saturado (fora de [piso, 1])
    });
    for (var a = 0; a < K; a++) for (var b = a; b < K; b++) props['p' + a + b] = nic[a].multiply(nic[b]);
    props.key = ee.String(f.get('city')).cat('|').cat(ee.Number(f.get('year')).format('%d'));
    return ee.Feature(null, props);
  });
  var groups = feats.reduceColumns(ee.Reducer.sum().repeat(sel.length).group({groupField: sel.length, groupName: 'key'}),
                                   sel.concat(['key']));
  var medYear = complete.reduceColumns(ee.Reducer.median().repeat(K).group({groupField: K, groupName: 'year'}),
                                       DESCRIPTORS.concat(['year']));
  var medSensor = complete.reduceColumns(ee.Reducer.median().repeat(K).group({groupField: K, groupName: 'sensor_flag'}),
                                         DESCRIPTORS.concat(['sensor_flag']));
  var nobsYear = complete.reduceColumns(ee.Reducer.median().group({groupField: 1, groupName: 'year'}), ['n_obs', 'year']);
  ee.Dictionary({g: groups, my: medYear, ms: medSensor, ny: nobsYear}).evaluate(function (r, err) {
    if (err) { print('ERRO nas estatísticas: ' + err); return; }
    finishCalibration(r, info, BOUNDS, BOUND_SETS, key, sel);
  });
}
function finishCalibration(r, info, BOUNDS, BOUND_SETS, key, sel) {
  var K = DESCRIPTORS.length, byCity = {}, byYear = {}, pooled = emptyStats(K);
  r.g.groups.forEach(function (g) {
    var s = g.sum, st = emptyStats(K), idx = 0;
    st.n = s[idx++];
    for (var i = 0; i < K; i++) st.S[i] = s[idx++];
    for (i = 0; i < K; i++) for (var j = i; j < K; j++) { st.Q[i][j] = s[idx]; st.Q[j][i] = s[idx]; idx++; }
    for (i = 0; i < K; i++) st.XL[i] = s[idx++];
    for (i = 0; i < K; i++) st.SAT[i] = s[idx++];
    var parts = g.key.split('|'), city = parts[0], year = parts[1];
    byCity[city] = addStats(byCity[city] || emptyStats(K), st);
    byYear[year] = addStats(byYear[year] || emptyStats(K), st);
    addStats(pooled, st);
  });
  // ---- saturação por ano e consistência temporal dos descritores brutos ----------------------
  var sat = {};
  Object.keys(byYear).sort().forEach(function (y) {
    sat[Number(y)] = toObj(DESCRIPTORS, byYear[y].SAT.map(function (v) { return Math.round(1000 * v / byYear[y].n) / 10; }));
  });
  print('% de pixels saturados (fora de [piso, 1]) por ano:', sat);
  var my = {}; r.my.groups.forEach(function (g) { my[g.year] = toObj(DESCRIPTORS, g.median); });
  print('Mediana agrupada por ano (procure degraus em 2012/2013 e anos atípicos):', my);
  var names = {1: 'TM', 2: 'ETM', 4: 'OLI', 8: 'OLI2'}, ms = {};
  r.ms.groups.forEach(function (g) {
    var f = Number(g.sensor_flag), lab = Object.keys(names).filter(function (b) { return f & Number(b); })
      .map(function (b) { return names[b]; }).join('+') || '?';
    ms[lab] = toObj(DESCRIPTORS, g.median);
  });
  print('Mediana por combinação de sensores:', ms);
  var ny = {}; r.ny.groups.forEach(function (g) { ny[g.year] = g.median; });
  print('Observações limpas por ano (mediana de n_obs):', ny);
  // ---- redundância -------------------------------------------------------------------------
  var cc = covCorr(pooled), vifInv = invert(cc.R);
  print('Correlação (NI):', cc.R.map(function (row) { return row.map(function (v) { return Math.round(v * 100) / 100; }); }));
  print('VIF:', toObj(DESCRIPTORS, vifInv.map(function (row, i) { return Math.round(row[i] * 100) / 100; })));
  // ---- pesos ---------------------------------------------------------------------------------
  var pc = wPca(cc.R);
  var eq = {}; DESCRIPTORS.forEach(function (d) { eq[d] = 1.0 / K; });
  var WEIGHTS_ALL = {critic: toObj(DESCRIPTORS, wCritic(pooled).map(round6)),
                     ewm: toObj(DESCRIPTORS, wEwm(pooled).map(round6)),
                     pca: toObj(DESCRIPTORS, pc.w.map(round6)), equal: eq};
  print('PC1 explica ' + (100 * pc.ev1).toFixed(1) + '% | cargas:', toObj(DESCRIPTORS, pc.loadings.map(function (v) { return Math.round(v * 1000) / 1000; })));
  var bad = DESCRIPTORS.filter(function (d, i) { return pc.loadings[i] < 0; });
  if (bad.length) print('ATENÇÃO — cargas com sinal oposto (descritor não converge com os demais):', bad);
  // bootstrap em blocos de cidade (respeita a dependência espacial dentro da cidade)
  var cityNames = Object.keys(byCity), rng = mulberry32(BOOT_SEED), boot = [];
  for (var b = 0; b < BOOT_N; b++) {
    var acc = emptyStats(K);
    for (var c = 0; c < cityNames.length; c++) addStats(acc, byCity[cityNames[Math.floor(rng() * cityNames.length)]]);
    boot.push(wCritic(acc));
  }
  var CRITIC_CI = {};
  DESCRIPTORS.forEach(function (d, i) {
    var col = boot.map(function (w) { return w[i]; });
    CRITIC_CI[d] = [percentileLin(col, 2.5), percentileLin(col, 97.5)];
  });
  var perYear = {};
  Object.keys(byYear).sort().forEach(function (y) { perYear[Number(y)] = toObj(DESCRIPTORS, wCritic(byYear[y]).map(round6)); });
  var cvYear = {};
  DESCRIPTORS.forEach(function (d) {
    var v = Object.keys(perYear).map(function (y) { return perYear[y][d]; });
    var mean = v.reduce(function (p, x) { return p + x; }, 0) / v.length;
    var sd = Math.sqrt(v.reduce(function (p, x) { return p + (x - mean) * (x - mean); }, 0) / (v.length - 1));
    cvYear[d] = Math.round(1000 * sd / mean) / 10;
  });
  print('Pesos (método -> descritor):', WEIGHTS_ALL);
  print('CRITIC IC95% (bootstrap por cidade, ' + BOOT_N + ' reamostragens):', CRITIC_CI);
  print('CRITIC por ano — CV entre anos (%):', cvYear);
  // ---- salvar ------------------------------------------------------------------------------
  var calib = {
    version: VERSION, created: new Date().toISOString().slice(0, 19) + 'Z',
    n_samples: info.n, years: info.years.map(Number),
    bounds: BOUNDS, bounds_by_pct: BOUND_SETS, bounds_key: key,
    weights: WEIGHTS_ALL[WEIGHT_METHOD], weight_method: WEIGHT_METHOD, weights_all: WEIGHTS_ALL,
    critic_ci95: CRITIC_CI, critic_by_year: perYear, pca_pc1_explained: pc.ev1,
    pca_loadings: toObj(DESCRIPTORS, pc.loadings.map(round6)), saturation_pct_by_year: sat,
    direction: DIRECTION, descriptors: DESCRIPTORS, config: configSnapshot(),
    source: 'GEE Code Editor (script 01)'};
  var js = JSON.stringify(calib);
  print('calibration_v6.json (copie se quiser usar no notebook ou colar no script 02):', js);
  var calibAsset = CALIB_DIR + '/' + CALIB_NAME;   // mesma pasta das amostras
  existingAssets(CALIB_DIR, function (done) {
    var fc = ee.FeatureCollection([ee.Feature(null, {calib_json: js, created: calib.created, weight_method: WEIGHT_METHOD})]);
    if (done[calibAsset]) {
      print('ATENÇÃO: ' + calibAsset + ' já existe. Apague-o no painel Assets (ou mude CALIB_NAME) e rode de novo para gravar.');
    } else {
      Export.table.toAsset({collection: fc, description: 'calibration_v6', assetId: calibAsset});
      print('Calibração será gravada em ' + calibAsset);
    }
    Export.table.toDrive({collection: fc, description: 'calibration_v6_drive', folder: DRIVE_FOLDER,
                          fileNamePrefix: 'calibration_v6_gee', fileFormat: 'CSV', selectors: ['calib_json']});
    print('Pesos usados (' + WEIGHT_METHOD + '):', calib.weights, 'Aba Tasks: RUN em calibration_v6.');
  });
}

// =========================================================================================
// BIBLIOTECA HU-EEQI v6  (não editar — idêntica nos scripts 00, 01, 02, 02b, 03 e 05)
// Tradução linha a linha da biblioteca do notebook (mesmas operações do Earth Engine).
// =========================================================================================

// ---- 0) Constantes de dados ---------------------------------------------------------------
var OPT_BANDS   = ['BLUE', 'GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2'];
var SENSOR_CODE = {TM: 1, ETM: 2, OLI: 4, OLI2: 8};          // bits do sensor_flag
var LS_COLLECTIONS = [['LANDSAT/LT05/C02/T1_L2', 'TM'], ['LANDSAT/LE07/C02/T1_L2', 'ETM'],
                      ['LANDSAT/LC08/C02/T1_L2', 'OLI'], ['LANDSAT/LC09/C02/T1_L2', 'OLI2']];
var SENSOR_YEARS = {TM: [1984, 2012], ETM: [1999, 2024], OLI: [2013, 2100], OLI2: [2021, 2100]};
var SR_SRC = {TM:   ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
              ETM:  ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
              OLI:  ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
              OLI2: ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7']};
var ST_SRC = {TM: 'ST_B6', ETM: 'ST_B6', OLI: 'ST_B10', OLI2: 'ST_B10'};
// [1] Roy et al. (2016) RSE 185:57-70, Tabela 2 — ETM+ -> OLI (refletância de superfície),
//     ordem BLUE, GREEN, RED, NIR, SWIR1, SWIR2. Aplicada também ao TM.
var ROY_COEF = {
  OLS: {slope: [0.8474, 0.8483, 0.9047, 0.8462, 0.8937, 0.9071],
        itcp:  [0.0003, 0.0088, 0.0061, 0.0412, 0.0254, 0.0172]},
  RMA: {slope: [0.9785, 0.9542, 0.9825, 1.0073, 1.0171, 0.9949],
        itcp:  [-0.0095, -0.0016, -0.0022, -0.0021, -0.0030, 0.0029]}};
// Tasseled-cap Wetness (Crist, 1985), aplicado à série harmonizada (escala OLI).
var TCW = {BLUE: 0.1509, GREEN: 0.1973, RED: 0.3279, NIR: 0.3406, SWIR1: -0.7112, SWIR2: -0.4572};
var SMOD_IC     = 'JRC/GHSL/P2023A/GHS_SMOD_V2-0';
var GSW_IMG     = 'JRC/GSW1_4/GlobalSurfaceWater';
var ERA5_HOURLY = 'ECMWF/ERA5_LAND/HOURLY';
var MAIAC_IC    = 'MODIS/061/MCD19A2_GRANULES';
var WORLDPOP_IC = 'WorldPop/GP/100m/pop';
var CORE_BANDS = ['HU_EEQI', 'EQ', 'E_local', 'J_local', 'NI_NDVI', 'NI_Wet', 'NI_NDBSI',
                  'NI_HEAT', 'NI_AQ', 'n_obs', 'sensor_flag', 'POP', 'V', 'urban', 'domain'];
var DIAG_BANDS = ['NDVI', 'Wet', 'NDBSI', 'HEAT', 'AQ', 'NI_clamped', 'n_TM', 'n_ETM', 'n_OLI',
                  'n_obs_thermal', 'LST', 'LST_anom', 'n_aod', 'AQ_filled', 'HEAT_ndays_xc', 'HEAT_filled'];

// ---- 1) Utilidades, cidades e domínio ------------------------------------------------------
function asciiSafe(s) {
  var from = 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ';
  var to   = 'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn';
  var out = '';
  for (var i = 0; i < s.length; i++) {
    var k = from.indexOf(s.charAt(i));
    out += k >= 0 ? to.charAt(k) : s.charAt(i);
  }
  out = out.replace(/[^A-Za-z0-9.-]/g, '_').slice(0, 40);
  return out || 'city';
}
function setter(props) { return function (f) { return f.set(props); }; }
function cities() { return ee.FeatureCollection(CITIES_ASSET); }

// Contexto por capital (mesma ordem do asset = mesmo índice/semente do notebook).
function withContexts(callback) {
  var fc = cities();
  var info = fc.map(function (f) {
    return ee.Feature(null, {name: f.get(CITY_NAME_PROP),
                             lon: f.geometry().centroid(1000).coordinates().get(0)});
  });
  info.evaluate(function (r, err) {
    if (err) { print('ERRO ao ler as capitais: ' + err); return; }
    var flist = fc.toList(fc.size());
    var ctxs = r.features.map(function (f, i) {
      var name = f.properties.name;
      var region = ee.Feature(flist.get(i)).geometry();
      return {idx: i, name: name, safe: asciiSafe(name), region: region,
              region_buf: region.buffer(WIN_RADIUS_M + 1000, 100),   // margem p/ a janela de E/J
              utc_offset: Math.round(f.properties.lon / 15.0),       // hora SOLAR (lon/15)
              months: CITY_MONTHS[name] || COMPOSITE_MONTHS};
    });
    callback(ctxs);
  });
}

function domainMask() {     // domínio FIXO: terra (JRC-GSW) ∩ união urbana GHS-SMOD 2000-2025
  var land = ee.Image(GSW_IMG).select('occurrence').unmask(0).lt(WATER_OCC_MAX);
  if (!APPLY_URBAN_MASK) return land.rename('domain');
  var urb = ee.ImageCollection(SMOD_IC)
    .filterDate(YEAR_START + '-01-01', (YEAR_END + 1) + '-01-01')
    .map(function (i) { return i.select(0).gte(URBAN_SMOD_MIN); }).max();
  return land.and(urb).rename('domain');
}
function urbanMask(year) {  // urbano do ano (época SMOD mais próxima) — só informativo
  var e = Math.min(Math.max(5 * Math.round(year / 5.0), 1975), 2030);
  var smod = ee.ImageCollection(SMOD_IC).filter(ee.Filter.calendarRange(e, e, 'year')).first();
  return ee.Image(smod).select(0).gte(URBAN_SMOD_MIN).rename('urban');
}

// Parâmetros que mudam os descritores brutos: a calibração tem de bater com eles.
function configSnapshot() {
  return JSON.parse(JSON.stringify({
    HARMONIZE: HARMONIZE, ROY_METHOD: ROY_METHOD, L7_POLICY: L7_POLICY,
    ST_QA_MAX_K: ST_QA_MAX_K, MIN_OBS: MIN_OBS, COMPOSITE_MONTHS: COMPOSITE_MONTHS,
    CITY_MONTHS: CITY_MONTHS, HEAT_METHOD: HEAT_METHOD, HEAT_LOCAL_HOURS: HEAT_LOCAL_HOURS,
    HEAT_STAT: HEAT_STAT, HEAT_FILL_NEIGHBORS: HEAT_FILL_NEIGHBORS, AQ_SOURCE: AQ_SOURCE, AQ_REQUIRE_BEST_QA: AQ_REQUIRE_BEST_QA,
    AOD_MIN_OBS: AOD_MIN_OBS, AQ_FILL: AQ_FILL, PM25_COLLECTION: PM25_COLLECTION,
    APPLY_URBAN_MASK: APPLY_URBAN_MASK, URBAN_SMOD_MIN: URBAN_SMOD_MIN,
    WATER_OCC_MAX: WATER_OCC_MAX, EQ_SCALE: EQ_SCALE, ANNUAL_STAT: 'median',
    BOUNDS_PCT: BOUNDS_PCT, DESCRIPTORS: DESCRIPTORS, DIRECTION: DIRECTION}));
}
function sameJson(a, b) {   // compara valores JSON ignorando a ordem das chaves e 2.0 vs 2
  if (a === b) return true;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-12;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  var ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  if (ka.length !== kb.length) return false;
  for (var i = 0; i < ka.length; i++) {
    if (ka[i] !== kb[i] || !sameJson(a[ka[i]], b[kb[i]])) return false;
  }
  return true;
}
function checkCalibration(calib) {
  var old = calib.config || {}, cur = configSnapshot(), diff = {};
  Object.keys(cur).forEach(function (k) {
    if (!sameJson(old[k], cur[k])) diff[k] = {calib: old[k], atual: cur[k]};
  });
  if (Object.keys(diff).length) {
    print('ERRO: calibração incompatível com a configuração atual — rode o script 01 de novo.', diff);
    return false;
  }
  print('Calibração compatível (criada em ' + calib.created + ', n=' + calib.n_samples + ' amostras).');
  return true;
}
// Calibração: do asset do script 01 (CALIB_SOURCE = 'asset') ou colada (CALIB_SOURCE = 'colar',
// conteúdo do calibration_v6.json do notebook em CALIB_JSON_TEXT).
function loadCalibration(callback) {
  if (typeof CALIB_SOURCE !== 'undefined' && CALIB_SOURCE === 'colar') {
    var c = JSON.parse(CALIB_JSON_TEXT);
    if (checkCalibration(c)) callback(c);
    return;
  }
  findInFolders(CALIB_FOLDERS, function (p, ids) { return ids[p + '/' + CALIB_NAME]; }, function (p) {
    var aid = p + '/' + CALIB_NAME;
    ee.FeatureCollection(aid).first().get('calib_json').evaluate(function (s, err) {
      if (err || !s) { print('ERRO: não li a calibração em ' + aid + '. ' + (err || '')); return; }
      print('Calibração lida de ' + aid);
      var c = JSON.parse(s);
      if (checkCalibration(c)) callback(c);
    });
  }, function () {
    print('ERRO: não achei ' + CALIB_NAME + ' em ' + CALIB_FOLDERS.join(' nem em ') +
          ' (rode o script 01, etapas amostras e calibrar, ou use CALIB_SOURCE = \'colar\').');
  });
}
function assetIdOf(a) {   // id curto: tira o prefixo 'projects/earthengine-legacy/assets/' das raízes antigas
  return String(a.id || a.name).replace(/^projects\/earthengine-legacy\/assets\//, '');
}
function listIds(parent, callback) {   // callback(ids, err) — ids = {assetId: true}; lê todas as páginas
  var ids = {};
  var page = function (token) {
    var opts = {pageSize: 1000};
    if (token) opts.pageToken = token;
    ee.data.listAssets(parent, opts, function (r, err) {
      if (err) { callback(ids, err); return; }
      ((r && r.assets) || []).forEach(function (a) { ids[assetIdOf(a)] = true; });
      if (r && r.nextPageToken) page(r.nextPageToken); else callback(ids, null);
    });
  };
  page(null);
}
function existingAssets(parent, callback) {
  listIds(parent, function (ids, err) {
    if (err) print('Aviso: não listei ' + parent + ' (' + err + ')');
    callback(ids);
  });
}
// Confere se a pasta/coleção de destino EXISTE. O Code Editor trava ao criar assets por script
// (ee.data.createAsset / createFolder: a aba congela e sai um erro "Cannot set properties of
// undefined (setting 'toString')"), então o destino é criado UMA vez, à mão, no painel Assets:
// NEW > Folder (pasta) ou NEW > Image collection (coleção), com o nome exato. Sem ele, nenhuma
// task é criada (uma task para um destino inexistente só falha ao clicar em RUN).
function assetKind(type) { return type === 'FOLDER' ? 'Folder' : 'Image collection'; }
function ensureAsset(path, type, callback) {
  ee.data.getAsset(path, function (a, err) {
    if (!err && a) { print('Destino: ' + path); callback(path); return; }
    print('ERRO: o destino ' + path + ' não existe ou a conta logada não tem acesso a ele. Nenhuma task foi criada.',
          'Crie-o no painel Assets (NEW > ' + assetKind(type) + ') com esse nome exato, logado na conta certa, e rode de novo.',
          'Resposta do Earth Engine: ' + err);
  });
}
// 1ª pasta da lista que existe e a conta consegue ler. Se nenhuma existir, para sem criar tasks.
function writableFolder(paths, type, callback) {
  var i = 0, falhas = [];
  var next = function () {
    if (i >= paths.length) {
      print('ERRO: nenhuma pasta de destino existe (ou a conta logada não tem acesso). Nenhuma task foi criada.', falhas,
            'Crie a pasta no painel Assets (NEW > ' + assetKind(type) + ') com o nome exato ' + paths[0] +
            ', logado na conta certa, e rode de novo.');
      return;
    }
    var p = paths[i++];
    ee.data.getAsset(p, function (a, err) {
      if (!err && a) { print('Destino: ' + p); callback(p); return; }
      falhas.push(p + ': ' + err);
      next();
    });
  };
  next();
}
// 1ª pasta da lista cujo conteúdo passa no teste test(pasta, ids); senão chama onNone().
function findInFolders(paths, test, callback, onNone) {
  var i = 0;
  var next = function () {   // função anônima: o Code Editor não aceita função nomeada auto-executada
    if (i >= paths.length) { onNone(); return; }
    var p = paths[i++];
    listIds(p, function (ids, err) {
      if (!err && test(p, ids)) callback(p, ids); else next();
    });
  };
  next();
}

// ---- 2) Landsat C2 L2 — [2] máscara QA, [1] harmonização, composição com n_obs -------------
function prepLandsat(img, sensor) {
  var qa = img.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(31).eq(0);        // bits 0-4: fill, nuvem dilatada, cirrus, nuvem, sombra
  var unsat = img.select('QA_RADSAT').eq(0);  // nenhuma banda saturada
  var good = clear.and(unsat);
  var sr = img.select(SR_SRC[sensor], OPT_BANDS).multiply(0.0000275).add(-0.2);
  if (HARMONIZE && (sensor === 'TM' || sensor === 'ETM')) {
    var c = ROY_COEF[ROY_METHOD];
    sr = sr.multiply(ee.Image.constant(c.slope)).add(ee.Image.constant(c.itcp)).rename(OPT_BANDS);
  }
  // remove refletâncias fisicamente impossíveis (bordas de nuvem, sombra profunda)
  var phys = sr.reduce(ee.Reducer.min()).gt(0).and(sr.reduce(ee.Reducer.max()).lt(1));
  sr = sr.updateMask(good.and(phys));
  var lst = img.select(ST_SRC[sensor]).multiply(0.00341802).add(149.0).subtract(273.15).rename('LST');
  var stUnc = img.select('ST_QA').multiply(0.01);          // incerteza em K
  lst = lst.updateMask(good).updateMask(stUnc.gt(0));
  if (ST_QA_MAX_K !== null && ST_QA_MAX_K !== undefined) lst = lst.updateMask(stUnc.lte(ST_QA_MAX_K));
  var sensorBand = ee.Image.constant(SENSOR_CODE[sensor]).toInt().rename('sensor')
                     .updateMask(sr.select('NIR').mask());
  var out = sr.addBands(lst).addBands(sensorBand).set('sensor', sensor);
  return ee.Image(out.copyProperties(img, ['system:time_start']));
}
function prepFn(sensor) { return function (im) { return prepLandsat(im, sensor); }; }
function dateFilter(col, year, months) {
  col = col.filterDate(year + '-01-01', (year + 1) + '-01-01');
  if (months) col = col.filter(ee.Filter.calendarRange(months[0], months[1], 'month'));
  return col;
}
function landsatCollection(year, region, months) {
  var cols = [];
  LS_COLLECTIONS.forEach(function (cs) {
    var cid = cs[0], sensor = cs[1], yy = SENSOR_YEARS[sensor];
    if (year < yy[0] || year > yy[1]) return;
    if (sensor === 'ETM' && L7_POLICY === 'no_oli_years' && year >= 2013) return;
    cols.push(dateFilter(ee.ImageCollection(cid).filterBounds(region), year, months).map(prepFn(sensor)));
  });
  var col = cols[0];
  for (var i = 1; i < cols.length; i++) col = col.merge(cols[i]);
  return col;
}
function countEq(code) { return function (i) { return i.eq(code); }; }
function landsatComposite(year, ctx) {     // mediana harmonizada + QA (n_obs, sensores, LST)
  var col = landsatCollection(year, ctx.region_buf, ctx.months);
  var nObs = col.select('NIR').count().rename('n_obs');
  var opt = col.select(OPT_BANDS).median().updateMask(nObs.gte(MIN_OBS));
  var sens = col.select('sensor');
  var sensorFlag = sens.reduce(ee.Reducer.bitwiseOr()).rename('sensor_flag');
  var nTm  = sens.map(countEq(1)).sum().unmask(0).rename('n_TM');
  var nEtm = sens.map(countEq(2)).sum().unmask(0).rename('n_ETM');
  var nOli = sens.map(function (i) { return i.gte(4); }).sum().unmask(0).rename('n_OLI');
  var lst  = col.select('LST').median().rename('LST');
  var nTh  = col.select('LST').count().rename('n_obs_thermal');
  var qa = ee.Image.cat([nObs.unmask(0), sensorFlag, nTm, nEtm, nOli, nTh, lst]);
  return [opt.clip(ctx.region_buf), qa.clip(ctx.region_buf)];
}
function descriptorsOptical(comp) {
  var nir = comp.select('NIR'), red = comp.select('RED'), swir1 = comp.select('SWIR1'),
      blue = comp.select('BLUE'), green = comp.select('GREEN');
  var ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI');
  var wet = comp.select('BLUE').multiply(TCW.BLUE);
  ['GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2'].forEach(function (b) { wet = wet.add(comp.select(b).multiply(TCW[b])); });
  wet = wet.rename('Wet');
  // NDBSI = (IBI + SI) / 2  (Xu, 2008; Xu, 2013)
  var t1 = swir1.multiply(2).divide(swir1.add(nir));
  var t2 = nir.divide(nir.add(red)).add(green.divide(green.add(swir1)));
  var ibi = t1.subtract(t2).divide(t1.add(t2));
  var si = swir1.add(red).subtract(nir.add(blue)).divide(swir1.add(red).add(nir.add(blue)));
  var ndbsi = ibi.add(si).divide(2).rename('NDBSI');
  return ee.Image.cat([ndvi, wet, ndbsi]);
}

// ---- 3) [4]/[8] HEAT — índice de calor com TEMPERATURA DO AR (ERA5-Land horário) ------------
function esHpa(t) {          // pressão de saturação (hPa), Magnus — Alduchov & Eskridge (1996)
  return t.expression('6.1094 * exp(17.625 * T / (T + 243.04))', {T: t});
}
function heatIndexNws(tC, rh) {   // heat index NWS (Rothfusz 1990 + ajustes). °C e % -> °C
  var T = tC.multiply(1.8).add(32);
  var simple = T.expression('0.5 * (T + 61.0 + (T - 68.0) * 1.2 + RH * 0.094)', {T: T, RH: rh});
  var roth = T.expression(
    '-42.379 + 2.04901523*T + 10.14333127*RH - 0.22475541*T*RH' +
    ' - 0.00683783*T*T - 0.05481717*RH*RH + 0.00122874*T*T*RH' +
    ' + 0.00085282*T*RH*RH - 0.00000199*T*T*RH*RH', {T: T, RH: rh});
  var adjDry = T.expression('((13 - RH) / 4) * sqrt((17 - abs(T - 95)) / 17)', {T: T, RH: rh});
  var adjWet = T.expression('((RH - 85) / 10) * ((87 - T) / 5)', {T: T, RH: rh});
  roth = roth.where(rh.lt(13).and(T.gte(80)).and(T.lte(112)), roth.subtract(adjDry));
  roth = roth.where(rh.gt(85).and(T.gte(80)).and(T.lte(87)), roth.add(adjWet));
  var hiF = simple.where(simple.add(T).divide(2).gte(80), roth);
  return hiF.subtract(32).divide(1.8);
}
function hourlyHeat(img) {
  var t  = img.select('temperature_2m').subtract(273.15);
  var td = img.select('dewpoint_temperature_2m').subtract(273.15);
  var e  = esHpa(td);                                     // pressão de vapor real (hPa)
  var rh = e.divide(esHpa(t)).multiply(100).clamp(0, 100);
  var hi;
  if (HEAT_METHOD === 'steadman_at') {   // Steadman (1994): AT = Ta + 0.33e - 0.70ws - 4.00
    var ws = img.select('u_component_of_wind_10m').hypot(img.select('v_component_of_wind_10m'));
    hi = t.add(e.multiply(0.33)).subtract(ws.multiply(0.70)).subtract(4.00);
  } else {
    hi = heatIndexNws(t, rh);
  }
  return ee.Image(hi.rename('HI').copyProperties(img, ['system:time_start']));
}
function dayKey(img) { return img.set('day', ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')); }
function clipTo(geom) { return function (img) { return img.clip(geom); }; }
function dailyMax(f) {
  var hours = ee.ImageCollection.fromImages(ee.Image(f).get('hours'));
  return hours.max().set('system:time_start', ee.Image(f).get('system:time_start'));
}
// Mediana EXATA por pixel (ordena o vetor de valores válidos). ee.Reducer.median() é aproximado.
function exactMedian(ic) {
  var arr = ic.toArray().arrayProject([0]).arraySort();
  var n = arr.arrayLength(0);
  var ok = n.gt(0);
  arr = arr.updateMask(ok);
  var lo = arr.arrayGet(n.subtract(1).divide(2).floor().max(0).toInt());
  var hi = arr.arrayGet(n.divide(2).floor().min(n.subtract(1)).max(0).toInt());
  return lo.add(hi).divide(2).updateMask(ok);
}
// MEDIANA anual (ou p95) do máximo diário do índice de calor na janela da tarde, na resolução
// ORIGINAL do ERA5-Land (~9 km, vizinho mais próximo). Máximo diário por JOIN.
function heatLayer(year, ctx) {
  var u0 = HEAT_LOCAL_HOURS[0] - ctx.utc_offset, u1 = HEAT_LOCAL_HOURS[1] - ctx.utc_offset;
  if (!(0 <= u0 && u0 <= u1 && u1 <= 23)) throw new Error('Janela UTC inválida ' + u0 + '-' + u1 + ' para ' + ctx.name);
  var box = ctx.region_buf.bounds(1000);
  if (HEAT_FILL_NEIGHBORS) box = box.buffer(15000, 1000).bounds(1000);   // + 1 célula ERA5 (~11 km): vizinhas
  var era = ee.ImageCollection(ERA5_HOURLY).filterDate(year + '-01-01', (year + 1) + '-01-01')
    .select(['temperature_2m', 'dewpoint_temperature_2m', 'u_component_of_wind_10m', 'v_component_of_wind_10m']);
  var hourly = era.filter(ee.Filter.calendarRange(u0, u1, 'hour'))
    .map(clipTo(box)).map(hourlyHeat).map(dayKey);
  var first = hourly.filter(ee.Filter.calendarRange(u0, u0, 'hour'));   // 1 imagem por dia
  var joined = ee.Join.saveAll('hours').apply(first, hourly,
    ee.Filter.equals({leftField: 'day', rightField: 'day'}));
  var daily = ee.ImageCollection(joined.map(dailyMax));
  var heat = HEAT_STAT === 'p95_daily_max'
    ? daily.reduce(ee.Reducer.percentile([95])).rename('HEAT')
    : exactMedian(daily).rename('HEAT');
  var ndaysXc = daily.map(function (i) { return i.gte(HEAT_XC_THRESH_C); }).sum().rename('HEAT_ndays_xc');
  var nat = ee.Image(era.first()).select('temperature_2m').projection();
  var heatFlag = ee.Image.constant(0).rename('HEAT_filled');
  if (HEAT_FILL_NEIGHBORS) {
    // célula sem dado <- média das células vizinhas imediatas com dado (3×3), na grade nativa, mesmo ano
    // (skipMasked: false — senão a saída fica mascarada justamente onde a célula central não tem dado)
    var K1 = ee.Kernel.square({radius: 1, units: 'pixels'});
    var h0 = heat.reproject(nat), n0 = ndaysXc.reproject(nat);
    var hN = h0.reduceNeighborhood({reducer: ee.Reducer.mean(), kernel: K1, skipMasked: false}).reproject(nat);
    var nN = n0.reduceNeighborhood({reducer: ee.Reducer.mean(), kernel: K1, skipMasked: false}).reproject(nat);
    heatFlag = h0.mask().not().and(hN.mask()).reproject(nat).rename('HEAT_filled');
    heat = h0.unmask(hN).rename('HEAT'); ndaysXc = n0.unmask(nN).rename('HEAT_ndays_xc');
  }
  if (NATIVE_GRID_EVAL || HEAT_FILL_NEIGHBORS) {
    // conta feita 1 vez por célula ERA5-Land (0,1°), não por pixel de 30 m: mesmo valor,
    // pois cada pixel de 30 m já recebia o valor da célula em que cai (vizinho mais próximo)
    heat = heat.reproject(nat); ndaysXc = ndaysXc.reproject(nat);
  }
  return [heat, ndaysXc, heatFlag];
}

// ---- 4) AQ — MAIAC com QA, sem "zero = ar perfeito" ----------------------------------------
function maiacPrep(img) {
  var aod = img.select('Optical_Depth_055').multiply(0.001);
  if (AQ_REQUIRE_BEST_QA) {
    var qa = img.select('AOD_QA');
    var clear = qa.bitwiseAnd(7).eq(1);                   // bits 0-2 = 001 (céu claro)
    var adj = qa.rightShift(5).bitwiseAnd(7).eq(0);       // bits 5-7 = 000 (sem adjacência)
    var best = qa.rightShift(8).bitwiseAnd(15).eq(0);     // bits 8-11 = 0000 (best quality)
    aod = aod.updateMask(clear.and(adj).and(best));
  }
  return aod.rename('AOD');
}
function aqLayer(year, ctx) {   // MEDIANA anual na resolução ORIGINAL (MAIAC 1 km)
  var s = year + '-01-01', e = (year + 1) + '-01-01', aq, n;
  if (AQ_SOURCE === 'pm25') {
    if (!PM25_COLLECTION) throw new Error("AQ_SOURCE='pm25' exige PM25_COLLECTION e PM25_BAND.");
    aq = ee.ImageCollection(PM25_COLLECTION).filterDate(s, e).select(PM25_BAND).median();
    n = ee.Image.constant(1).rename('n_aod');
  } else {
    var col = ee.ImageCollection(MAIAC_IC).filterDate(s, e).filterBounds(ctx.region_buf).map(maiacPrep);
    n = col.count().rename('n_aod');
    aq = col.median().updateMask(n.gte(AOD_MIN_OBS));    // sem dado -> MASCARADO (não 0)
  }
  aq = aq.rename('AQ');
  var filled = aq;
  if (AQ_FILL === 'city_median') {   // lacuna -> mediana do ano na cidade (um número)
    var m = aq.reduceRegion({reducer: ee.Reducer.median(), geometry: ctx.region, scale: AQ_STATS_SCALE,
                             maxPixels: 1e12, bestEffort: true}).get('AQ');
    filled = ee.Image(ee.Algorithms.If(m, aq.unmask(ee.Image.constant(m)), aq)).rename('AQ');
  }
  var flag = aq.mask().not().and(filled.mask()).rename('AQ_filled');
  return [filled, n.unmask(0), flag];
}

// ---- 5) Pilha bruta de descritores ---------------------------------------------------------
function rawStack(year, ctx) {
  var lc = landsatComposite(year, ctx), opt = descriptorsOptical(lc[0]);
  var h = heatLayer(year, ctx), a = aqLayer(year, ctx);
  var raw = ee.Image.cat([opt, h[0], a[0]]).select(DESCRIPTORS);
  var qa = ee.Image.cat([lc[1], h[1], h[2], a[1], a[2]]);
  return [raw, qa];
}

// ---- 6) Normalização (limites agrupados) + EQ (média geométrica ponderada) ----------------
function normalizeStack(raw, bounds) {
  var out = [], flags = ee.Image.constant(0);
  DESCRIPTORS.forEach(function (name, i) {
    var lo = Number(bounds[name].min), hi = Number(bounds[name].max), x = raw.select(name), ni;
    if (DIRECTION[name] === 'benefit') ni = x.subtract(lo).divide(hi - lo);
    else ni = ee.Image.constant(hi).subtract(x).divide(hi - lo);
    var clipped = ni.lt(NI_FLOOR).or(ni.gt(1));
    flags = flags.add(clipped.multiply(Math.pow(2, i)));    // bit i = descritor saturado
    out.push(ni.clamp(NI_FLOOR, 1.0).rename('NI_' + name));
  });
  return [ee.Image.cat(out), flags.rename('NI_clamped')];
}
function computeEq(ni, weights) {
  var tot = 0;
  DESCRIPTORS.forEach(function (d) { tot += Number(weights[d]); });
  var logsum = ee.Image.constant(0.0);
  DESCRIPTORS.forEach(function (d) {
    logsum = logsum.add(ni.select('NI_' + d).log().multiply(Number(weights[d]) / tot));
  });
  return ee.Image(logsum).exp().clamp(NI_FLOOR, 1.0).rename('EQ');
}

// ---- 7) [3] População — GHS-POP R2023A (100 m, resolução ORIGINAL), log-linear -------------
function ghsEpoch(e) {
  return ee.Image(ee.ImageCollection(GHS_POP_IC).filter(ee.Filter.calendarRange(e, e, 'year')).first()).select(0);
}
function popProvenance(year) {
  if (POP_SOURCE === 'worldpop') return (year >= 2000 && year <= 2020) ? 'observado' : 'mantido_2020';
  return year % 5 === 0 ? 'observado' : 'interpolado_loglinear';
}
function popYear(year) {        // habitantes por célula de 100 m (sem reprojeção nem agregação)
  if (POP_SOURCE === 'worldpop') {
    var yw = Math.min(Math.max(year, 2000), 2020);
    return ee.Image(ee.ImageCollection(WORLDPOP_IC).filter(ee.Filter.eq('country', 'BRA'))
      .filter(ee.Filter.eq('year', yw)).first()).select('population').rename('POP');
  }
  var lo = 5 * Math.floor(year / 5), a = ghsEpoch(lo);
  if (year % 5 === 0) return a.rename('POP');
  var b = ghsEpoch(lo + 5), f = (year - lo) / 5.0;
  var lin = a.add(b.subtract(a).multiply(f));
  var loglin = a.max(1e-6).log().multiply(1 - f).add(b.max(1e-6).log().multiply(f)).exp();
  return lin.where(a.gt(0).and(b.gt(0)), loglin).rename('POP');   // log-linear onde as 2 épocas > 0
}

// ---- 8) Vulnerabilidade V e verificação de degenerescência da justiça ---------------------
function censusImg(y) {
  var spec = V_CENSUS[y];
  var fc = ee.FeatureCollection(spec.asset).filter(ee.Filter.notNull([spec.prop]));
  return fc.reduceToImage([spec.prop], ee.Reducer.first());     // valor do setor, sem reamostrar
}
function vulnRaw(year) {        // variável socioeconômica (maior = MENOS vulnerável)
  if (V_SOURCE === 'census') {
    var yrs = Object.keys(V_CENSUS).map(Number).sort();
    if (!yrs.length) throw new Error("V_SOURCE='census' exige V_CENSUS preenchido.");
    var los = yrs.filter(function (y) { return y <= year; }), his = yrs.filter(function (y) { return y >= year; });
    var lo = los.length ? los[los.length - 1] : yrs[0], hi = his.length ? his[0] : yrs[yrs.length - 1];
    var a = censusImg(lo);
    if (lo === hi) return [a.rename('VAR'), lo === year ? 'observado' : 'mantido_' + lo];
    var b = censusImg(hi), f = (year - lo) / (hi - lo);
    return [a.max(1e-6).log().multiply(1 - f).add(b.max(1e-6).log().multiply(f)).exp().rename('VAR'),
            'interpolado_loglinear'];
  }
  if (!GDP_ASSET) throw new Error("V_SOURCE='gdp_adm1' exige GDP_ASSET na configuração.");
  var yg = Math.min(Math.max(year, GDP_YEAR_START), GDP_YEAR_END);
  return [ee.Image(GDP_ASSET).select('PPP_' + yg).rename('VAR'), yg === year ? 'observado' : 'mantido_' + yg];
}
function vulnerability(year, ctx) {
  var vr = vulnRaw(year), x = vr[0];
  var pct = x.reduceRegion({reducer: ee.Reducer.percentile([2, 98]), geometry: ctx.region,
                            scale: V_STATS_SCALE, maxPixels: 1e12, bestEffort: true});
  var p2  = ee.Number(ee.Algorithms.If(pct.get('VAR_p2'),  pct.get('VAR_p2'),  0));
  var p98 = ee.Number(ee.Algorithms.If(pct.get('VAR_p98'), pct.get('VAR_p98'), 0));
  var rng = p98.subtract(p2);
  var jValid = rng.gt(p98.abs().multiply(V_MIN_REL_RANGE).max(1e-12));   // V constante => J sem informação
  var sc = x.subtract(p2).divide(rng.max(1e-12)).clamp(0, 1);
  return [ee.Image.constant(1).subtract(sc).rename('V'), ee.Number(jValid), vr[1]];
}

// ---- 9) Focais ponderados por população — na grade de SAÍDA (30 m), sem agregação --------
function kernelWin() { return ee.Kernel.square({radius: WIN_RADIUS_M, units: 'meters'}); }
function nsum(img, K) {
  return img.reduceNeighborhood({reducer: ee.Reducer.sum(), kernel: K, optimization: 'boxcar'});
}
function wmean(img, w, K) {
  var valid = img.mask().gt(0);
  var num = nsum(img.unmask(0).multiply(w).multiply(valid), K);
  var den = nsum(w.multiply(valid), K).max(1e-9);        // só pixels onde img é válido
  return num.divide(den);
}
function equityLocal(eq, w) {
  var K = kernelWin(), mu = wmean(eq, w, K), ex2 = wmean(eq.pow(2), w, K);
  var sd = ex2.subtract(mu.pow(2)).max(0).sqrt();
  var cv = sd.divide(mu.max(1e-6)).min(1.0);
  return ee.Image.constant(1).subtract(cv).clamp(NI_FLOOR, 1.0).rename('E_local');
}
function justiceLocal(eq, w, v) {
  var K = kernelWin(), b = ee.Image.constant(1).subtract(eq);     // ônus ambiental
  v = v.updateMask(eq.mask());
  var mb = wmean(b, w, K), mv = wmean(v, w, K);
  var cov = wmean(b.multiply(v), w, K).subtract(mb.multiply(mv));
  var sb = wmean(b.pow(2), w, K).subtract(mb.pow(2)).max(0).sqrt();
  var sv = wmean(v.pow(2), w, K).subtract(mv.pow(2)).max(0).sqrt();
  var corr = cov.divide(sb.multiply(sv).max(1e-6));               // + = ônus sobre os vulneráveis
  return ee.Image.constant(1).subtract(corr.clamp(0, 1)).clamp(NI_FLOOR, 1.0).rename('J_local');
}

// ---- 10) Fusão  HU-EEQI = EQ^a · E^b · J^c  (expoentes efetivos no servidor) --------------
function fuseIndex(eq, eLoc, jLoc, jValid) {
  var jv = USE_JUSTICE ? ee.Number(jValid) : ee.Number(0);
  var cEff = ee.Number(GAMMA).multiply(jv);
  var aEff = J_FALLBACK === 'to_eq' ? ee.Number(ALPHA).add(ee.Number(GAMMA).subtract(cEff)) : ee.Number(ALPHA);
  var s = aEff.add(BETA).add(cEff);
  var ex = {a: aEff.divide(s), b: ee.Number(BETA).divide(s), c: cEff.divide(s)};
  var lg = eq.log().multiply(ex.a).add(eLoc.log().multiply(ex.b)).add(jLoc.log().multiply(ex.c));
  return [ee.Image(lg).exp().clamp(0, 1).rename('HU_EEQI'), ex];
}

// ---- 11) Montagem do ano/cidade em DUAS passagens — [6] bandas NI_*, n_obs, sensor ----------
// Nenhuma camada é reprojetada, agregada ou interpolada.
//   1ª passagem (cara, sem calibração): rawYearImage = descritores brutos + QA + POP + V, gravada
//      em RAW_COLLECTION (script 00, etapa 'exportar_bruto'). É a única que lê Landsat/ERA5/MAIAC.
//   Calibração (script 01): amostras tiradas dessas imagens já gravadas (rápido) -> calibration_v6.
//   2ª passagem (barata): indexFromRaw = normalização, EQ, E, J e HU-EEQI a partir da pilha bruta
//      gravada (script 02, etapa 'exportar').
// buildYearImage = as duas passagens em sequência, sem gravar nada (mesmo resultado; usado nos
// testes, no preview e nas variantes do script 05).
var RAW_QA_BANDS = ['n_obs', 'sensor_flag', 'n_TM', 'n_ETM', 'n_OLI', 'n_obs_thermal', 'LST', 'LST_anom',
                    'n_aod', 'AQ_filled', 'HEAT_ndays_xc', 'HEAT_filled'];
var RAW_BANDS = DESCRIPTORS.concat(RAW_QA_BANDS).concat(['POP', 'V']);
function rawConfig() {      // parâmetros que mudam a pilha bruta (os limites só entram na 2ª passagem)
  var c = configSnapshot();
  delete c.BOUNDS_PCT;
  c.USE_JUSTICE = USE_JUSTICE; c.V_SOURCE = V_SOURCE; c.POP_SOURCE = POP_SOURCE; c.WIN_RADIUS_M = WIN_RADIUS_M;
  return c;
}
function rawYearImage(year, ctx, DOM) {
  var rs = rawStack(year, ctx), raw = rs[0].updateMask(DOM), qa = rs[1];
  var pop = popYear(year), v, jValid, vProv;
  if (USE_JUSTICE) {
    var vv = vulnerability(year, ctx);
    v = vv[0]; jValid = vv[1]; vProv = vv[2];
  } else {
    v = ee.Image.constant(0).rename('V'); jValid = ee.Number(0); vProv = 'n/a';
  }
  var lst = qa.select('LST');
  var med = lst.updateMask(DOM).reduceRegion({reducer: ee.Reducer.median(), geometry: ctx.region,
                                              scale: 90, maxPixels: 1e12, bestEffort: true}).get('LST');
  var lstAnom = lst.subtract(ee.Number(ee.Algorithms.If(med, med, 0))).rename('LST_anom');
  var bands = [raw, qa.select(['n_obs', 'sensor_flag', 'n_TM', 'n_ETM', 'n_OLI', 'n_obs_thermal', 'LST']), lstAnom,
               qa.select(['n_aod', 'AQ_filled', 'HEAT_ndays_xc', 'HEAT_filled']), pop, v];
  var img = ee.Image.cat(bands.map(function (b) { return ee.Image(b).toFloat(); })).select(RAW_BANDS);
  // recorte no BUFFER (região + WIN_RADIUS_M + 1 km): a janela de E/J nas bordas do município
  // usa pixels de fora dele, como no cálculo em uma passagem
  return img.clip(ctx.region_buf).set({
    year: year, city: ctx.name, version: VERSION, stage: 'raw', j_valid: jValid,
    prov: JSON.stringify({POP: popProvenance(year), V: vProv, AQ: 'observado', HEAT: 'observado'}),
    raw_config: JSON.stringify(rawConfig()), export_scale_m: EQ_SCALE,
    note: 'Pilha bruta (1ª passagem): descritores sem normalização, QA, POP e V. O índice é calculado ' +
          'depois (script 02, etapa exportar) com a calibração tirada destas imagens (script 01).'});
}
function indexFromRaw(r, year, ctx, bounds, weights, DOM) {
  r = ee.Image(r);
  var raw = r.select(DESCRIPTORS);
  var nn = normalizeStack(raw, bounds), ni = nn[0], clamped = nn[1];
  var eq = computeEq(ni, weights);
  var pop = r.select('POP'), w = pop.unmask(0).add(POP_W_EPS), v = r.select('V');
  var jValid = ee.Number(r.get('j_valid'));
  var eLoc = equityLocal(eq, w), jLoc;
  jLoc = USE_JUSTICE ? justiceLocal(eq, w, v) : ee.Image.constant(1.0).rename('J_local');
  eLoc = eLoc.updateMask(eq.mask()); jLoc = jLoc.updateMask(eq.mask());
  var fu = fuseIndex(eq, eLoc, jLoc, jValid), hu = fu[0], ex = fu[1];
  var bands = [hu, eq, eLoc, jLoc, ni, r.select(['n_obs', 'sensor_flag']), pop, v, urbanMask(year),
               DOM.rename('domain')];
  if (EXPORT_DIAGNOSTICS) {
    bands = bands.concat([raw, clamped, r.select(['n_TM', 'n_ETM', 'n_OLI', 'n_obs_thermal', 'LST', 'LST_anom',
                                                  'n_aod', 'AQ_filled', 'HEAT_ndays_xc', 'HEAT_filled'])]);
  }
  var img = ee.Image.cat(bands.map(function (b) { return ee.Image(b).toFloat(); }))
    .select(CORE_BANDS.concat(EXPORT_DIAGNOSTICS ? DIAG_BANDS : []));
  var props = {
    year: year, city: ctx.name, version: VERSION, harmonize: HARMONIZE ? 'True' : 'False',
    roy_method: ROY_METHOD, l7_policy: L7_POLICY, heat_method: HEAT_METHOD, heat_stat: HEAT_STAT,
    aq_source: AQ_SOURCE, aq_fill: AQ_FILL, pop_source: POP_SOURCE, v_source: V_SOURCE,
    j_fallback: J_FALLBACK, annual_statistic: 'median',
    prov: r.get('prov'),
    weights: JSON.stringify(weights), bounds: JSON.stringify(bounds),
    alpha: ALPHA, beta: BETA, gamma: GAMMA, win_radius_m: WIN_RADIUS_M, ni_floor: NI_FLOOR,
    export_scale_m: EQ_SCALE, j_valid: jValid, exp_eq: ex.a, exp_e: ex.b, exp_j: ex.c,
    note: 'Camadas na resolução original, sem reprojeção/agregação/interpolação: Landsat 30 m, ' +
          'ERA5-Land ~9 km, MAIAC 1 km, GHS-POP 100 m, PIB adm1. Agregação anual pela mediana. ' +
          'E/J com janela de WIN_RADIUS_M na grade de exportação. Índice calculado sobre a pilha bruta ' +
          'gravada (2ª passagem)'};
  return img.clip(ctx.region).set(props);
}
function buildYearImage(year, ctx, bounds, weights, DOM) {
  return indexFromRaw(rawYearImage(year, ctx, DOM), year, ctx, bounds, weights, DOM);
}
function rawAssetIdFor(ctx, year) { return RAW_COLLECTION + '/huEEQIraw_' + ctx.safe + '_' + year; }
function exportRawParams(img, ctx, year) {
  return {image: img, description: ('huEEQIraw' + VERSION + '_' + ctx.safe + '_' + year).slice(0, 100),
          assetId: rawAssetIdFor(ctx, year), region: ctx.region_buf, scale: EQ_SCALE, crs: EXPORT_CRS,
          maxPixels: 1e13,
          pyramidingPolicy: {'.default': 'mean', sensor_flag: 'mode', AQ_filled: 'mode', HEAT_filled: 'mode'}};
}
// Confere se as pilhas brutas gravadas foram feitas com a configuração atual.
function checkRawConfig(ids, callback) {
  if (!ids.length) { callback(true); return; }
  ee.ImageCollection.fromImages(ids.map(function (i) { return ee.Image(i); }))
    .aggregate_array('raw_config').distinct().evaluate(function (cfgs, err) {
      if (err) { print('ERRO ao ler a configuração das pilhas brutas: ' + err); return; }
      var cur = rawConfig(), bad = [];
      (cfgs || []).forEach(function (s) {
        var old = JSON.parse(s), diff = {};
        Object.keys(cur).forEach(function (k) { if (!sameJson(old[k], cur[k])) diff[k] = {bruto: old[k], atual: cur[k]}; });
        if (Object.keys(diff).length) bad.push(diff);
      });
      if (bad.length) {
        print('ERRO: há pilhas brutas em ' + RAW_COLLECTION + ' feitas com outra configuração. ' +
              'Apague-as (ou volte a configuração) e rode o script 00 (etapa exportar_bruto) de novo.', bad);
        return;
      }
      callback(true);
    });
}
function assetIdFor(ctx, year) { return OUT_COLLECTION + '/huEEQI_' + ctx.safe + '_' + year; }
function exportIndexParams(img, ctx, year) {
  return {image: img, description: ('huEEQIv6_' + ctx.safe + '_' + year).slice(0, 100),
          assetId: assetIdFor(ctx, year), region: ctx.region, scale: EQ_SCALE, crs: EXPORT_CRS,
          maxPixels: 1e13,
          pyramidingPolicy: {'.default': 'mean', sensor_flag: 'mode', NI_clamped: 'mode',
                             AQ_filled: 'mode', HEAT_filled: 'mode', urban: 'mode', domain: 'mode'}};
}
function filterCtxs(ctxs) {
  return ctxs.filter(function (c) {
    return typeof CITY_FILTER === 'undefined' || !CITY_FILTER || CITY_FILTER.indexOf(c.name) >= 0;
  });
}

// ---- 13) [9] Preenchimento de lacunas (script 02b; usado pelos 04 e 05) ---------------------
// Cascata pixel a pixel e banda a banda sobre a série anual JÁ exportada (OUT_COLLECTION), em TODAS
// as bandas contínuas (FILL_BANDS: índice, componentes, descritores, LST, POP e V):
//   0 observado | 1 interpolação linear no tempo entre o último ano com dado antes e o primeiro depois
//   (vale também para o ano inteiro vazio) | 2 ponta da série: ano com dado mais próximo |
//   3 sem dado em nenhum ano: média dos pixels com valor no mesmo ano numa janela de WIN_RADIUS_M |
//   4 nenhum pixel com valor nessa janela: mediana da capital no ano.
// fill_type e gap_years descrevem FILL_KEY_BAND; filled_mask marca (bit i) as bandas FILL_BANDS[i]
// que não foram observadas no pixel-ano. Contagens e marcas (FILL_COPY_BANDS) vêm do ano (0 = sem obs.).
function availableBands() { return CORE_BANDS.concat(EXPORT_DIAGNOSTICS ? DIAG_BANDS : []); }
function fillBandList() {
  var all = availableBands();
  return FILL_BANDS.filter(function (b) { return all.indexOf(b) >= 0; });
}
function fillCopyBands() {
  var all = availableBands();
  return FILL_COPY_BANDS.filter(function (b) { return all.indexOf(b) >= 0; });
}
function maskedImage(bands) {
  return ee.Image.constant(bands.map(function () { return 0; })).rename(bands).toFloat().updateMask(0);
}
function valueAndYear(img, year, FB) {
  var v = ee.Image(img).select(FB).toFloat();
  var t = ee.Image.constant(FB.map(function () { return year; }))
            .rename(FB.map(function (b) { return b + '__t'; })).toFloat();
  return v.addBands(t.updateMask(v.mask()));
}
function firstValid(series, years, FB) {   // 1º valor válido percorrendo `years` na ordem (+ ano dele)
  if (!years.length) return [maskedImage(FB), maskedImage(FB)];
  var tb = FB.map(function (b) { return b + '__t'; });
  var r = ee.ImageCollection.fromImages(years.map(function (y) { return valueAndYear(series[y], y, FB); }))
            .reduce(ee.Reducer.firstNonNull()).rename(FB.concat(tb));
  return [r.select(FB), r.select(tb).rename(FB)];
}
// {ano: imagem observada} da capital; years = anos presentes (lidos com evaluate)
function citySeries(col, ctx, years) {
  var cc = col.filter(ee.Filter.eq('city', ctx.name)), s = {};
  years.forEach(function (y) { s[y] = ee.Image(cc.filter(ee.Filter.eq('year', y)).first()); });
  return s;
}
// tipo 3: média, banda a banda, dos pixels COM valor numa janela quadrada de WIN_RADIUS_M (a mesma de E/J)
function spatialMean(img, FB) {
  var K = kernelWin();
  var num = nsum(img.unmask(0), K), den = nsum(img.mask(), K);
  return num.divide(den.max(1e-9)).updateMask(den.gt(0)).rename(FB);
}
function fillYearImage(series, year, ctx, DOM) {
  var FB = fillBandList();
  var present = Object.keys(series).map(Number).sort(function (a, b) { return a - b; });
  var has = present.indexOf(year) >= 0;
  var cur = has ? ee.Image(series[year]).select(FB).toFloat() : maskedImage(FB);
  var before = present.filter(function (y) { return y < year; }).reverse();
  var after = present.filter(function (y) { return y > year; });
  var p = firstValid(series, before, FB), nx = firstValid(series, after, FB);
  var pv = p[0], pt = p[1], nv = nx[0], nt = nx[1];
  var yr = ee.Image.constant(year);
  var interp = pv.add(nv.subtract(pv).multiply(yr.subtract(pt).divide(nt.subtract(pt))));   // tipo 1
  var edge = pv.unmask(nv);                                                                  // tipo 2
  var temporal = cur.unmask(interp).unmask(edge);                                            // tipos 0–2
  var spatial = spatialMean(temporal.updateMask(DOM), FB);                                   // tipo 3
  var tmp = FB.map(function (b) { return b + '__tmp'; });
  var med = cur.addBands(temporal.rename(tmp)).updateMask(DOM).reduceRegion({
    reducer: ee.Reducer.median(), geometry: ctx.region, scale: EQ_SCALE, crs: EXPORT_CRS,
    maxPixels: 1e13, tileScale: 4});
  var consts = FB.map(function (b, i) {
    return ee.Image.constant(ee.Number(ee.Algorithms.If(med.get(b), med.get(b),
                             ee.Algorithms.If(med.get(tmp[i]), med.get(tmp[i]), -9999))));
  });
  var cityMed = ee.Image.cat(consts).rename(FB).toFloat();
  cityMed = cityMed.updateMask(cityMed.neq(-9999));
  var filled = temporal.unmask(spatial).unmask(cityMed);                                     // tipo 4

  var k = FILL_KEY_BAND;
  var ftype = ee.Image.constant(4).where(spatial.select(k).mask(), 3).where(edge.select(k).mask(), 2)
                .where(interp.select(k).mask(), 1).where(cur.select(k).mask(), 0);
  var kpt = pt.select(k), knt = nt.select(k);
  var gap = knt.subtract(kpt)              // 1: distância entre os dois anos observados
              .unmask(yr.subtract(kpt))    // 2: só há ano antes
              .unmask(knt.subtract(yr))    // 2: só há ano depois
              .unmask(YEARS.length)        // 3 e 4: nunca observado
              .where(cur.select(k).mask(), 0);
  var fmask = ee.Image.constant(0);
  FB.forEach(function (b, i) { fmask = fmask.add(cur.select(b).mask().not().multiply(Math.pow(2, i))); });
  var parts = [filled, ftype.rename('fill_type').toFloat(), gap.rename('gap_years').toFloat(),
               fmask.rename('filled_mask').toFloat()];
  var cb = fillCopyBands();
  if (cb.length) {
    parts.push(has ? ee.Image(series[year]).select(cb).unmask(0).toFloat()
                   : ee.Image.constant(cb.map(function () { return 0; })).rename(cb).toFloat());
  }
  if (availableBands().indexOf('urban') >= 0) parts.push(urbanMask(year).toFloat());
  var img = ee.Image.cat(parts).updateMask(DOM).addBands(DOM.rename('domain').toFloat()).clip(ctx.region);
  img = img.set({year: year, city: ctx.name, version: VERSION, source: OUT_COLLECTION,
                 year_observed: has ? 1 : 0, years_present: JSON.stringify(present),
                 fill_key_band: k, fill_bands: JSON.stringify(FB),
                 fill_method: '0 observado | 1 interpolação linear no tempo entre o último ano com dado antes e o ' +
                              'primeiro depois | 2 ponta da série: ano com dado mais próximo | 3 nunca observado: ' +
                              'média dos pixels com valor no mesmo ano numa janela de ' + WIN_RADIUS_M + ' m | ' +
                              '4 sem valor na janela: mediana da capital no ano',
                 note: 'Preenchimento pixel a pixel sobre a série anual exportada (02b). filled_mask: bit i = ' +
                       'banda fill_bands[i] preenchida. NI_clamped, AQ_filled e HEAT_filled = 0 onde o ano não ' +
                       'foi observado.'});
  if (has) img = ee.Image(img.copyProperties(series[year], ['j_valid', 'exp_eq', 'exp_e', 'exp_j', 'prov']));
  return img;
}
function filledAssetId(ctx, year) { return FILLED_COLLECTION + '/huEEQIf_' + ctx.safe + '_' + year; }
function fillExportParams(img, ctx, year) {
  return {image: img, description: ('huEEQIf' + VERSION + '_' + ctx.safe + '_' + year).slice(0, 100),
          assetId: filledAssetId(ctx, year), region: ctx.region, scale: EQ_SCALE, crs: EXPORT_CRS,
          maxPixels: 1e13, pyramidingPolicy: {'.default': 'mean', fill_type: 'mode', gap_years: 'mode',
                                              filled_mask: 'mode', sensor_flag: 'mode', NI_clamped: 'mode',
                                              AQ_filled: 'mode', HEAT_filled: 'mode', urban: 'mode', domain: 'mode'}};
}
var FILL_SUMMARY_COLS = ['n_domain', 'n_observed', 'n_interp', 'n_edge', 'n_spatial', 'n_city_median',
                         'n_gap_gt' + FILL_REPORT_GAP, 'n_still_missing', 'n_any_band_missing'];
function fillSummaryFeature(img, ctx) {   // pixels do domínio por tipo de preenchimento
  var ft = img.select('fill_type'), gap = img.select('gap_years');
  var still = ft.gte(0).and(img.select(FILL_KEY_BAND).mask().not());
  var anyMiss = ft.gte(0).and(img.select(fillBandList()).mask().reduce(ee.Reducer.min()).eq(0));
  var ind = ee.Image.cat([ft.gte(0), ft.eq(0), ft.eq(1), ft.eq(2), ft.eq(3), ft.eq(4),
                          ft.gt(0).and(ft.lt(3)).and(gap.gt(FILL_REPORT_GAP)), still, anyMiss])
              .rename(FILL_SUMMARY_COLS);
  var s = ind.reduceRegion({reducer: ee.Reducer.sum().unweighted(), geometry: ctx.region, scale: EQ_SCALE, crs: EXPORT_CRS,
                            maxPixels: 1e13, tileScale: 4});
  return ee.Feature(null, s).set({city: ctx.name, year: img.get('year')});
}

// =========================================================================================
// EXECUÇÃO
// =========================================================================================
var ETAPAS = {amostras: etapaAmostras, calibrar: etapaCalibrar, amostras_direto: etapaAmostrasDireto};
if (ETAPAS[ETAPA]) {
  print('Etapa: ' + ETAPA + ' | v6 | revisão 06/11/2026-g (00 pilha bruta -> 01 calibração -> 02 índice -> 02b preenchimento; sem prioridade)');
  ETAPAS[ETAPA]();
} else if (ETAPA !== 'nenhuma') {
  print('ETAPA inválida: ' + ETAPA + '. Use uma de: ' + Object.keys(ETAPAS).join(', '));
}
