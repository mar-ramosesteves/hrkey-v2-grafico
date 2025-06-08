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

import json

from math import pi


# Carrega o dicionário de arquétipos dominantes por questão
with open("arquetipos_dominantes_por_questao.json", encoding="utf-8") as f:
    arquetipos_dominantes = json.load(f)


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

        # 🧹 Remove relatórios consolidados antigos antes de ler os arquivos
        antigos = service.files().list(
            q=f"'{lider_id}' in parents and name contains 'relatorio_consolidado_' and trashed = false and mimeType = 'application/json'",
            fields="files(id)").execute().get("files", [])

        for arq in antigos:
            service.files().delete(fileId=arq["id"]).execute()

        # 🔍 Lê os arquivos de auto e equipe
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

        relatorio_final = {
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": email_lider,
            "autoavaliacao": auto,
            "avaliacoesEquipe": equipe,
            "mensagem": "Relatório consolidado gerado com sucesso.",
            "caminho": f"Avaliacoes RH / {empresa} / {codrodada} / {email_lider}"
        }

        # 💾 Salva o novo JSON consolidado
        nome_arquivo = f"relatorio_consolidado_{email_lider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        conteudo = json.dumps(relatorio_final, ensure_ascii=False, indent=2).encode("utf-8")
        file_metadata = {"name": nome_arquivo, "parents": [lider_id]}
        media = MediaIoBaseUpload(io.BytesIO(conteudo), mimetype="application/json")
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify(relatorio_final)

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

        arquivos_json = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'relatorio_consolidado_' and trashed = false and mimeType='application/json'",
            fields="files(id, name, createdTime)").execute().get("files", [])

        arquivos_filtrados = [
            f for f in arquivos_json
            if emailLider.lower() in f["name"].lower() and codrodada.lower() in f["name"].lower()
        ]

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



@app.route("/ver-arquetipos")
def ver_arquetipos():
    return jsonify(arquetipos_dominantes)

