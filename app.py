
from flask import Flask, request, jsonify
import requests
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Carrega credenciais da conta de serviço
creds = service_account.Credentials.from_service_account_file(
    "armazenamentopastasrh-1290b90ee29c.json",
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
        import os
        import json
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        import io

        # 🔐 Caminho da credencial da conta de serviço
        SERVICE_ACCOUNT_FILE = 'armazenamentopastasrh-2284e919a76c.json'
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

        # ✅ Autentica
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)

        # 📥 Dados recebidos
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        # 📁 Caminho da pasta no Drive (fixo = Avaliacoes RH)
        caminho_pasta = f"Avaliacoes RH/{empresa}/{codrodada}/{email_lider}"

        # 🔍 Função auxiliar para localizar a pasta
        def buscar_id_pasta(nome_pasta, id_pasta_mae):
            query = f"'{id_pasta_mae}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            resultados = service.files().list(q=query, fields="files(id, name)").execute()
            arquivos = resultados.get('files', [])
            return arquivos[0]['id'] if arquivos else None

        # 🚩 Inicia pela raiz 'Avaliacoes RH'
        raiz_id = buscar_id_pasta("Avaliacoes RH", "root")
        if not raiz_id:
            return jsonify({"erro": "Pasta raiz 'Avaliacoes RH' não encontrada."}), 404

        empresa_id = buscar_id_pasta(empresa, raiz_id)
        rodada_id = buscar_id_pasta(codrodada, empresa_id)
        lider_id = buscar_id_pasta(email_lider, rodada_id)

        if not lider_id:
            return jsonify({"erro": f"Pasta do líder '{email_lider}' não encontrada."}), 404

        # 📄 Lista arquivos JSON da pasta do líder
        query = f"'{lider_id}' in parents and mimeType = 'application/json' and trashed = false"
        arquivos = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])

        if not arquivos:
            return jsonify({"erro": "Nenhum JSON encontrado na pasta do líder."}), 404

        auto = None
        equipe = []

        for arquivo in arquivos:
            nome = arquivo['name']
            file_id = arquivo['id']
            request_drive = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_drive)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)
            conteudo = json.load(fh)
            tipo = conteudo.get("tipo", "").lower()

            if tipo.startswith("auto"):
                auto = conteudo
            else:
                equipe.append(conteudo)

        if not auto and not equipe:
            return jsonify({"erro": "Nenhum dado de avaliação encontrado."}), 404

        return jsonify({
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "mensagem": "Relatório consolidado gerado com sucesso.",
            "caminho": caminho_pasta
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500





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

