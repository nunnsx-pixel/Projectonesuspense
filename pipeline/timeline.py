"""Tempo, curvas de keyframes e resolução de âncoras.

Âncoras permitem que SFX, câmera e beats "grudem" em palavras da narração:
se a gravação real mudar o tempo das falas, tudo que está ancorado acompanha.

Formas aceitas para um tempo (`at`):
    12.5                                                    segundos absolutos
    {"ref": "s1-04", "word": "quase", "edge": "start", "offset": -0.4}
    {"ref": "s1-04"}                                        item de narração inteiro
    {"beat": "b2-bilhete", "edge": "end", "offset": 0.2}    beat de cena
    {"cue": "bip-catraca", "offset": 0.35}                  cue de SFX
    {"scene": "s3", "edge": "start"}                        janela de cena
`edge` é "start" (padrão) ou "end"; `offset` em segundos.
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path

FPS = 60
ROOT = Path(__file__).resolve().parent.parent


def snap(t: float) -> float:
    """Arredonda para a grade de frames (1/60 s)."""
    return round(t * FPS) / FPS


def to_frame(t: float) -> int:
    return int(round(t * FPS))


def tc(t: float) -> str:
    """Timecode legível MM:SS.mmm."""
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:06.3f}"


def smoothstep(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def norm_word(w: str) -> str:
    return re.sub(r"[^\w-]", "", w.lower())


class Curve:
    """Keyframes [(t, v)] com interpolação 'smooth' (smoothstep por trecho) ou 'linear'.

    Antes da primeira chave e depois da última o valor é mantido.
    """

    def __init__(self, points, mode: str = "smooth"):
        self.pts = sorted((float(t), float(v)) for t, v in points)
        self.ts = [p[0] for p in self.pts]
        if mode not in ("smooth", "linear"):
            raise ValueError(f"modo de curva inválido: {mode!r}")
        self.mode = mode

    def __call__(self, t: float) -> float:
        if not self.pts:
            return 0.0
        if t <= self.ts[0]:
            return self.pts[0][1]
        i = bisect.bisect_right(self.ts, t) - 1
        if i >= len(self.pts) - 1:
            return self.pts[-1][1]
        (t0, v0), (t1, v1) = self.pts[i], self.pts[i + 1]
        u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
        if self.mode == "smooth":
            u = smoothstep(u)
        return v0 + (v1 - v0) * u


class Resolver:
    """Resolve âncoras para segundos. Itens de narração entram prontos;
    beats e cues são registrados como definições e resolvidos sob demanda."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.scenes: dict[str, tuple[float, float]] = {}
        self._defs: dict[tuple[str, str], dict] = {}
        self._spans: dict[tuple[str, str], tuple[float, float]] = {}
        self._busy: set[tuple[str, str]] = set()

    def register(self, kind: str, defs: list[dict]) -> None:
        for d in defs:
            key = (kind, d["id"])
            if key in self._defs:
                raise ValueError(f"id duplicado em {kind}: {d['id']}")
            self._defs[key] = d

    def span(self, kind: str, id_: str) -> tuple[float, float]:
        key = (kind, id_)
        if key in self._spans:
            return self._spans[key]
        if key not in self._defs:
            raise KeyError(f"{kind} inexistente: {id_!r}")
        if key in self._busy:
            raise ValueError(f"âncora circular em {kind}:{id_}")
        self._busy.add(key)
        d = self._defs[key]
        start = self.time(d["at"])
        if "dur" in d:
            end = start + float(d["dur"])
        elif "until" in d:
            end = self.time(d["until"])
        else:
            end = start
        self._busy.discard(key)
        self._spans[key] = (start, end)
        return start, end

    def time(self, at) -> float:
        if isinstance(at, (int, float)):
            return float(at)
        edge = at.get("edge", "start")
        offset = float(at.get("offset", 0.0))
        if "ref" in at:
            start, end = self._item_span(at)
        elif "beat" in at:
            start, end = self.span("beat", at["beat"])
        elif "cue" in at:
            start, end = self.span("cue", at["cue"])
        elif "scene" in at:
            start, end = self.scenes[at["scene"]]
        else:
            raise ValueError(f"âncora inválida: {at!r}")
        return (end if edge == "end" else start) + offset

    def _item_span(self, at: dict) -> tuple[float, float]:
        if at["ref"] not in self.items:
            raise KeyError(f"item de narração inexistente: {at['ref']!r}")
        item = self.items[at["ref"]]
        if "word" not in at:
            return item["start"], item["end"]
        want = norm_word(at["word"])
        hits = [w for w in item.get("words", []) if norm_word(w["w"]) == want]
        nth = int(at.get("nth", 0))
        if len(hits) <= nth:
            raise KeyError(f"palavra {at['word']!r} (#{nth}) não encontrada em {at['ref']}")
        return hits[nth]["start"], hits[nth]["end"]


def curve_from_spec(spec, res: Resolver) -> Curve:
    """Aceita [[t, v], ...] (suave) ou {"mode": "linear", "keys": [[t, v], ...]}.
    Cada `t` pode ser número ou âncora."""
    mode = "smooth"
    keys = spec
    if isinstance(spec, dict):
        mode = spec.get("mode", "smooth")
        keys = spec["keys"]
    return Curve([(res.time(t), v) for t, v in keys], mode)


def keys_out_of_order(spec, res: Resolver) -> list[tuple[float, float]]:
    """Pares de chaves vizinhas cujo tempo resolvido anda para trás em relação à ordem escrita.

    A `Curve` reordena por tempo em silêncio; se uma âncora (ex.: fim de uma respiração que a medição do áudio encurtou)
    cair antes da chave anterior, a curva ganha outro formato (um valor pode ficar preso até o fim do episódio)."""
    keys = spec["keys"] if isinstance(spec, dict) else spec
    times = [res.time(t) for t, _v in keys]
    return [(a, b) for a, b in zip(times, times[1:]) if b < a - 1e-9]