@app.route("/gerar-relatorio-analitico", methods=["POST"])
def gerar_relatorio_analitico():
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

        arquivos_json = service.files().list(
            q=f"'{id_lider}' in parents and name contains 'relatorio_consolidado_' and trashed = false and mimeType='application/json'",
            fields="files(id, name, createdTime)").execute().get("files", [])

        arquivos_filtrados = [
            f for f in arquivos_json
            if emailLider.lower() in f["name"].lower() and codrodada.lower() in f["name"].lower()
        ]

        if not arquivos_filtrados:
            return jsonify({"erro": "Relatório consolidado não encontrado."}), 404

        arquivo_alvo = sorted(arquivos_filtrados, key=lambda x: x["createdTime"], reverse=True)[0]
        file_id = arquivo_alvo["id"]

        fh = io.BytesIO()
        request_drive = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        relatorio = json.loads(fh.getvalue().decode("utf-8"))
        auto = relatorio.get("autoavaliacao", {})
        equipes = relatorio.get("avaliacoesEquipe", [])

        respostas_auto = auto.get("respostas", {})
        respostas_equipes = [r.get("respostas", {}) for r in equipes if r.get("respostas")]

        with open("arquetipos_dominantes_por_questao.json", encoding="utf-8") as f:
            mapa_dom = json.load(f)

        matriz_df = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")

        def extrair_valor(matriz_df, cod, nota):
            try:
                nota = int(round(float(nota)))
                if nota < 1 or nota > 6:
                    return None
            except:
                return None

            for arq in arquetipos:
                chave = f"{arq}{nota}{cod}"
                linha = matriz_df[matriz_df["CHAVE"] == chave]
                if not linha.empty:
                    percentual = round(float(linha['% Tendência'].values[0]) * 100, 1)
                    return {
                        "tendencia": linha['Tendência'].values[0],
                        "percentual": percentual,
                        "afirmacao": linha['AFIRMACAO'].values[0]
                    }
            return None

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm

        nome_pdf = f"RELATORIO_ANALITICO_ARQUETIPOS_{empresa}_{emailLider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        c = canvas.Canvas(tmp_path, pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, height - 2 * cm, "Relatório Analítico por Arquétipos")
        c.setFont("Helvetica", 10)
        c.drawString(2 * cm, height - 2.6 * cm, f"Empresa: {empresa} | Líder: {emailLider} | Rodada: {codrodada}")
        c.drawString(2 * cm, height - 3.1 * cm, datetime.now().strftime("%d/%m/%Y %H:%M"))

        y = height - 4 * cm
        espacamento = 2.2 * cm

        agrupado = {}
        for cod, dupla in mapa_dom.items():
            chave = " e ".join(sorted(dupla))
            if chave not in agrupado:
                agrupado[chave] = []
            agrupado[chave].append(cod)

        def desenhar_barra(c, x, y, percentual, label):
            largura_max = 12 * cm
            altura = 0.4 * cm
            cor = (0.2, 0.6, 0.2) if "favorável" in label.lower() else (1.0, 0.5, 0.0)
            largura = largura_max * (percentual / 100)

            c.setFillColorRGB(*cor)
            c.rect(x, y, largura, altura, fill=True, stroke=False)

            c.setFillColorRGB(0, 0, 0)
            for i in range(0, 110, 10):
                xi = x + (largura_max * i / 100)
                c.line(xi, y, xi, y + altura)
                c.setFont("Helvetica", 6)
                c.drawString(xi - 0.2 * cm, y - 0.3 * cm, f"{i}%")

        for grupo, codigos in agrupado.items():
            c.setFont("Helvetica-Bold", 12)
            c.drawString(2 * cm, y, f"🔹 Afirmações que impactam os arquétipos: {grupo}")
            y -= espacamento / 2

            for cod in codigos:
                info_auto = extrair_valor(matriz_df, cod, respostas_auto.get(cod))

                # calcular média por questão
                somatorio = 0
                qtd_avaliacoes = 0
                for r in respostas_equipes:
                    try:
                        nota = int(round(float(r.get(cod, 0))))
                        if 1 <= nota <= 6:
                            somatorio += nota
                            qtd_avaliacoes += 1
                    except:
                        continue

                info_eq = None
                if qtd_avaliacoes > 0:
                    media = round(somatorio / qtd_avaliacoes)
                    info_eq = extrair_valor(matriz_df, cod, media)

                if not info_auto and not info_eq:
                    continue

                texto = info_auto["afirmacao"] if info_auto else cod
                tendencia_auto = info_auto["tendencia"] if info_auto else "-"
                percentual_auto = info_auto["percentual"] if info_auto else 0
                tendencia_eq = info_eq["tendencia"] if info_eq else "-"
                percentual_eq = info_eq["percentual"] if info_eq else 0

                c.setFont("Helvetica", 10)
                c.drawString(2 * cm, y, f"{cod}: {texto}")
                y -= espacamento / 2
                c.drawString(2.5 * cm, y, f"Autoavaliação → Tendência: {tendencia_auto} | %: {percentual_auto}%")
                y -= 0.6 * cm
                desenhar_barra(c, 2.5 * cm, y, percentual_auto, tendencia_auto)
                y -= espacamento / 2
                c.drawString(2.5 * cm, y, f"Média Equipe → Tendência: {tendencia_eq} | %: {percentual_eq}%")
                y -= 0.6 * cm
                desenhar_barra(c, 2.5 * cm, y, percentual_eq, tendencia_eq)
                y -= espacamento / 2

                if y < 4 * cm:
                    c.showPage()
                    y = height - 4 * cm

        c.save()

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaFileUpload(tmp_path, mimetype="application/pdf", resumable=False)
        enviado = service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": "✅ Relatório analítico gerado e salvo com sucesso."})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500



