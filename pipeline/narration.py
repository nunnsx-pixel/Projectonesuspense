"""Narração: texto + respirações + pausas -> tempos por palavra.

Os tempos são uma ESTIMATIVA a partir de sílabas e pontuação (ainda não há
gravação). Cada cena tem uma janela [início, fim]; o motor distribui as
palavras/pausas dentro dela mantendo as proporções do ritmo pretendido
(`pace_syl_s`) e informa o quanto precisou acelerar ou folgar (`fit_ratio`).
Quando a voz real existir, use `narration.measured.json` (ver README do ep).
"""
from __future__ import annotations

import re

from .timeline import lerp

# palavras átonas/curtas: duram menos que uma sílaba "cheia"
FUNCTION_WORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em", "no",
    "na", "nos", "nas", "e", "que", "eu", "se", "por", "pra", "pro", "para", "com",
    "mas", "é", "tá", "tô", "né", "meu", "me", "ao", "já",
}
FUNCTION_WEIGHT = 0.7
FINAL_LENGTHENING = {"...": 1.3, ".": 1.25, "!": 1.2, "?": 1.25, "?!": 1.25, ",": 1.1}
DEFAULT_PAUSES = {
    "...": 0.55, ".": 0.38, "!": 0.32, "?": 0.32, "?!": 0.34, ",": 0.15, ";": 0.2, ":": 0.2,
}
NO_PUNCT_PAUSE = 0.18

# fração de `dur` em inspirar / segurar / expirar + amplitude relativa do peito
BREATH_SHAPES = {
    "inhale_quick": {"in": 1.0, "hold": 0.0, "out": 0.0, "amp": 1.0},
    "sigh_long":    {"in": 0.40, "hold": 0.10, "out": 0.50, "amp": 1.5},
    "sniff":        {"in": 0.55, "hold": 0.0, "out": 0.45, "amp": 0.45},
    "yawn":         {"in": 0.55, "hold": 0.20, "out": 0.25, "amp": 1.8},
    "deep_slow":    {"in": 0.45, "hold": 0.10, "out": 0.45, "amp": 1.3},
    "gasp":         {"in": 1.0, "hold": 0.0, "out": 0.0, "amp": 1.9},           # susto: inspira seco e já grita
    "pant":         {"in": 0.5, "hold": 0.0, "out": 0.5, "amp": 1.2, "cycles": 3},   # huh-huh-huh
    "swallow":      {"in": 0.3, "hold": 0.1, "out": 0.6, "amp": 0.2},           # engole seco (quase sem peito)
}

_V = "aeiouáéíóúâêôãõà"
_STRONG = "aeoáéóâêôãõà"
_STRONG_ACCENTED = "áéóâêôãõà"


def count_syllables(word: str) -> int:
    """Heurística de sílabas para pt-BR (ditongos, hiatos comuns, qu/gu mudos)."""
    w = word.lower()
    w = re.sub(r"(?<=[qg])u(?=[eiéêíè])", "", w)
    w = re.sub(r"[^a-záéíóúâêôãõàç]", "", w)
    n = 0
    for m in re.finditer(rf"[{_V}]+", w):
        run = m.group(0)
        after = w[m.end(): m.end() + 2]
        n += 1
        for j in range(1, len(run)):
            p, c = run[j - 1], run[j]
            pp = run[j - 2] if j >= 2 else ""
            if p in _STRONG and c in _STRONG:
                n += 1                                   # hiato: bo-a
            elif c in "íú":
                n += 1                                   # hiato tônico: a-í
            elif c in _STRONG_ACCENTED and p in "iu":
                n += 1                                   # vi-á
            elif c in _STRONG and p in "iu" and pp in tuple(_V):
                n += 1                                   # mei-a, mei-o
            elif (c in "iu" and p in _V and after[:1] in tuple("nlrzm")
                  and (len(after) == 1 or after[1] not in _V)):
                n += 1                                   # sa-in-do, ru-im
    return max(n, 1)


def _split_punct(token: str) -> tuple[str, str]:
    token = token.replace("…", "...")
    m = re.match(r"^(.*?)(\.\.\.|\?!|!\?|[.!?,;:])+$", token)
    if not m:
        return token, ""
    tail = token[len(m.group(1)):]
    if tail.endswith("..."):
        return m.group(1), "..."
    if tail in ("?!", "!?"):
        return m.group(1), "?!"
    return m.group(1), tail[-1]


def tokenize(text: str, lexicon: dict[str, str]) -> list[dict]:
    words = []
    for raw in text.split():
        word, punct = _split_punct(raw)
        if not word:
            continue
        spoken = lexicon.get(word, word)
        syl = sum(count_syllables(p) for p in re.split(r"[-\s]+", spoken) if p)
        base = re.sub(r"\W", "", word.lower())
        weight = syl * (FUNCTION_WEIGHT if base in FUNCTION_WORDS else 1.0)
        weight *= FINAL_LENGTHENING.get(punct, 1.0)
        words.append({"w": word, "punct": punct, "spoken": spoken, "syl": syl, "weight": weight})
    return words


