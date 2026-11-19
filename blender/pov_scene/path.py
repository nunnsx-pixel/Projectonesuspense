"""Caminho-base da cabeça (posição, altura dos olhos, direção) guiado pelos PASSOS (sem bpy).

A câmera só recebe balanço e olhar (CSV); aqui está o resto: ONDE a cabeça está. O avanço nasce da
lista de contatos do pé (a mesma do CSV e do SFX), então "o pé planta" exatamente nos frames dos
passos e a velocidade acompanha a cadência: correr = passadas rápidas, parar = sem passos.

Um caminho é uma lista de trechos (legs). Cada trecho tem:
  steps + from_time/to_time | phase0/phase1   avanço pelos passos (fase = nº fracionário de passos)
  span=(t0, t1)                                avanço por tempo (suavizado), sem passos
  pos      polilinha [(x, y), ...]             percorrida pelo avanço p (0..1) por comprimento de arco
  heading  número ou [[p, graus], ...]          0 = frente do ônibus (+Y), 90 = direita (+X), 270 = esquerda
  floor    número ou [[p, z], ...]              altura do piso sob os pés (ex.: degraus, piso do ônibus)
  eye      número ou [[p, z], ...]              altura dos olhos acima do piso (em pé, correndo, sentado)
Fora do trecho a pose fica parada na pose final do trecho anterior.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass


def smoothstep(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def interp(keys, p: float) -> float:
    """[[p, v], ...] com suavização por trecho; número = constante."""
    if isinstance(keys, (int, float)):
        return float(keys)
    ks = sorted((float(a), float(b)) for a, b in keys)
    if p <= ks[0][0]:
        return ks[0][1]
    if p >= ks[-1][0]:
        return ks[-1][1]
    i = bisect.bisect_right([k[0] for k in ks], p) - 1
    (p0, v0), (p1, v1) = ks[i], ks[i + 1]
    return v0 + (v1 - v0) * smoothstep((p - p0) / (p1 - p0))


class Phase:
    """Fase contínua do passo: contato i ocorre na fase i; linear entre contatos, extrapolada nas pontas."""

    def __init__(self, times: list[float]):
        if len(times) < 2:
            raise ValueError("um trecho guiado por passos precisa de ao menos 2 passos")
        self.t = list(times)

    def at(self, t: float) -> float:
        ts = self.t
        if t <= ts[0]:
            return (t - ts[0]) / (ts[1] - ts[0])
        if t >= ts[-1]:
            return len(ts) - 1 + (t - ts[-1]) / (ts[-1] - ts[-2])
        i = bisect.bisect_right(ts, t) - 1
        return i + (t - ts[i]) / (ts[i + 1] - ts[i])

    def time(self, phase: float) -> float:
        ts = self.t
        if phase <= 0:
            return ts[0] + phase * (ts[1] - ts[0])
        if phase >= len(ts) - 1:
            return ts[-1] + (phase - (len(ts) - 1)) * (ts[-1] - ts[-2])
        i = int(math.floor(phase))
        return ts[i] + (phase - i) * (ts[i + 1] - ts[i])


@dataclass
class Pose:
    x: float
    y: float
    floor: float
    eye: float
    heading: float

    @property
    def z(self) -> float:
        return self.floor + self.eye


def _arc(points, p: float) -> tuple[float, float]:
    segs = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(segs)
    if total == 0:
        return points[0]
    d = min(1.0, max(0.0, p)) * total
    for (a, b), s in zip(zip(points, points[1:]), segs):
        if d <= s or (a, b) == (points[-2], points[-1]):
            u = 0.0 if s == 0 else min(1.0, d / s)
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        d -= s
    return points[-1]


class Leg:
    def __init__(self, id_: str, pos, heading=0.0, floor=0.0, eye=1.62, steps=None, from_time=None, to_time=None,
                 phase0=None, phase1=None, span=None):
        self.id, self.pos, self.heading, self.floor, self.eye = id_, [tuple(p) for p in pos], heading, floor, eye
        self.length = sum(math.dist(a, b) for a, b in zip(self.pos, self.pos[1:]))
        if steps is not None:
            self.phase = Phase(steps)
            self.phase0 = phase0 if phase0 is not None else (self.phase.at(from_time) if from_time is not None else 0.0)
            self.phase1 = phase1 if phase1 is not None else (self.phase.at(to_time) if to_time is not None
                                                           else len(steps) - 1.0)
            self.t0, self.t1 = self.phase.time(self.phase0), self.phase.time(self.phase1)
            self.span = None
        elif span is not None:
            self.phase, self.span = None, tuple(span)
            self.t0, self.t1 = self.span
        else:
            raise ValueError(f"trecho {id_}: informe steps ou span")

    @property
    def stride(self) -> float | None:
        """Metros por passo (só para trechos guiados por passos)."""
        return None if self.phase is None else self.length / (self.phase1 - self.phase0)

    def progress(self, t: float) -> float:
        if self.phase is not None:
            return min(1.0, max(0.0, (self.phase.at(t) - self.phase0) / (self.phase1 - self.phase0)))
        return smoothstep((t - self.t0) / (self.t1 - self.t0))

    def pose(self, p: float) -> Pose:
        x, y = _arc(self.pos, p)
        return Pose(x, y, interp(self.floor, p), interp(self.eye, p), interp(self.heading, p))


class Track:
    def __init__(self, legs: list[Leg]):
        self.legs = sorted(legs, key=lambda l: l.t0)
        for a, b in zip(self.legs, self.legs[1:]):
            if b.t0 < a.t1 - 1e-6:
                raise ValueError(f"trechos sobrepostos: {a.id} termina {a.t1:.2f}s, {b.id} começa {b.t0:.2f}s")

    def sample(self, t: float) -> Pose:
        cur = None
        for leg in self.legs:
            if t >= leg.t0:
                cur = leg
        if cur is None:
            return self.legs[0].pose(0.0)
        return cur.pose(cur.progress(t))

    def gaps(self) -> list[tuple[str, str, float, float]]:
        """Descontinuidades entre o fim de um trecho e o início do seguinte: (a, b, metros, graus)."""
        out = []
        for a, b in zip(self.legs, self.legs[1:]):
            pa, pb = a.pose(1.0), b.pose(0.0)
            out.append((a.id, b.id, math.hypot(pa.x - pb.x, pa.y - pb.y) + abs(pa.z - pb.z),
                        abs((pa.heading - pb.heading + 180) % 360 - 180)))
        return out
