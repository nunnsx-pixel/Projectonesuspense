"""Orquestra um episódio: fontes -> linha do tempo sincronizada -> build/."""
from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from pathlib import Path

from . import camera, narration, overview, sfx
from .timeline import FPS, ROOT, Resolver, keys_out_of_order, snap, tc, to_frame

CSV_COLUMNS = [
    "frame", "t", "scene",
    "shake_x_cm", "shake_y_cm", "shake_z_cm", "shake_yaw", "shake_pitch", "shake_roll",
    "look_yaw", "look_pitch", "look_roll", "fov_pct",
    "vignette", "edge_blur", "eyelid", "black",
    "breath", "heart", "speed_kmh", "step",
]
OPTIONAL_COLUMNS = ("light", "motion_blur", "bump", "red_fog")     # entram no CSV só se camera.json pedir em `csv_extra`


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mmss(s: str) -> float:
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def _norm_text(s: str) -> str:
    s = s.replace("…", "...").replace("*", "")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().lower()


def _round(obj, nd=4):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def build_episode(ep_id: str, root: Path = ROOT, write: bool = True, use_measured: bool = True) -> dict:
    """`use_measured=False` ignora narration.measured.json (devolve a linha do tempo ESTIMADA; usado pela análise de áudio)."""
    project = _load(root / "scenes-config.json")
    ep = next((e for e in project["episodes"] if e["id"] == ep_id), None)
    if ep is None:
        raise SystemExit(f"episódio {ep_id!r} não existe em scenes-config.json")
    ep_dir = root / ep_id
    duration = float(ep["duration_seconds"])
    n_frames = int(round(duration * FPS))
    warnings: list[str] = []

    # ---- cenas (janelas vêm do scenes-config.json) ------------------------------
    scene_files = [_load(p) for p in sorted((ep_dir / "scenes").glob("*.json"))]
    scenes = []
    for sf in scene_files:
        cfg_scene = ep["scenes"][sf["config_index"]]
        if cfg_scene["description"] != sf["name"]:
            raise ValueError(f"cena {sf['id']}: nome difere de scenes-config.json "
                             f"({sf['name']!r} != {cfg_scene['description']!r})")
        scenes.append({**sf, "start": _mmss(cfg_scene["start"]), "end": _mmss(cfg_scene["end"]),
                       "config": cfg_scene})
    scenes.sort(key=lambda s: s["start"])
    if scenes[0]["start"] != 0 or scenes[-1]["end"] != duration or \
            any(a["end"] != b["start"] for a, b in zip(scenes, scenes[1:])):
        raise ValueError("as janelas das cenas não cobrem 0..duração sem buracos")
    windows = [(s["id"], s["start"], s["end"]) for s in scenes]

    res = Resolver()
    res.scenes = {sid: (a, b) for sid, a, b in windows}

    # ---- narração ---------------------------------------------------------------
    narr = _load(ep_dir / "narration.json")
    pauses = {**narration.DEFAULT_PAUSES, **narr.get("pauses", {})}
    items, fits = [], {}
    for nsc in narr["scenes"]:
        sc = next(s for s in scenes if s["id"] == nsc["scene"])
        w0, w1 = nsc["window"]
        if not (sc["start"] <= w0 < w1 <= sc["end"]):
            raise ValueError(f"janela da narração {nsc['scene']} fora da cena {sc['start']}-{sc['end']}")
        script = " ".join(i["text"] for i in nsc["items"] if i["kind"] == "speech" and not i.get("skip"))
        if _norm_text(script) != _norm_text(sc["config"]["dialogue"]):
            raise ValueError(f"texto da narração {nsc['scene']} difere do dialogue em scenes-config.json")
        out = narration.layout_scene(nsc, narr.get("lexicon", {}), pauses)
        for it in out["items"]:
            it["scene"] = nsc["scene"]
            it["timing"] = "estimado"
            items.append(it)
        fits[nsc["scene"]] = out["stats"]
        if out["stats"]["status"] in ("ESTOURA", "apertado"):
            st = out["stats"]
            warnings.append(
                f"{nsc['scene']}: fala {st['status'].upper()} — precisa de {st['needed_s_at_target_pace']}s no ritmo "
                f"pretendido ({st['pace_target_syl_s']} sil/s) e a janela tem {st['available_s']}s "
                f"(fala efetiva a {st['articulation_syl_s']} sil/s). Corte falas com \"skip\": true em narration.json.")
    measured_file = ep_dir / "narration.measured.json"
    if use_measured and measured_file.exists():
        measured = _load(measured_file)["items"]
        unknown = set(measured) - {i["id"] for i in items}
        if unknown:
            raise ValueError(f"narration.measured.json cita ids inexistentes/pulados: {sorted(unknown)}")
        for it in items:
            if it["id"] in measured:
                m = measured[it["id"]]
                _retime(it, m["start"], m["end"], m.get("pauses"))
                it["timing"] = "medido"
    for it in items:
        _snap_item(it)
    items.sort(key=lambda i: i["start"])
    for a, b in zip(items, items[1:]):
        if b["start"] < a["end"] - 1e-6:
            raise ValueError(f"itens de narração sobrepostos: {a['id']} / {b['id']}")
    for it in items:
        res.items[it["id"]] = it

    # ---- beats e cues (âncoras) ---------------------------------------------------
    sfx_cfg = _load(ep_dir / "sfx.json")
    for s in scenes:
        res.register("beat", s["beats"])
    res.register("cue", sfx_cfg["cues"])
    beats = []
    for s in scenes:
        for b in s["beats"]:
            start, end = res.span("beat", b["id"])
            beats.append({**b, "scene": s["id"], "start": start, "end": end})
            _check_inside(f"beat {b['id']}", start, end, duration)

    # ---- câmera -----------------------------------------------------------------
    cam_cfg = _load(ep_dir / "camera.json")
    breath_events = narration.derive_breaths(
        items, {n["scene"]: n["breath_min_gap"] for n in narr["scenes"] if "breath_min_gap" in n})
    speech_spans = [(i["start"] - 0.3, i["end"]) for i in items if i["kind"] == "speech"]
    cam = camera.build(cam_cfg, res, breath_events, speech_spans, windows, duration)
    for name, spec in cam_cfg.get("curves", {}).items():
        if not name.startswith("_"):
            for a, b in keys_out_of_order(spec, res):
                warnings.append(f"câmera: curva {name!r} com chaves fora de ordem ({a:.3f}s depois {b:.3f}s) — "
                                f"a âncora andou para trás (fala medida mais curta?); o valor pode ficar preso")

    # ---- SFX (cues + passos da câmera) ----------------------------------------------
    sfx_out = sfx.build(sfx_cfg, res, cam["steps"], cam_cfg.get("seed", 348), windows, cam_cfg.get("gait_table"),
                        cam["bumps"], cam["flickers"], cam_cfg.get("flicker", {}).get("sfx"), cam["heartbeats"])
    columns = CSV_COLUMNS + [c for c in cam_cfg.get("csv_extra", []) if c in OPTIONAL_COLUMNS]
    for cue in sfx_out["cues"]:
        _check_inside(f"cue {cue['id']}", cue["start"], cue["end"], duration)
        pfs = cue.pop("pitch_from_speed", None)
        if pfs:
            speed = cam["curves"]["speed_kmh"]
            t0, t1 = speed.pts[0][0], speed.pts[-1][0]
            keys = [[0.0, 0.0]] if t0 > 0 else []
            t = math.floor(t0)
            while t <= t1 + 1.0:
                keys.append([float(t), round(pfs["max_semitones"] * min(1.0, speed(t) / pfs["max_kmh"]), 3)])
                t += 1
            cue.setdefault("automation", {})["pitch_semitones"] = keys
    for ch in cam["rows"]:
        for key in columns[3:]:
            if isinstance(ch[key], float) and not math.isfinite(ch[key]):
                raise ValueError(f"valor inválido na câmera, frame {ch['frame']}, coluna {key}")
    if len(cam["rows"]) != n_frames:
        raise ValueError("número de frames da câmera difere da duração")
    for it in items:
        if it["kind"] == "speech" and any(it["start"] < b and it["end"] > a for a, b in cam["black_ranges"]):
            warnings.append(f"{it['id']} cai numa faixa de tela preta")

    timeline = _assemble(project, ep, scenes, items, fits, beats, breath_events, cam, sfx_out, n_frames,
                         duration, warnings, columns, narr.get("speakers"))
    if write:
        _write(ep_dir / "build", ep_id, timeline, cam["rows"], columns)
    timeline["_cam"] = cam          # uso interno (testes); não vai para o JSON
    return timeline


