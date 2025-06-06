from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload, MediaFileUpload
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import tempfile
import numpy as np
import re
import time

# ✅ Lista dos códigos das 49 perguntas
perguntas = [f"Q{str(i).zfill(2)}" for i in range(1, 50)]

# ✅ Carrega a matriz de cálculo com os arquétipos reais da planilha
matriz = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
arquetipos = sorted(matriz["ARQUETIPO"].unique())

# 🔐 Autenticação Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
    scopes=SCOPES
)
service = build('drive', 'v3', credentials=creds)
PASTA_RAIZ = "1l4kOZwed-Yc5nHU4RBTmWQz3zYAlpniS"

# 🚀 App Flask
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

def garantir_pasta(nome, id_pai):
    resultado = service.files().list(
        q=f"'{id_pai}' in parents and name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id)").execute()
    arquivos = resultado.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    else:
        pasta_metadata = {
            "name": nome,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [id_pai]
        }
        nova_pasta = service.files().create(body=pasta_metadata, fields="id").execute()
        return nova_pasta["id"]

@app.route("/salvar-json-consolidado", methods=["POST"])
def salvar_json_consolidado():
    try:
        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        emailLider = dados.get("emailLider")

        if not all([empresa, codrodada, emailLider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        id_empresa = garantir_pasta(empresa, PASTA_RAIZ)
        id_rodada = garantir_pasta(codrodada, id_empresa)
        id_lider = garantir_pasta(emailLider, id_rodada)

        nome_arquivo = f"relatorio_consolidado_{emailLider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        conteudo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
        file_metadata = {"name": nome_arquivo, "parents": [id_lider]}
        media = MediaIoBaseUpload(io.BytesIO(conteudo), mimetype="application/json")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": f"JSON salvo como '{nome_arquivo}' com sucesso!"})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/gerar-relatorio-json", methods=["POST", "OPTIONS"])
def gerar_relatorio_json():
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
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        def buscar_id_pasta(nome_pasta, id_pasta_mae):
            query = f"'{id_pasta_mae}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            resultados = service.files().list(q=query, fields="files(id, name)").execute()
            arquivos = resultados.get('files', [])
            return arquivos[0]['id'] if arquivos else None

        empresa_id = buscar_id_pasta(empresa, PASTA_RAIZ)
        rodada_id = buscar_id_pasta(codrodada, empresa_id)
        lider_id = buscar_id_pasta(email_lider, rodada_id)

        if not lider_id:
            return jsonify({"erro": f"Pasta do líder '{email_lider}' não encontrada."}), 404

        query = f"'{lider_id}' in parents and (mimeType = 'application/json' or mimeType = 'text/plain') and trashed = false"
        arquivos = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])

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

        id_empresa = garantir_pasta(empresa, PASTA_RAIZ)
        id_rodada = garantir_pasta(codrodada, id_empresa)
        id_lider = garantir_pasta(emailLider, id_rodada)

        prefixo = f"relatorio_consolidado_{emailLider}"
        arquivos_json = service.files().list(
            q=f"'{id_lider}' in parents and name contains '{prefixo}' and trashed = false and mimeType='application/json'",
            fields="files(id, name, createdTime)").execute().get("files", [])

        padrao = re.compile(rf"^relatorio_consolidado_{re.escape(emailLider)}.*\.json$", re.IGNORECASE)
        arquivos_filtrados = [f for f in arquivos_json if padrao.match(f["name"])]

        if not arquivos_filtrados:
            return jsonify({"erro": "Arquivo de relatório consolidado não encontrado no Drive."}), 404

        arquivo_alvo = sorted(arquivos_filtrados, key=lambda x: x["createdTime"], reverse=True)[0]
        file_id = arquivo_alvo["id"]

        fh = io.BytesIO()
        request_drive = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        json_data = json.loads(fh.getvalue().decode("utf-8"))

        gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emailLider)

        return jsonify({"mensagem": "✅ PDF gerado com sucesso e salvo no Drive."})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

