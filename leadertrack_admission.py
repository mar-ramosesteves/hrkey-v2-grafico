"""Admission-only eligibility for LEVEN individual feedback, not executive snapshots."""

from datetime import date
import hashlib
import json
import os
import requests

ADMISSION_VERSION = "admission_v1"
MINIMUM_DAYS = 90
MINIMUM_RESPONDENTS = 3


def admission_enabled(round_code):
    # Enable only after the admission view and all consumers have been published.
    rounds = {r.strip().lower() for r in os.getenv("LEADERTRACK_ADMISSION_ROUNDS", "").split(",") if r.strip()}
    return str(round_code or "").strip().lower() in rounds


def fetch_admission_rows(rest_url, headers, company, round_code, leader, get=None):
    get = get or requests.get
    rows = []
    for offset in range(0, 10000, 1000):
        response = get(f"{rest_url}/v_leadertrack_respostas_classificadas", headers=headers, params={
            "select": "modulo,resposta_id,email_respondente,email_lider_avaliado,tipo_relacao_lider,holding,admission_date,data_criacao,dados_json",
            "empresa": f"eq.{str(company).lower()}", "codrodada": f"ilike.{str(round_code).lower()}",
            "email_lider_avaliado": f"eq.{str(leader).lower()}", "order": "modulo,resposta_id",
            "limit": 1000, "offset": offset,
        }, timeout=30)
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Resposta invalida ao consultar a amostra.")
        rows.extend(page)
        if len(page) < 1000:
            break
    else:
        raise ValueError("Amostra excedeu o limite de leitura; nenhum calculo parcial foi utilizado.")
    if not rows:
        raise ValueError("Respostas originais indisponiveis; nao foi usado grafico antigo.")
    if any(str(r.get("holding") or "").strip().upper() != "LEVEN"
           for r in rows if r.get("tipo_relacao_lider") != "AUTOAVALIACAO"):
        raise ValueError("Cadastro/contexto incompleto na amostra; revisar antes de calcular.")
    return rows


def raw_answers(row):
    value = row.get("dados_json") or {}
    return json.loads(value) if isinstance(value, str) else dict(value)


def filtered_consolidated(rows, module):
    eligible, self_rows, meta = select_sample(rows, module)
    if meta["insuficiente"]:
        raise ValueError(f"Amostra insuficiente: {meta['elegiveis_media']} respostas elegiveis por admissao; minimo de 3.")
    return {"autoavaliacao": raw_answers(self_rows[0]) if self_rows else {},
            "avaliacoesEquipe": [raw_answers(r) for r in eligible], "amostra": meta}

# The individual microenvironment API maps form order to matrix order this way.
# Do not change the executive pipeline's independent mapping in this module.
MICRO_FORM_KEYS = dict(zip(
    [f"Q{i:02d}" for i in range(1, 49)],
    sorted((f"Q{i:02d}" for i in range(1, 49)), key=lambda q: str(int(q[1:]))),
))


def admission_day(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None


def temporal_status(row):
    admitted = admission_day(row.get("admission_date"))
    responded = admission_day(row.get("data_criacao"))
    if not admitted or not responded or admitted > responded:
        return "pending"
    return "eligible" if (responded - admitted).days >= MINIMUM_DAYS else "recent"


def select_sample(rows, module):
    selected = []
    seen = set()
    # Keep the first submission per respondent, as the existing consolidators do.
    for row in sorted(rows, key=lambda r: (r.get("data_criacao") or "", r.get("resposta_id") or "")):
        if row.get("modulo") != module:
            continue
        email = str(row.get("email_respondente") or "").strip().lower()
        if not email:
            raise ValueError("Resposta sem identificacao; amostra nao pode ser validada.")
        kind = "self" if row.get("tipo_relacao_lider") == "AUTOAVALIACAO" else "team"
        key = (kind, email)
        if key not in seen:
            selected.append((kind, row))
            seen.add(key)
    team = [r for kind, r in selected if kind == "team"]
    eligible = [r for r in team if temporal_status(r) == "eligible"]
    self_rows = [r for kind, r in selected if kind == "self"]
    meta = {
        "criterio_elegibilidade": ADMISSION_VERSION,
        "respostas_equipe": len(team),
        "elegiveis_media": len(eligible),
        "menos_de_3_meses": sum(temporal_status(r) == "recent" for r in team),
        "pendentes_admissao": sum(temporal_status(r) == "pending" for r in team),
        "respostas_utilizadas": len(eligible) if len(eligible) >= MINIMUM_RESPONDENTS else 0,
        "insuficiente": len(eligible) < MINIMUM_RESPONDENTS,
        "autoavaliacoes": len(self_rows),
        "escopo_amostra": "Avaliacoes ao lider na empresa selecionada (direta e funcional).",
    }
    return eligible, self_rows, meta


def answers(row, micro=False):
    value = row.get("dados_json") or {}
    if isinstance(value, str):
        value = json.loads(value)
    value = value.get("respostas", value)
    if not isinstance(value, dict):
        raise ValueError("Respostas LeaderTrack em formato invalido.")
    if not micro:
        return {k: v for k, v in value.items() if str(k).startswith("Q")}
    return {q + suffix: value[form + suffix]
            for q, form in MICRO_FORM_KEYS.items() for suffix in ("C", "k")
            if form + suffix in value}


def sample_fingerprint(rows):
    # No identities or raw answers leave the server through this fingerprint.
    items = [(r.get("modulo"), r.get("resposta_id"), r.get("admission_date"),
              r.get("data_criacao"), r.get("dados_json")) for r in rows]
    payload = json.dumps(sorted(items, key=lambda r: str(r[:2])), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_individual_reports(rows, calculator):
    reports = {}
    for module in ("arquetipos", "microambiente"):
        eligible, self_rows, meta = select_sample(rows, module)
        used = [] if meta["insuficiente"] else eligible
        team_answers = [answers(r, micro=module == "microambiente") for r in used]
        self_answers = [answers(r, micro=module == "microambiente") for r in self_rows]
        blocks = calculator(module, team_answers, self_answers)
        for key, block in blocks.items():
            block = dict(block or {})
            block["amostra"] = dict(meta)
            block["amostra"]["autoavaliacao"] = "grafico_autoavaliacao" in key
            block["criterio_elegibilidade"] = ADMISSION_VERSION
            block["respostas_equipe"] = meta["respostas_equipe"]
            block["elegiveis_media"] = meta["elegiveis_media"]
            block["info_avaliacoes"] = f"Equipe: {meta['respostas_utilizadas']} respostas utilizadas"
            block["escopo"] = "lider_individual"
            reports[key] = block
    return reports

