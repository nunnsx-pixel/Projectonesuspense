"""Painel SVG com todas as trilhas no mesmo eixo de tempo (para conferir a sincronia a olho)."""
from __future__ import annotations

from html import escape

PX = 30            # pixels por segundo
LEFT = 150
COL = {"voz": "#3b82f6", "respiro": "#f59e0b", "implicito": "#9ca3af", "sfx": "#10b981",
       "inferido": "#6ee7b7", "passo": "#ef4444", "linha": "#111827", "grade": "#e5e7eb"}


def render(tl: dict, rows: list[dict]) -> str:
    dur = tl["duration_s"]
    width = LEFT + int(dur * PX) + 20
    out: list[str] = []
    y = 10

    def x(t):
        return LEFT + t * PX

    def lane(label: str, h: int) -> int:
        nonlocal y
        out.append(f'<text x="8" y="{y + 14}" font-size="12" font-weight="600">{escape(label)}</text>')
        out.append(f'<rect x="{LEFT}" y="{y}" width="{dur * PX}" height="{h}" fill="#fafafa" stroke="{COL["grade"]}"/>')
        top = y
        y += h + 8
        return top

    def series(top: int, h: int, key: str, lo: float, hi: float, color: str, w: float = 1.0, every: int = 2):
        pts = " ".join(f"{x(r['t']):.1f},{top + h - (r[key] - lo) / (hi - lo) * h:.1f}" for r in rows[::every])
        out.append(f'<polyline fill="none" stroke="{color}" stroke-width="{w}" points="{pts}"/>')

    def label(top: int, text: str):
        out.append(f'<text x="{LEFT + 4}" y="{top + 11}" font-size="9" fill="#6b7280">{escape(text)}</text>')

    head_h = 22
    top = lane("tempo (s)", head_h)
    for s in range(0, int(dur) + 1, 5):
        out.append(f'<text x="{x(s) + 2}" y="{top + 14}" font-size="10">{s}s</text>')
    grid_top = top
    top = lane("cenas", 22)
    for i, s in enumerate(tl["scenes"]):
        out.append(f'<rect x="{x(s["start"])}" y="{top}" width="{(s["end"] - s["start"]) * PX}" height="22" '
                   f'fill="{["#dbeafe", "#fce7f3", "#e0e7ff"][i % 3]}" stroke="#94a3b8"/>')
        out.append(f'<text x="{x(s["start"]) + 4}" y="{top + 15}" font-size="11">{escape(s["id"])} · {escape(s["name"])}</text>')
        for b in s["beats"]:
            out.append(f'<line x1="{x(b["start"])}" x2="{x(b["start"])}" y1="{top + 17}" y2="{top + 22}" stroke="#334155"/>')

    top = lane("voz / respiros", 36)
    for i, it in enumerate(tl["narration"]):
        w = max(1.5, (it["end"] - it["start"]) * PX)
        col = COL["voz"] if it["kind"] == "speech" else COL["respiro"]
        yy = top + 3 + (i % 2) * 16
        out.append(f'<rect x="{x(it["start"])}" y="{yy}" width="{w}" height="14" fill="{col}" opacity="0.85"/>')
        out.append(f'<text x="{x(it["start"]) + 2}" y="{yy + 11}" font-size="9" fill="#fff">{escape(it["id"])}</text>')
        for wd in it.get("words", []):
            out.append(f'<line x1="{x(wd["start"])}" x2="{x(wd["start"])}" y1="{yy + 10}" y2="{yy + 14}" stroke="#fff" opacity=".6"/>')

    beds = [c for c in tl["sfx"]["cues"] if c["end"] - c["start"] > 0.5]
    ones = [c for c in tl["sfx"]["cues"] if c["end"] - c["start"] <= 0.5]
    top = lane("sfx", 14 + 14 * len(beds) + 30)
    for i, c in enumerate(beds):
        yy = top + 3 + i * 14
        out.append(f'<rect x="{x(c["start"])}" y="{yy}" width="{(c["end"] - c["start"]) * PX}" height="11" fill="{COL["sfx"]}" opacity=".55"/>')
        out.append(f'<text x="{x(c["start"]) + 3}" y="{yy + 9}" font-size="9">{escape(c["id"])}</text>')
    base = top + 3 + len(beds) * 14
    for i, c in enumerate(ones):
        col = COL["inferido"] if c.get("origin") == "inferido" else COL["sfx"]
        out.append(f'<line x1="{x(c["start"])}" x2="{x(c["start"])}" y1="{base}" y2="{base + 14}" stroke="{col}" stroke-width="2"/>')
        out.append(f'<text x="{x(c["start"]) + 3}" y="{base + 9 + (i % 2) * 11}" font-size="9">{escape(c["id"])}</text>')
    for f in tl["sfx"]["footsteps"]:
        out.append(f'<line x1="{x(f["start"])}" x2="{x(f["start"])}" y1="{base + 26}" y2="{base + 38}" stroke="{COL["passo"]}"/>')

    h = 60
    top = lane("cabeça: subir/descer (y cm)", h)
    for st in tl["camera"]["steps"]:
        out.append(f'<line x1="{x(st["t"])}" x2="{x(st["t"])}" y1="{top}" y2="{top + h}" stroke="{COL["passo"]}" opacity=".35"/>')
    series(top, h, "shake_y_cm", -5, 5, COL["linha"], 0.8)
    label(top, "linhas vermelhas = pisadas (== SFX de passos)")

    top = lane("peito (respiração)", 44)
    for b in tl["breaths"]:
        col = COL["respiro"] if b["explicit"] else COL["implicito"]
        out.append(f'<line x1="{x(b["t"])}" x2="{x(b["t"])}" y1="{top}" y2="{top + 44}" stroke="{col}" stroke-width="2" opacity=".7"/>')
    series(top, 44, "breath", 0, 1.9, "#b45309", 1.2)
    label(top, "laranja = respiro do roteiro · cinza = respiro implícito antes da frase")

    top = lane("coração", 30)
    series(top, 30, "heart", 0, 1.6, "#dc2626", 0.7, every=1)

    top = lane("olhar yaw / pitch (°)", 70)
    series(top, 70, "look_yaw", -90, 90, "#2563eb", 1.3)
    series(top, 70, "look_pitch", -90, 90, "#16a34a", 1.3)
    label(top, "azul = yaw (esq−/dir+) · verde = pitch (baixo−/cima+)")

    top = lane("ônibus (km/h)", 28)
    series(top, 28, "speed_kmh", 0, 70, "#7c3aed", 1.4)

    top = lane("tela: vinheta / blur / pálpebra", 50)
    series(top, 50, "vignette", 0, 1, "#111827", 1.3)
    series(top, 50, "edge_blur", 0, 1, "#0891b2", 1.3)
    series(top, 50, "eyelid", 0, 1, "#be123c", 1.3)
    label(top, "preto = vinheta · ciano = blur de borda · vinho = pálpebra")

    for s in range(0, int(dur) + 1, 5):
        out.append(f'<line x1="{x(s)}" x2="{x(s)}" y1="{grid_top}" y2="{y - 8}" stroke="{COL["grade"]}" stroke-dasharray="2 3"/>')
    cut = tl["camera"]["cut_to_black_at"]
    out.append(f'<rect x="{x(cut)}" y="{grid_top}" width="{(dur - cut) * PX}" height="{y - 8 - grid_top}" fill="#000" opacity=".25"/>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{y + 6}" '
            f'font-family="system-ui, sans-serif"><rect width="100%" height="100%" fill="#fff"/>'
            + "".join(out) + "</svg>\n")
