
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


from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload
import os
import json

# 📁 Autentica com a conta de serviço
SERVICE_ACCOUNT_FILE = 'armazenamentopastasrh-2284e919a76c.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

# 📂 ID da pasta raiz "Avaliacoes RH" no seu Google Drive
FOLDER_RAIZ_ID = '1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS'

# 🔍 Função auxiliar: busca arquivos JSON da pasta do líder
def buscar_jsons_google_drive(empresa, codrodada, email_lider):
    drive_service = build('drive', 'v3', credentials=creds)

    caminho_pasta = f"Avaliacoes RH / {empresa} / {codrodada} / {email_lider}".strip()
    print(f"🔍 Procurando pasta: {caminho_pasta}")

    # 1. Navega pelas subpastas a partir da raiz
    pasta_atual = FOLDER_RAIZ_ID
    for nome_subpasta in [empresa, codrodada, email_lider]:
        query = f"'{pasta_atual}' in parents and name = '{nome_subpasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        resultados = drive_service.files().list(q=query, fields="files(id, name)").execute()
        arquivos = resultados.get('files', [])
        if not arquivos:
            raise FileNotFoundError(f"❌ Pasta '{nome_subpasta}' não encontrada no caminho.")
        pasta_atual = arquivos[0]['id']  # Vai para a subpasta

    # 2. Busca arquivos JSON dentro da pasta final
    query_json = f"'{pasta_atual}' in parents and mimeType = 'application/json' and trashed = false"
    arquivos_json = drive_service.files().list(q=query_json, fields="files(id, name)").execute().get('files', [])

    print(f"📄 {len(arquivos_json)} JSONs encontrados.")
    dados_jsons = []
    for arquivo in arquivos_json:
        request = drive_service.files().get_media(fileId=arquivo['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        conteudo = json.loads(fh.getvalue().decode("utf-8"))
        dados_jsons.append((arquivo['name'], conteudo))

    return dados_jsons

@app.route("/gerar-relatorio-json", methods=["POST"])
def gerar_relatorio_json():
    try:
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        jsons = buscar_jsons_google_drive(empresa, codrodada, email_lider)

        auto = None
        equipe = []

        for nome_arquivo, conteudo in jsons:
            tipo = conteudo.get("tipo", "").lower()
            if tipo.startswith("auto"):
                auto = conteudo
            else:
                equipe.append(conteudo)

        if not auto and not equipe:
            return jsonify({"erro": "Nenhum dado de avaliação encontrado."}), 404

        resultado = {
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "mensagem": "Relatório consolidado gerado com sucesso.",
            "caminho": f"Avaliacoes RH / {empresa} / {codrodada} / {email_lider}"
        }

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"erro": str(e)}), 500





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

@app.route("/listar-pasta", methods=["GET"])
def listar_pasta():
    try:
        # ID fixo da pasta "Avaliacoes RH"
        pasta_id = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

        # Busca os arquivos/diretórios dentro da pasta
        resultados = drive_service.files().list(
            q=f"'{pasta_id}' in parents and trashed = false",
            fields="files(name, id, mimeType)"
        ).execute()

        arquivos = resultados.get("files", [])

        return jsonify({
            "status": "ok",
            "itens_encontrados": len(arquivos),
            "conteudo": arquivos
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