def calcular_percentuais(respostas_dict):
    total_por_arquetipo = {a: 0 for a in arquetipos}
    max_por_arquetipo = {a: 0 for a in arquetipos}
    for cod in perguntas:
        try:
            raw = respostas_dict.get(cod, 0)
            nota = int(round(float(raw)))
            if nota < 1 or nota > 6:
                continue
        except:
            continue

        for arq in arquetipos:
            chave = f"{arq}{nota}{cod}"
            linha = matriz[matriz["CHAVE"] == chave]
            if not linha.empty:
                pontos = linha["PONTOS_OBTIDOS"].values[0]
                maximo = linha["PONTOS_MAXIMOS"].values[0]
                total_por_arquetipo[arq] += pontos
                max_por_arquetipo[arq] += maximo
    return {
        a: round((total_por_arquetipo[a] / max_por_arquetipo[a]) * 100, 1) if max_por_arquetipo[a] > 0 else 0
        for a in arquetipos
    }

def calcular_percentuais_equipes(lista_respostas):
    totais_por_arquetipo = {a: 0 for a in arquetipos}
    total_avaliacoes = 0

    for resposta in lista_respostas:
        respostas_dict = resposta.get("respostas", {})
        if not respostas_dict:
            continue

        percentuais = calcular_percentuais(respostas_dict)
        for arq in arquetipos:
            totais_por_arquetipo[arq] += percentuais.get(arq, 0)
        total_avaliacoes += 1

    if total_avaliacoes == 0:
        return {a: 0 for a in arquetipos}

    return {
        a: round(totais_por_arquetipo[a] / total_avaliacoes, 1)
        for a in arquetipos
    }

def gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emailLider):
    respostas_auto = json_data.get("autoavaliacao", {}).get("respostas", {})
    respostas_equipes = json_data.get("avaliacoesEquipe", [])

    pct_auto = calcular_percentuais(respostas_auto)
    pct_equipes = calcular_percentuais_equipes(respostas_equipes)

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(arquetipos))
    auto_vals = [pct_auto.get(a, 0) for a in arquetipos]
    equipe_vals = [pct_equipes.get(a, 0) for a in arquetipos]

    ax.bar(x - 0.2, auto_vals, width=0.4, label="Autoavaliação", color='royalblue')
    ax.bar(x + 0.2, equipe_vals, width=0.4, label="Média da Equipe", color='darkorange')

    for i, (a, e) in enumerate(zip(auto_vals, equipe_vals)):
        ax.text(i - 0.2, a + 1, f"{a:.1f}%", ha='center', fontsize=9)
        ax.text(i + 0.2, e + 1, f"{e:.1f}%", ha='center', fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(arquetipos)
    ax.set_ylim(0, 100)
    ax.set_yticks(np.arange(0, 110, 10))
    ax.axhline(60, color='gray', linestyle='--', label="Dominante (60%)")
    ax.axhline(50, color='gray', linestyle=':', label="Suporte (50%)")
    ax.set_ylabel("Pontuação (%)")
    ax.set_title(f"ARQUÉTIPOS DE GESTÃO\n{emailLider} | {codrodada} | {empresa}\nEquipe: {len(respostas_equipes)} respondentes", fontsize=12)
    ax.legend()
    plt.tight_layout()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        with PdfPages(tmp.name) as pdf:
            pdf.savefig(fig)

        id_empresa = garantir_pasta(empresa, PASTA_RAIZ)
        id_rodada = garantir_pasta(codrodada, id_empresa)
        id_lider = garantir_pasta(emailLider, id_rodada)

        nome_pdf = f"ARQUETIPOS_AUTO_VS_EQUIPE_{emailLider}_{codrodada}.pdf"

        anteriores = service.files().list(
            q=f"'{id_lider}' in parents and name = '{nome_pdf}' and trashed = false",
            fields="files(id)").execute()
        for arq in anteriores.get("files", []):
            service.files().delete(fileId=arq["id"]).execute()

        time.sleep(1)

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaFileUpload(tmp.name, mimetype="application/pdf", resumable=False)

        try:
            enviado = service.files().create(body=file_metadata, media_body=media, fields="id, name, parents").execute()
            print(f"✅ PDF gerado e enviado com sucesso: {enviado['name']} | ID: {enviado['id']} | Pasta: {id_lider}")
        except Exception as e:
            print(f"❌ ERRO ao tentar salvar o PDF no Drive: {str(e)}")