def match_pauses(it: dict, start: float, end: float, pauses) -> list[tuple[float, float]]:
    """Casa as pausas INTERNAS medidas (silêncios dentro da fala) com as pausas de pontuação estimadas do item.

    Devolve os nós (tempo estimado -> tempo medido) do mapeamento por partes, em ordem crescente. Alinhamento
    monótono (estilo Needleman-Wunsch) pela posição relativa dentro do item; só casa o que está a menos de 0,3 do
    comprimento do item, e o resto fica sem nó (interpola)."""
    words = it.get("words", [])
    est = [(a["end"], b["start"]) for a, b in zip(words, words[1:]) if b["start"] - a["end"] >= 0.05]
    mea = sorted((max(a, start), min(b, end)) for a, b in (pauses or []) if min(b, end) - max(a, start) >= 0.08)
    if not est or not mea:
        return []
    old_s, old_e = it["start"], it["end"]
    span_e, span_m = max(old_e - old_s, 1e-9), max(end - start, 1e-9)
    re_ = [((a + b) / 2 - old_s) / span_e for a, b in est]
    rm = [((a + b) / 2 - start) / span_m for a, b in mea]
    UN = 0.25                                                   # custo de deixar uma pausa sem par
    n, m = len(est), len(mea)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            opts = []
            if i:
                opts.append((best[i - 1][j] + UN, "e"))
            if j:
                opts.append((best[i][j - 1] + UN, "m"))
            if i and j and abs(re_[i - 1] - rm[j - 1]) <= 0.3:
                opts.append((best[i - 1][j - 1] + abs(re_[i - 1] - rm[j - 1]), "x"))
            best[i][j], back[i][j] = min(opts)
    pairs, i, j = [], n, m
    while i or j:
        step = back[i][j]
        if step == "x":
            pairs.append((est[i - 1], mea[j - 1]))
            i, j = i - 1, j - 1
        elif step == "e":
            i -= 1
        else:
            j -= 1
    knots: list[tuple[float, float]] = []
    for (ea, eb), (ma, mb) in reversed(pairs):
        for k in ((ea, ma), (eb, max(mb, ma + 1e-6))):
            if not knots or (k[0] > knots[-1][0] and k[1] > knots[-1][1]):
                knots.append(k)
    return [k for k in knots if old_s < k[0] < old_e and start < k[1] < end]


