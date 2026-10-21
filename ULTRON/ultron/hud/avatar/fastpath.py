"""Conversões rápidas NumPy → Qt por QDataStream (medidas: ~11× mais rápido que criar QPointF um a um).

* ``polygon`` — uma polilinha (QPolygonF);
* ``path`` — várias sub-polilinhas num único QPainterPath (``connect[i]`` diz se o ponto i liga ao anterior);
* ``level_paths`` — linhas (linhas × colunas × 2) agrupadas por nível de alfa dos segmentos: um caminho por
  nível, desenhado com uma caneta só (o custo é por chamada de desenho, não por segmento).
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui

_PATH_DTYPE = np.dtype([("c", ">i4"), ("x", ">f8"), ("y", ">f8")])


def polygon(points) -> QtGui.QPolygonF:
    a = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    buf = np.empty(len(a) * 2, dtype=">f8")
    buf[0::2] = a[:, 0]
    buf[1::2] = a[:, 1]
    stream = QtCore.QDataStream(QtCore.QByteArray(np.array([len(a)], dtype=">u4").tobytes() + buf.tobytes()))
    poly = QtGui.QPolygonF()
    stream >> poly
    return poly


def path(points, connect) -> QtGui.QPainterPath:
    xy = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    n = len(xy)
    out = QtGui.QPainterPath()
    if n == 0:
        return out
    arr = np.empty(n, dtype=_PATH_DTYPE)
    arr["c"] = np.asarray(connect, dtype=bool).astype(np.int32)
    arr["c"][0] = 0
    arr["x"] = xy[:, 0]
    arr["y"] = xy[:, 1]
    data = np.array([n], dtype=">i4").tobytes() + arr.tobytes() + np.array([0, 0], dtype=">i4").tobytes()
    stream = QtCore.QDataStream(QtCore.QByteArray(data))
    stream >> out
    return out


def level_paths(rows_xy, segment_alpha, levels: int = 8, min_level: int = 1):
    """[(nível 0..1, QPainterPath)] — segmentos com alfa NaN ou ≤ 0 não são desenhados."""
    rows_xy = np.nan_to_num(np.asarray(rows_xy, dtype=np.float64))
    alpha = np.nan_to_num(np.asarray(segment_alpha, dtype=np.float64))
    rows, cols = rows_xy.shape[:2]
    quant = np.clip((alpha * levels + 0.5).astype(np.int32), 0, levels)
    flat = rows_xy.reshape(-1, 2)
    out = []
    for level in range(min_level, levels + 1):
        mask = quant == level
        if not mask.any():
            continue
        include = np.zeros((rows, cols), dtype=bool)
        include[:, :-1] |= mask
        include[:, 1:] |= mask
        connect = np.zeros((rows, cols), dtype=bool)
        connect[:, 1:] = mask
        selected = include.reshape(-1)
        out.append((level / levels, path(flat[selected], connect.reshape(-1)[selected])))
    return out
