
from flask import Flask, request, jsonify
import requests
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Carrega credenciais da conta de serviço
creds = service_account.Credentials.from_service_account_file(
    "armazenamentopastasrh-2284e919a76c.json",
    scopes=["https://www.googleapis.com/auth/drive"]
)

# Conecta ao Google Drive
drive_service = build("drive", "v3", credentials=creds)

app = Flask(__name__)

@app.route("/enviar-avaliacao-com-int", methods=["POST"])
def proxy_enviar_avaliacao_com_int():
    try:
        dados = request.get_json()
        if not dados:
            raise Exception("Nenhum dado recebido.")

        respostas = dados.get("respostas", {})
        respostas_int = {k: int(v) if isinstance(v, str) and v.isdigit() else v for k, v in respostas.items()}
        dados["respostas"] = respostas_int

        resposta = requests.post(
            "https://script.google.com/macros/s/AKfycbzrKBSwgRf9ckJrBDRkC1VsDibhYrWTJkLPhVMt83x_yCXnd_ex_CYuehT8pioTFvbxsw/exec",
            json=dados,
            timeout=10
        )

        texto = resposta.text.strip()

        if "já enviou" in texto:
            return jsonify({"status": "duplicado", "mensagem": texto}), 409

        return jsonify({"status": "ok", "mensagem": texto}), 200

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route("/")
def home():
    return "🔁 API V2 pronta para uso com conversão segura."


@app.route("/gerar-relatorio-json", methods=["POST"])
def gerar_relatorio_json():
    try:
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        pasta = f"Avaliacoes RH/{empresa}/{codrodada}/{email_lider}"

        # Lista os arquivos .json da pasta
        arquivos = os.listdir(pasta)
        jsons = [arq for arq in arquivos if arq.endswith(".json")]

        auto = None
        equipe = []

        for arq in jsons:
            caminho = os.path.join(pasta, arq)
            with open(caminho, "r", encoding="utf-8") as f:
                conteudo = json.load(f)
                if conteudo.get("tipo", "").lower().startswith("auto"):
                    auto = conteudo
                else:
                    equipe.append(conteudo)

        if not auto and not equipe:
            return jsonify({"erro": "Nenhum dado de avaliação encontrado."}), 404

        # Resultado básico de retorno
        resultado = {
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "mensagem": "Relatório consolidado gerado com sucesso.",
            "caminho": pasta
        }

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

from flask_cors import CORS

CORS(app, resources={r"/*": {"origins": ["https://gestor.thehrkey.tech"]}}, supports_credentials=True)

@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


