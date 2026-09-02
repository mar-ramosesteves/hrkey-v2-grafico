"""Shared boundary for original graph APIs. Original consolidated rows are untouched."""
import json
import requests
from flask import g, has_request_context, request
from leadertrack_admission import (
    ADMISSION_VERSION, admission_enabled, fetch_admission_rows, raw_answers,
    sample_fingerprint, select_sample,
)


def get_eligible_consolidated(url, *, headers, params, timeout=30):
    def value(key):
        text = str(params.get(key) or "")
        return text.split(".", 1)[1] if text.startswith(("eq.", "ilike.")) else text
    company, round_code, leader = value("empresa"), value("codrodada"), value("emaillider")
    if not admission_enabled(round_code):
        return requests.get(url, headers=headers, params=params, timeout=timeout)
    module = "microambiente" if url.endswith("/consolidado_microambiente") else "arquetipos"
    rows = fetch_admission_rows(url.rsplit("/", 1)[0], headers, company, round_code, leader)
    eligible, own, meta = select_sample(rows, module)
    if has_request_context():
        g.leadertrack_admission_sample = meta
        g.leadertrack_admission_fingerprint = sample_fingerprint(rows)
    self_only = has_request_context() and "autoavaliacao" in request.path
    if meta["insuficiente"] and not self_only:
        raise ValueError(f"Amostra insuficiente: {meta['elegiveis_media']} respostas elegiveis por admissao; minimo de 3.")
    data = {"autoavaliacao": raw_answers(own[0]) if own else {},
            "avaliacoesEquipe": [raw_answers(r) for r in eligible] if not meta["insuficiente"] else [],
            "amostra": meta}
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps([{"dados_json": data}]).encode("utf-8")
    return response


def attach_admission_sample(data):
    sample = getattr(g, "leadertrack_admission_sample", None) if has_request_context() else None
    if not sample:
        return data
    was_string = isinstance(data, str)
    if was_string:
        data = json.loads(data)
    if isinstance(data, dict):
        data["amostra"] = dict(sample)
        data["criterio_elegibilidade"] = ADMISSION_VERSION
        data["amostra_fingerprint"] = g.leadertrack_admission_fingerprint
        data["respostas_equipe"] = sample["respostas_equipe"]
        data["elegiveis_media"] = sample["elegiveis_media"]
    return json.dumps(data, ensure_ascii=False) if was_string else data


def cached_sample_is_current(data, rest_url, headers, company, round_code, leader):
    if not admission_enabled(round_code):
        return True
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict) or data.get("criterio_elegibilidade") != ADMISSION_VERSION:
        return False
    rows = fetch_admission_rows(rest_url, headers, company, round_code, leader)
    return data.get("amostra_fingerprint") == sample_fingerprint(rows)


def register_admission_metadata(app):
    @app.after_request
    def admission_response(response):
        if response.is_json and getattr(g, "leadertrack_admission_sample", None):
            data = response.get_json(silent=True)
            if isinstance(data, dict):
                response.set_data(json.dumps(attach_admission_sample(data), ensure_ascii=False))
                response.headers["Cache-Control"] = "no-store"
                if response.status_code >= 400 and g.leadertrack_admission_sample["insuficiente"]:
                    response.status_code = 422
        return response

