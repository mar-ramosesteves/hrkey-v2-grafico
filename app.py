from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload





# 🔐 Autentica com a conta de serviço via variável de ambiente segura
SCOPES = ['https://www.googleapis.com/auth/drive']

creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
    scopes=SCOPES
)
service = build('drive', 'v3', credentials=creds)
# 🗂 ID fixo da pasta "Avaliacoes RH" no Drive
PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://gestor.thehrkey.tech"]}}, supports_credentials=True)

@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/")
def home():
    return "🔁 API V2 pronta para uso com leitura no Google Drive."

@app.route("/gerar-relatorio-json", methods=["POST"])
def gerar_relatorio_json():
    try:
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        def buscar_id_pasta(nome_pasta, id_pasta_mae):
            query = f"'{id_pasta_mae}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            resultados = service.files().list(q=query, fields="files(id, name)").execute()
            arquivos = resultados.get('files', [])
            return arquivos[0]['id'] if arquivos else None

        raiz_id = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"
        if not raiz_id:
            return jsonify({"erro": "Pasta raiz 'Avaliacoes RH' não encontrada."}), 404

        empresa_id = buscar_id_pasta(empresa, raiz_id)
        rodada_id = buscar_id_pasta(codrodada, empresa_id)
        lider_id = buscar_id_pasta(email_lider, rodada_id)

        if not lider_id:
            return jsonify({"erro": f"Pasta do líder '{email_lider}' não encontrada."}), 404

        query = f"'{lider_id}' in parents and (mimeType = 'application/json' or mimeType = 'text/plain') and trashed = false"

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

        return jsonify({
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "mensagem": "Relatório consolidado gerado com sucesso.",
            "caminho": f"Avaliacoes RH / {empresa} / {codrodada} / {email_lider}"
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


from datetime import datetime
from googleapiclient.http import MediaIoBaseUpload

from datetime import datetime
from googleapiclient.http import MediaIoBaseUpload

@app.route("/salvar-json-consolidado", methods=["POST"])
def salvar_json_consolidado():
    try:
        from datetime import datetime
        import io
        from googleapiclient.http import MediaIoBaseUpload

        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")
        auto = dados.get("autoavaliacao")
        equipe = dados.get("avaliacoesEquipe")

        if not all([empresa, codrodada, email_lider, auto, equipe]):
            return jsonify({"erro": "Dados insuficientes para salvar o relatório."}), 400

        # 🔍 Função para buscar ID de subpasta
        def buscar_id_pasta(nome_pasta, id_pasta_mae):
            query = f"'{id_pasta_mae}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            resultados = service.files().list(q=query, fields="files(id, name)").execute()
            arquivos = resultados.get('files', [])
            return arquivos[0]['id'] if arquivos else None

        raiz_id = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"
        empresa_id = buscar_id_pasta(empresa, raiz_id)
        rodada_id = buscar_id_pasta(codrodada, empresa_id)
        lider_id = buscar_id_pasta(email_lider, rodada_id)

        if not lider_id:
            return jsonify({"erro": f"Pasta do líder '{email_lider}' não encontrada."}), 404

        # 🧩 Monta o dicionário final com os dados já recebidos
        relatorio = {
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "geradoEm": datetime.now().isoformat()
        }

        # 💾 Prepara o conteúdo e nome do arquivo
        json_bytes = io.BytesIO(json.dumps(relatorio, indent=2).encode("utf-8"))
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        nome_arquivo = f"relatorio_consolidado_{email_lider}_{timestamp}.json"

        media = MediaIoBaseUpload(json_bytes, mimetype="application/json")
        file_metadata = {
            "name": nome_arquivo,
            "parents": [lider_id],
            "mimeType": "application/json"
        }

        novo_arquivo = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        return jsonify({
            "mensagem": "✅ Relatório consolidado salvo no Drive com sucesso!",
            "nome_arquivo": nome_arquivo,
            "arquivo_id": novo_arquivo.get("id")
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/gerar-graficos-comparativos", methods=["POST", "OPTIONS"])
def gerar_graficos_comparativos():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'CORS preflight OK'})
        response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    try:
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        emailLider = dados.get("emailLider")

        if not all([empresa, codrodada, emailLider]):
            return jsonify({"erro": "Campos obrigatórios faltando"}), 400

        def encontrar_pasta(nome, id_pai):
            resultado = service.files().list(
                q=f"'{id_pai}' in parents and name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id)").execute()
            arquivos = resultado.get("files", [])
            return arquivos[0]["id"] if arquivos else None

        id_empresa = encontrar_pasta(empresa, PASTA_RAIZ)
        id_rodada = encontrar_pasta(codrodada, id_empresa)
        id_lider = encontrar_pasta(emailLider, id_rodada)

        if not id_lider:
            return jsonify({"erro": "Pasta do líder não encontrada no Drive."}), 404

        # 🔍 Procura pelo arquivo que começa com "relatorio_consolidado_{emailLider}" e termina com .json (ignorando maiúsculas)
        import re
        arquivos = service.files().list(
            q=f"'{id_lider}' in parents and mimeType = 'application/json' and trashed = false",
            fields="files(id, name, createdTime)").execute().get("files", [])

        padrao = re.compile(rf"^relatorio_consolidado_{re.escape(emailLider)}.*\\.json$", re.IGNORECASE)
        arquivos_filtrados = [f for f in arquivos if padrao.match(f["name"])]

        if not arquivos_filtrados:
            return jsonify({"erro": "Arquivo de relatório consolidado não encontrado no Drive."}), 404

        # 📁 Usa o mais recente
        arquivo_alvo = sorted(arquivos_filtrados, key=lambda x: x["createdTime"], reverse=True)[0]
        file_id = arquivo_alvo["id"]

        # 🔽 Baixa conteúdo JSON
        fh = io.BytesIO()
        request_drive = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request_drive)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        json_str = fh.getvalue().decode("utf-8")
        json_data = json.loads(json_str)

        # ✅ SEGUE LÓGICA DE GERAÇÃO DOS GRÁFICOS (já incluída antes)
        gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emailLider)

        return jsonify({"mensagem": f"PDFs salvos na pasta do líder com sucesso! ✅"})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