def _retime(it: dict, start: float, end: float, pauses=None) -> None:
    """Move/estica um item (e suas palavras) para o intervalo medido na gravação.

    Sem `pauses`, as palavras se redistribuem proporcionalmente. Com `pauses` (silêncios internos medidos no áudio),
    o mapeamento é linear POR PARTES: cada pausa de pontuação estimada cai na pausa medida e as palavras entre
    elas se esticam no que sobra (as âncoras por palavra ficam certas mesmo em falas com reticências)."""
    old_s, old_e = it["start"], it["end"]
    knots = [(old_s, start)] + (match_pauses(it, start, end, pauses) if pauses else []) + [(old_e, end)]

    def f(t: float) -> float:
        if old_e <= old_s:
            return start
        for (t0, m0), (t1, m1) in zip(knots, knots[1:]):
            if t <= t1 or (t1, m1) == knots[-1]:
                return m0 + (t - t0) * (m1 - m0) / (t1 - t0) if t1 > t0 else m0
        return end

    for w in it.get("words", []):
        w["start"] = f(w["start"])
        w["end"] = f(w["end"])
    it["start"], it["end"] = start, end


def _snap_item(it: dict) -> None:
    prev = None
    for w in it.get("words", []):
        w["start"], w["end"] = snap(w["start"]), max(snap(w["end"]), snap(w["start"]) + 1 / FPS)
        if prev is not None and w["start"] < prev["end"]:
            w["start"] = prev["end"]
            w["end"] = max(w["end"], w["start"] + 1 / FPS)
        prev = w
    it["start"] = it["words"][0]["start"] if it.get("words") else snap(it["start"])
    it["end"] = it["words"][-1]["end"] if it.get("words") else snap(it["end"])