def layout_scene(scene: dict, lexicon: dict[str, str], pauses: dict[str, float]) -> dict:
    """Distribui os itens da cena dentro da janela. Retorna itens com tempos + estatísticas."""
    w0, w1 = scene["window"]
    syl0 = 1.0 / scene["pace_syl_s"]
    drag0, drag1 = scene.get("drag", [1.0, 1.0])

    entries = []
    for item in scene["items"]:
        if item.get("skip"):
            continue
        if item["kind"] == "speech":
            entries.append((item, tokenize(item["text"], lexicon)))
        else:
            entries.append((item, None))
    total_syl = sum(w["syl"] for _, ws in entries if ws for w in ws) or 1

    slots = []   # {"type": word|pause|fixed, "dur", "flex", ...}
    cum = 0
    for item, words in entries:
        if words is None:
            slots.append({"type": "fixed", "item": item, "dur": float(item["dur"]), "flex": False})
            gap = float(item.get("gap_after", 0.1 if item["kind"] == "breath" else 0.0))
            if gap:
                slots.append({"type": "gap", "dur": gap, "flex": False})
            continue
        for wd in words:
            drag = lerp(drag0, drag1, (cum + wd["syl"] / 2) / total_syl)
            cum += wd["syl"]
            slots.append({"type": "word", "item": item, "word": wd, "dur": wd["weight"] * syl0 * drag,
                          "flex": True})
            if wd["punct"]:
                slots.append({"type": "pause", "dur": pauses[wd["punct"]] * drag, "flex": True})
            elif wd is words[-1]:
                slots.append({"type": "pause", "dur": NO_PUNCT_PAUSE * drag, "flex": True})
    if slots and slots[-1]["type"] in ("pause", "gap"):
        slots.pop()                              # silêncio final não conta para a janela

    fixed = sum(s["dur"] for s in slots if not s["flex"])
    flex = sum(s["dur"] for s in slots if s["flex"])
    room = (w1 - w0) - fixed
    if room <= 0 or flex <= 0:
        raise ValueError(f"cena {scene['scene']}: janela {w0}-{w1}s menor que as partes fixas ({fixed:.2f}s)")
    k = room / flex

    t = w0
    out: dict[str, dict] = {}
    syl_total = 0
    word_time = 0.0
    for s in slots:
        d = s["dur"] * (k if s["flex"] else 1.0)
        if s["type"] == "fixed":
            item = s["item"]
            out[item["id"]] = {**item, "start": t, "end": t + d}
        elif s["type"] == "word":
            item, wd = s["item"], s["word"]
            rec = out.setdefault(item["id"], {**item, "start": t, "words": []})
            rec["words"].append({"w": wd["w"], "spoken": wd["spoken"], "punct": wd["punct"],
                                 "syl": wd["syl"], "start": t, "end": t + d})
            rec["end"] = t + d
            syl_total += wd["syl"]
            word_time += d
        t += d

    items = [out[i["id"]] for i, _ in entries]
    needed = fixed + flex
    stats = {
        "window": [w0, w1],
        "pace_target_syl_s": scene["pace_syl_s"],
        "syllables": syl_total,
        "articulation_syl_s": round(syl_total / word_time, 2) if word_time else 0.0,
        "overall_syl_s": round(syl_total / (w1 - w0), 2),
        "needed_s_at_target_pace": round(needed, 2),
        "available_s": round(w1 - w0, 2),
        "fit_ratio": round(k, 3),
    }
    stats["status"] = fit_status(k)
    return {"items": items, "stats": stats}


def fit_status(k: float) -> str:
    if k < 0.70:
        return "ESTOURA"      # precisa falar >40% mais rápido que o pretendido
    if k < 0.85:
        return "apertado"
    if k > 1.6:
        return "folgado"
    return "ok"


def derive_breaths(items: list[dict], min_gap: dict[str, float] | None = None) -> list[dict]:
    """Eventos de inspiração para a câmera: explícitos (do roteiro) + implícitos
    (um respiro antes de cada frase, se a pausa antes dela for >= `min_gap` da cena; padrão 0,3 s —
    personagem ofegante usa um valor menor)."""
    min_gap = min_gap or {}
    events = []
    for idx, it in enumerate(items):
        if it["kind"] != "breath":
            continue
        shape = BREATH_SHAPES[it["type"]]
        cycles = shape.get("cycles", 1)
        dur = (it["end"] - it["start"]) / cycles
        inhale, hold, exhale = dur * shape["in"], dur * shape["hold"], dur * shape["out"]
        if exhale <= 0:     # a expiração acontece falando a frase seguinte
            nxt = next((n for n in items[idx + 1:] if n["kind"] == "speech"), None)
            exhale = min(4.0, max(0.4, nxt["end"] - (it["start"] + inhale))) if nxt else 0.6
        for c in range(cycles):
            events.append({"t": it["start"] + c * dur, "inhale": inhale, "hold": hold, "exhale": exhale,
                           "amp": shape["amp"], "type": it["type"], "ref": it["id"], "explicit": True})
    explicit_marks = [(e["t"], e["t"] + e["inhale"] + e["hold"]) for e in events]
    for it in items:
        if it["kind"] != "speech":
            continue
        if any(a - 0.05 <= it["start"] <= b + 0.15 for a, b in explicit_marks):
            continue                           # já veio de um respiro explícito colado
        prev_end = max([e["end"] for e in items if e["end"] <= it["start"]] or [0.0])
        gap = it["start"] - prev_end
        if gap < min_gap.get(it.get("scene"), 0.3):
            continue
        inhale = min(0.35, max(0.12, gap * 0.7))
        events.append({"t": it["start"] - inhale, "inhale": inhale, "hold": 0.0,
                       "exhale": min(5.0, max(0.5, it["end"] - it["start"])), "amp": 0.8,
                       "type": "inhale_phrase", "ref": it["id"], "explicit": False})
    return sorted(events, key=lambda e: e["t"])
