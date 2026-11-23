# -*- coding: utf-8 -*-
"""Verificador automático de layout das figuras (matplotlib). Considera só o que aparece no arquivo salvo:
  - ignora rótulos de eixo cujo tique está fora dos limites visíveis (o matplotlib não os desenha);
  - a área de referência é a caixa justa da figura (as figuras são salvas com bbox_inches="tight"), de modo
    que só é "cortado" o que ficaria fora dela.
Relata: textos cortados, textos sobrepostos entre si e textos sobre um painel de mapa de outro eixo.
Uso: from checar_layout import auditar; auditar(fig, "Figura_3", "revisao_layout.txt") antes de salvar."""
import matplotlib.text as mtext
from matplotlib.transforms import Bbox


def _ticklabels_desenhados(fig):
    ok, todos = set(), set()
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        for axis in (ax.xaxis, ax.yaxis):
            for tk in axis.get_major_ticks() + axis.get_minor_ticks():
                todos.update({id(tk.label1), id(tk.label2)})
            if not ax.axison:                          # eixo desligado (ax.axis("off")): nada é desenhado
                continue
            for tk in axis._update_ticks():           # só os tiques dentro dos limites visíveis
                ok.update({id(tk.label1), id(tk.label2)})
    return ok, todos


def _txts(fig, r):
    ok, todos = _ticklabels_desenhados(fig)
    out = []
    for t in fig.findobj(mtext.Text):
        if not t.get_visible() or not t.get_text().strip():
            continue
        if id(t) in todos and id(t) not in ok:
            continue                                  # tique fora dos limites ou eixo desligado (não desenhado)
        if t.axes is not None and not t.axes.get_visible():
            continue
        try:
            bb = t.get_window_extent(r)
        except Exception:
            continue
        if bb.width > 0 and bb.height > 0:
            out.append((t, bb))
    return out


def auditar(fig, nome, log_path, tol=1.0, tight=True):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    if tight:
        tb = fig.get_tightbbox(r)
        area = Bbox.from_extents(tb.x0 * fig.dpi, tb.y0 * fig.dpi, tb.x1 * fig.dpi, tb.y1 * fig.dpi)
    else:
        area = fig.bbox
    tx = _txts(fig, r)
    probs = []
    for t, bb in tx:
        if bb.x0 < area.x0 - tol or bb.y0 < area.y0 - tol or bb.x1 > area.x1 + tol or bb.y1 > area.y1 + tol:
            probs.append(f"texto cortado: {t.get_text()[:50]!r}")
    for i in range(len(tx)):
        for j in range(i + 1, len(tx)):
            (a, ba), (b, bb) = tx[i], tx[j]
            ix = min(ba.x1, bb.x1) - max(ba.x0, bb.x0)
            iy = min(ba.y1, bb.y1) - max(ba.y0, bb.y0)
            if ix > tol and iy > tol:
                probs.append(f"textos sobrepostos: {a.get_text()[:35]!r} x {b.get_text()[:35]!r}")
    img_axes = [ax for ax in fig.axes if ax.images and ax.get_visible()]
    for t, bb in tx:
        for ax in img_axes:
            if t.axes is ax:
                continue
            ab = ax.get_window_extent(r)
            ix = min(ab.x1, bb.x1) - max(ab.x0, bb.x0)
            iy = min(ab.y1, bb.y1) - max(ab.y0, bb.y0)
            if ix > tol and iy > tol:
                probs.append(f"texto sobre painel de mapa: {t.get_text()[:40]!r}")
                break
    probs = sorted(set(probs))
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"{nome}: {'OK' if not probs else str(len(probs)) + ' problema(s)'}\n")
        for p in probs:
            fh.write(f"    - {p}\n")
    return probs
