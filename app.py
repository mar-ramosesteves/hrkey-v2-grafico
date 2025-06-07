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

        json_data = json.loads(fh.getvalue().decode("utf-8"))
        respostas_auto = json_data.get("autoavaliacao", {}).get("respostas", {})
        respostas_equipes = json_data.get("avaliacoesEquipe", [])

        with open("arquetipos_dominantes_por_questao.json", "r", encoding="utf-8") as f:
            mapa_dom = json.load(f)

        matriz_df = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")

        def obter_dados_por_cod(respostas_dicts):
            somas = {}
            contagens = {}
            for r in respostas_dicts:
                respostas = r.get("respostas", {})
                for cod, valor in respostas.items():
                    try:
                        val = float(valor)
                        somas[cod] = somas.get(cod, 0) + val
                        contagens[cod] = contagens.get(cod, 0) + 1
                    except:
                        pass
            medias = {cod: round(somas[cod] / contagens[cod]) for cod in somas if contagens[cod] > 0}
            return medias

        media_equipes = obter_dados_por_cod(respostas_equipes)
        auto_ajustada = {cod: round(float(respostas_auto.get(cod, 0))) for cod in perguntas if cod in respostas_auto}

        agrupado = {}
        for cod, dupla in mapa_dom.items():
            chave = " e ".join(sorted(dupla))
            if chave not in agrupado:
                agrupado[chave] = []
            agrupado[chave].append(cod)

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        from matplotlib import pyplot as plt
        import matplotlib.patches as patches

        def criar_velocimetro(valor, cor, titulo):
            fig, ax = plt.subplots(figsize=(2, 1.2), subplot_kw={'projection': 'polar'})
            ax.set_theta_offset(np.pi) 
            ax.set_theta_direction(-1)
            ax.set_yticklabels([])
            ax.set_xticklabels([])
            ax.set_ylim(0, 100)
            ax.barh(0, np.pi, height=100, color="lightgrey")
            theta = (valor / 100) * np.pi
            ax.barh(0, theta, height=100, color=cor)
            ax.text(0, -10, f"{valor:.1f}%", fontsize=10, ha='center')
            ax.set_title(titulo, fontsize=9)
            plt.tight_layout()
            tmp_img = io.BytesIO()
            plt.savefig(tmp_img, format="png", bbox_inches="tight", dpi=150)
            plt.close(fig)
            tmp_img.seek(0)
            return tmp_img

        nome_pdf = f"RELATORIO_ANALITICO_ARQUETIPOS_{empresa}_{emailLider}_{codrodada}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        c = canvas.Canvas(tmp_path, pagesize=A4)
        width, height = A4
        y = height - 2 * cm

        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, y, "Relatório Analítico por Arquétipos")
        y -= 1 * cm
        c.setFont("Helvetica", 10)
        c.drawString(2 * cm, y, f"Empresa: {empresa} | Líder: {emailLider} | Rodada: {codrodada}")
        y -= 1 * cm
        c.drawString(2 * cm, y, datetime.now().strftime("%d/%m/%Y %H:%M"))
        y -= 1.5 * cm

        for grupo, codigos in agrupado.items():
            c.setFont("Helvetica-Bold", 12)
            c.drawString(2 * cm, y, f"🔹 Afirmações que impactam os arquétipos: {grupo}")
            y -= 0.8 * cm

            for cod in codigos:
                linha = matriz_df[matriz_df["CHAVE"].str.endswith(str(cod))].iloc[0]
                afirmacao = linha["AFIRMACAO"]
                tendencia_auto = linha["Tendência"]
                pct_auto = linha["% Tendência"]

                auto_nota = auto_ajustada.get(cod, 0)
                equipe_nota = media_equipes.get(cod, 0)

                chave_auto = f"{auto_nota}{cod}"
                chave_equipe = f"{equipe_nota}{cod}"

                linha_auto = matriz_df[matriz_df["CHAVE"].str.endswith(chave_auto)]
                linha_equipe = matriz_df[matriz_df["CHAVE"].str.endswith(chave_equipe)]

                t_auto = linha_auto["Tendência"].values[0] if not linha_auto.empty else "-"
                p_auto = linha_auto["% Tendência"].values[0] if not linha_auto.empty else "-"
                t_eq = linha_equipe["Tendência"].values[0] if not linha_equipe.empty else "-"
                p_eq = linha_equipe["% Tendência"].values[0] if not linha_equipe.empty else "-"

                c.setFont("Helvetica", 10)
                c.drawString(2 * cm, y, f"{cod}: {afirmacao[:110]}")
                y -= 1 * cm

                img_auto = criar_velocimetro(float(p_auto), "royalblue", "Autoavaliação")
                img_eq = criar_velocimetro(float(p_eq), "darkorange", "Média da Equipe")

                c.drawInlineImage(img_auto, 2 * cm, y - 3.2 * cm, width=5 * cm, height=2.5 * cm)
                c.drawInlineImage(img_eq, 8 * cm, y - 3.2 * cm, width=5 * cm, height=2.5 * cm)

                y -= 3.4 * cm

                c.setFont("Helvetica", 8)
                c.drawString(2 * cm, y, f"Tendência Auto: {t_auto} | %: {p_auto}")
                c.drawString(8 * cm, y, f"Tendência Equipe: {t_eq} | %: {p_eq}")
                y -= 1 * cm

                if y < 5 * cm:
                    c.showPage()
                    y = height - 2 * cm

        c.save()

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaFileUpload(tmp_path, mimetype="application/pdf", resumable=False)
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return jsonify({"mensagem": "✅ Relatório analítico com gráficos gerado com sucesso."})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500
