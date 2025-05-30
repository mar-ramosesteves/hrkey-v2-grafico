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
        import re, io, json, tempfile, numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

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

        # 🔍 Lista todos os arquivos da pasta e localiza o JSON consolidado mais recente
        arquivos = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'relatorio_consolidado_' and trashed = false",
            fields="files(id, name, createdTime)").execute().get("files", [])

        arquivos_filtrados = [f for f in arquivos if re.search(rf"relatorio_consolidado_{re.escape(emailLider)}_.*\\.json", f["name"], re.IGNORECASE)]
        if not arquivos_filtrados:
            return jsonify({"erro": "Arquivo de relatório consolidado não encontrado no Drive."}), 404

        # Ordena por data de criação e pega o mais recente
        arquivo_alvo = sorted(arquivos_filtrados, key=lambda x: x["createdTime"], reverse=True)[0]

        file_id = arquivo_alvo["id"]
        fh = io.BytesIO()
        request_drive = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        json_str = fh.getvalue().decode("utf-8")
        json_data = json.loads(json_str)

        matriz = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
        perguntas = [f"Q{str(i).zfill(2)}" for i in range(1, 50)]
        arquetipos = matriz["ARQUETIPO"].unique()

        def calcular_total_por_arquetipo(respostas):
            totais = {a: 0 for a in arquetipos}
            maximos = {a: 0 for a in arquetipos}
            for cod, estrelas in respostas.items():
                if not cod.startswith("Q"):
                    continue
                estrelas = int(estrelas)
                for arq in arquetipos:
                    chave = f"{arq}{estrelas}{cod}"
                    linha = matriz[matriz["CHAVE"] == chave]
                    if not linha.empty:
                        totais[arq] += linha["PONTOS_OBTIDOS"].values[0]
                        maximos[arq] += linha["PONTOS_MAXIMOS"].values[0]
            return {a: round((totais[a] / maximos[a]) * 100, 1) if maximos[a] > 0 else 0 for a in arquetipos}

        pct_auto = calcular_total_por_arquetipo(json_data["autoavaliacao"])

        respostas_equipes = json_data["avaliacoesEquipe"]
        qtd_respondentes = len(respostas_equipes)
        media_equipes = {}
        for cod in perguntas:
            soma = sum([r.get(cod, 0) for r in respostas_equipes])
            media_equipes[cod] = round(soma / qtd_respondentes, 1) if qtd_respondentes else 0

        pct_equipe = calcular_total_por_arquetipo(media_equipes)

        def gerar_grafico_completo_com_titulo(pct_auto, pct_equipe):
            fig, ax = plt.subplots(figsize=(10, 5))
            arqs = list(pct_auto.keys())
            x = np.arange(len(arqs))
            ax.bar(x - 0.2, [pct_auto[a] for a in arqs], width=0.4, label="Auto", color='royalblue')
            ax.bar(x + 0.2, [pct_equipe[a] for a in arqs], width=0.4, label="Equipe", color='darkorange')
            ax.axhline(60, color='gray', linestyle='--', label="Dominante (60%)")
            ax.axhline(50, color='gray', linestyle=':', label="Suporte (50%)")
            ax.set_xticks(x)
            ax.set_xticklabels(arqs)
            ax.set_ylim(0, 100)
            ax.set_ylabel("%")
            for i, a in enumerate(arqs):
                ax.text(i - 0.25, pct_auto[a] + 1, f"{pct_auto[a]}%", fontsize=9)
                ax.text(i + 0.05, pct_equipe[a] + 1, f"{pct_equipe[a]}%", fontsize=9)
            titulo = "ARQUÉTIPOS DE GESTÃO"
            subtitulo = f"Líder: {emailLider} — {empresa} / {codrodada} — Média Equipe: {qtd_respondentes} respondentes"
            plt.title(f"{titulo}\n{subtitulo}")
            plt.legend()
            return fig

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            with PdfPages(tmp.name) as pdf:
                pdf.savefig(gerar_grafico_completo_com_titulo(pct_auto, pct_equipe))

        nome_pdf = "ARQUETIPOS_AUTO_VS_EQUIPE.pdf"
        anteriores = service.files().list(
            q=f"'{id_lider}' in parents and name = '{nome_pdf}' and trashed = false",
            fields="files(id)").execute()
        for arq in anteriores.get("files", []):
            service.files().delete(fileId=arq["id"]).execute()

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaFileUpload(tmp.name, mimetype="application/pdf")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"PDF salvo com sucesso com {qtd_respondentes} respondentes."})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
