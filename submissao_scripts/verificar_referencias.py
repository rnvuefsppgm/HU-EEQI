# -*- coding: utf-8 -*-
"""Verifica cada referência com DOI no Crossref (título, 1º autor, ano, periódico) e busca candidatos para as
referências indicadas em BUSCAR. Saída: ../Submissao_HU_EEQI_v1/06_Validation/References_check.md
Uso: python verificar_referencias.py"""
import os
import re
import json
import time
import difflib
import urllib.request
import urllib.parse
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "Submissao_HU_EEQI_v1", "06_Validation", "References_check.md")
UA = {"User-Agent": "reference-checker/1.0 (python urllib)"}
BUSCAR = ["Examining heat inequity in a Brazilian metropolitan region Jung Haddad Gelder Urban Climate",
          "Racial and economic disparities in high-temperature exposure in Brazil Nature Communications",
          "A remote sensing assessment index for urban ecological livability and its application Yu"]


def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except Exception as e:                     # noqa: BLE001
            if "404" in str(e):
                return None
            time.sleep(2 * (k + 1))
    return None


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def check(line):
    key, doi, ref = line.split("|", 2)
    if not doi:
        return key, "sem DOI (livro/relatório/dado)", ""
    j = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    if not j:
        return key, "**DOI não encontrado no Crossref**", doi
    m = j["message"]
    title = (m.get("title") or [""])[0]
    year = (m.get("issued", {}).get("date-parts") or [[None]])[0][0]
    fam = (m.get("author") or [{}])[0].get("family", "")
    jour = (m.get("container-title") or [""])[0]
    t_ref = ref.split(") ", 1)[1].split(". ")[0] if ") " in ref else ref
    sim = difflib.SequenceMatcher(None, norm(t_ref), norm(title)).ratio()
    y_ref = re.search(r"\((\d{4})\)", ref)
    ok_y = y_ref and year and abs(int(y_ref.group(1)) - int(year)) <= 1
    ok_a = not fam or norm(fam.split()[0])[:5] in norm(ref[:60])
    st = "OK" if (sim > 0.8 and ok_y and ok_a) else "**CONFERIR**"
    return key, st, f"Crossref: {fam} ({year}) {title} — {jour} | similaridade {sim:.2f}"


def main():
    lines = [l.strip() for l in open(os.path.join(HERE, "referencias.txt"), encoding="utf-8") if l.strip()]
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(check, lines))
    out = ["# Reference check (Crossref)", "", "| Key | Status | Crossref record |", "|---|---|---|"]
    out += [f"| {k} | {s} | {d} |" for k, s, d in res]
    out += ["", "## Searches for references without DOI", ""]
    for q in BUSCAR:
        j = get("https://api.crossref.org/works?rows=3&query.bibliographic=" + urllib.parse.quote(q))
        for it in (j or {}).get("message", {}).get("items", []):
            out.append(f"- {q[:50]} → {it.get('DOI')} | {(it.get('title') or [''])[0]} | "
                       f"{(it.get('container-title') or [''])[0]} | {(it.get('issued', {}).get('date-parts') or [[None]])[0][0]} | "
                       f"{', '.join(a.get('family', '') for a in it.get('author', [])[:4])}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(out))
    bad = [r for r in res if "**" in r[1]]
    print(f"{len(res)} referências; {len(bad)} a conferir")
    for r in bad:
        print(" ", r)
    print("\n".join(out[-9:]))


if __name__ == "__main__":
    main()