def _check_inside(what: str, start: float, end: float, duration: float) -> None:
    if start < -1e-6 or end > duration + 1e-6:
        raise ValueError(f"{what} fora do episódio: {start:.3f}-{end:.3f}s")


def _assemble(project, ep, scenes, items, fits, beats, breath_events, cam, sfx_out, n_frames, duration,
              warnings, columns, speakers=None) -> dict:
    def stamp(d: dict, *keys: str) -> dict:
        out = dict(d)
        for k in keys:
            out[f"{k}_frame"] = to_frame(d[k])
            out[f"{k}_tc"] = tc(d[k])
        return out

    return _round({
        "project": project["project"], "episode": ep["id"], "title": ep["title"],
        "fps": FPS, "resolution": project["resolution"], "duration_s": duration, "frames": n_frames,
        "conventions": {
            "units": "segundos (t) e frames (_frame, @60fps); timecode MM:SS.mmm (_tc)",
            "axes": "+X direita, +Y cima, +Z frente; yaw+ direita, pitch+ cima, roll+ inclina p/ direita; ordem YXZ",
            "camera_csv": "shake_* = camada ADITIVA (cm e graus); look_* = intenção de olhar; "
                          "rotação final = look + shake. fov_pct = variação % do FOV.",
            "narration_timing": "ESTIMADO por sílabas e pontuação (ainda sem gravação).",
        },
        "warnings": warnings,
        **({"speakers": speakers} if speakers else {}),
        "scenes": [{
            "id": s["id"], "name": s["name"], **stamp({"start": s["start"], "end": s["end"]}, "start", "end"),
            "set": s.get("set"), "narration_fit": fits.get(s["id"]),
            "beats": [stamp(b, "start", "end") for b in beats if b["scene"] == s["id"]],
        } for s in scenes],
        "narration": [_stamp_item(i, stamp) for i in items],
        "breaths": breath_events,
        "sfx": {
            "cues": [stamp(c, "start", "end") for c in sfx_out["cues"]],
            "footsteps": [stamp(f, "start") for f in sfx_out["footsteps"]],
            **({"bumps": [stamp(f, "start") for f in sfx_out["bumps"]]} if sfx_out["bumps"] else {}),
            **({"flicker": [stamp(f, "start", "end") for f in sfx_out["flicker"]]} if sfx_out["flicker"] else {}),
            **({"heartbeat": [stamp(f, "start") for f in sfx_out["heartbeat"]]} if sfx_out["heartbeat"] else {}),
            "mix": sfx_out["mix"],
        },
        "camera": {
            "file": f"{ep['id']}.camera.csv", "columns": columns,
            "steps": [{"t": s["t"], "frame": to_frame(s["t"]), "segment": s["seg"], "cadence": s["cadence"]}
                      for s in cam["steps"]],
            "look": [{k: v for k, v in k_.items() if k != "at"} for k_ in cam["look_keys"]],
            "kicks": [{k: v for k, v in k_.items() if k != "at"} for k_ in cam["kicks"]],
            "pulses": [{k: v for k, v in k_.items() if k != "at"} for k_ in cam["pulses"]],
            "heartbeats": [round(b[0], 3) for b in cam["heartbeats"] if b[0] < duration],
            "breath_cycles": cam["breath_cycles"],
            "black_ranges": [[a, b] for a, b in cam["black_ranges"]],
            **({"bumps": [{"t": b["t"], "frame": to_frame(b["t"]), "size": b["size"], "segment": b["seg"]}
                          for b in cam["bumps"]]} if cam["bumps"] else {}),
            **({"flicker": cam["flickers"]} if cam["flickers"] else {}),
        },
    })


def _stamp_item(item: dict, stamp) -> dict:
    out = stamp(item, "start", "end")
    if "words" in item:
        out["words"] = [stamp(w, "start", "end") for w in item["words"]]
    return out


def _write(out_dir: Path, ep_id: str, timeline: dict, rows: list[dict], columns: list[str]) -> None:
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{ep_id}.timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(out_dir / f"{ep_id}.camera.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([(f"{r[c]:.5f}" if c == "t" else f"{r[c]:.4f}") if isinstance(r[c], float) else r[c]
                        for c in columns])
    (out_dir / f"{ep_id}.cue-sheet.md").write_text(cue_sheet(timeline), encoding="utf-8")
    (out_dir / f"{ep_id}.overview.svg").write_text(overview.render(timeline, rows), encoding="utf-8")


def cue_sheet(tl: dict) -> str:
    """Lista cronológica legível de TUDO que acontece (voz, respiro, SFX, câmera)."""
    ev: list[tuple[float, int, str, str]] = []

    def add(t, lane, text, order=5):
        ev.append((t, order, lane, text))

    for s in tl["scenes"]:
        add(s["start"], "CENA", f"**{s['id']} — {s['name']}**", 0)
        for b in s["beats"]:
            add(b["start"], "BEAT", f"`{b['id']}` {b['text']}" + (" _(inferido)_" if b.get("origin") == "inferido" else ""), 1)
    for i in tl["narration"]:
        if i["kind"] == "speech":
            how = f" _[{i['direction']}]_" if i.get("direction") else ""
            who = f" **{i['speaker']}**" if i.get("speaker") else ""
            add(i["start"], "VOZ", f"`{i['id']}`{who}{how} “{i['text']}” _(até {tc(i['end'])})_", 2)
        elif i["kind"] == "silence":
            add(i["start"], "SILÊNCIO", f"`{i['id']}` {i['label']} _(até {tc(i['end'])})_", 2)
        else:
            add(i["start"], "RESPIRO", f"`{i['id']}` {i['label']} _(até {tc(i['end'])})_", 2)
    for c in tl["sfx"]["cues"]:
        tag = " _(inferido)_" if c.get("origin") == "inferido" else ""
        span = f" _(até {tc(c['end'])})_" if c["end"] > c["start"] else ""
        add(c["start"], "SFX", f"`{c['id']}` {c['desc']}{span}{tag}", 3)
    by_seg: dict[str, list[dict]] = {}
    for f in tl["sfx"]["footsteps"]:
        by_seg.setdefault(f["segment"], []).append(f)
    for seg, fs in by_seg.items():
        add(fs[0]["start"], "PASSOS", f"`{seg}` {len(fs)} passos até {tc(fs[-1]['start'])} — {fs[0]['surface']} "
            f"({fs[0]['origin']}); cada passo = frame de contato da câmera", 3)
    beats_ = tl["sfx"].get("heartbeat", [])
    if beats_:
        add(beats_[0]["start"], "CORAÇÃO", f"{len(beats_)} batimentos de {tc(beats_[0]['start'])} a {tc(beats_[-1]['start'])} "
            f"({beats_[0]['bpm']:g}→{beats_[-1]['bpm']:g} bpm; {beats_[0]['gain_db']:g}→{beats_[-1]['gain_db']:g} dB): "
            f"cada um cai no frame do pulso da câmera (`heart` no CSV) — o som e o tremor são o mesmo evento", 3)
    bumps = tl["sfx"].get("bumps", [])
    for seg in dict.fromkeys(b["segment"] for b in bumps):
        bs = [b for b in bumps if b["segment"] == seg]
        add(bs[0]["start"], "ESTRADA", f"`{seg}` {len(bs)} batidas até {tc(bs[-1]['start'])} ({bs[0]['origin']}); "
            f"cada batida = solavanco da câmera (`bump=1` no CSV) + SFX no mesmo frame", 3)
    lamp = tl["sfx"].get("flicker", [])
    for e in lamp:
        if e["origin_event"] == "marcado":
            add(e["start"], "LUZ", f"apaga {round((e['end'] - e['start']) * 60)} frames (profundidade {e['depth']:g})", 3)
    if lamp:
        rnd = [e for e in lamp if e["origin_event"] != "marcado"]
        add(lamp[0]["start"], "LUZ", f"{len(rnd)} falhas elétricas em rajadas aleatórias (semente fixa) de "
            f"{tc(min(e['start'] for e in rnd))} a {tc(max(e['start'] for e in rnd))}; cada uma = queda do canal `light` "
            f"+ SFX `{lamp[0]['tag']}` no mesmo frame", 3)
    for k in tl["camera"]["look"]:
        pose = f"yaw {k['yaw']:+g}°, pitch {k['pitch']:+g}°" + (f", roll {k['roll']:+g}°" if k.get("roll") else "")
        add(k["t"], "OLHAR", pose + (f" — {k['note']}" if k.get("note") else ""), 4)
    for k in tl["camera"]["kicks"] + tl["camera"]["pulses"]:
        if k.get("note"):
            add(k["t"], "IMPACTO", f"`{k['id']}` {k['note']}", 4)
    for a, b in tl["camera"]["black_ranges"]:
        add(a, "FX", "corte seco para preto absoluto" if b >= tl["duration_s"]
            else f"tela preta de {b - a:g}s (até {tc(b)})", 4)
    ev.sort(key=lambda e: (e[0], e[1]))

    lines = [f"# Cue sheet — {tl['episode']} · {tl['title']}", "",
             f"{tl['duration_s']:g}s · {tl['frames']} frames @{tl['fps']}fps · {tl['resolution']}. "
             "Gerado por `python -m pipeline build` — não edite à mão.", ""]
    if tl["warnings"]:
        lines += ["## ⚠️ Avisos", ""] + [f"- {w}" for w in tl["warnings"]] + [""]
    lines += ["## Orçamento de fala por cena", "",
              "| Cena | Janela | Sílabas | Precisa* | Cabe | Fala efetiva | Situação |", "|---|---|---|---|---|---|---|"]
    for s in tl["scenes"]:
        f = s["narration_fit"]
        lines.append(f"| {s['id']} | {tc(f['window'][0])}–{tc(f['window'][1])} | {f['syllables']} | "
                     f"{f['needed_s_at_target_pace']}s | {f['available_s']}s | {f['articulation_syl_s']} sil/s "
                     f"(alvo {f['pace_target_syl_s']}) | **{f['status']}** |")
    lines += ["", "\\* tempo que a fala pede no ritmo pretendido da cena.", "",
              "## Linha do tempo", "", "| Tempo | Frame | Trilha | Evento |", "|---|---|---|---|"]
    for t, _, lane, text in ev:
        lines.append(f"| {tc(t)} | {to_frame(t)} | {lane} | {text} |")
    return "\n".join(lines) + "\n"
