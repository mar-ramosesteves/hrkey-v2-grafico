from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload, MediaFileUpload
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import tempfile
import numpy as np
import re
import time
import base64
from math import pi
from reportlab.lib.units import cm
import pandas as pd
import os
import traceback

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://gestor.thehrkey.tech"]}}, supports_credentials=True)

@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://gestor.thehrkey.tech"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


# === Funções de cálculo ===

def calcular_percentuais(respostas_dict):
    print("📥 [DEBUG] Entrou em calcular_percentuais")
    print(f"📥 [DEBUG] Respostas recebidas: {len(respostas_dict)} itens. Exemplo Q01: {respostas_dict.get('Q01', 'N/A')}")

    total_por_arquetipo = {a: 0 for a in arquetipos}
    max_por_arquetipo = {a: 0 for a in arquetipos}

    for cod_pergunta in perguntas:
        raw_nota = respostas_dict.get(cod_pergunta, "")
        
        try:
            nota = int(round(float(raw_nota)))
            if nota < 1 or nota > 6:
                print(f"⚠️ Nota fora do intervalo ignorada para {cod_pergunta}: '{raw_nota}' -> {nota}")
                continue

            for arq_nome in arquetipos:
                chave = f"{arq_nome}{nota}{cod_pergunta}"
                linha_matriz = matriz[matriz["CHAVE"] == chave]

                if not linha_matriz.empty:
                    pontos_obtidos = linha_matriz["PONTOS_OBTIDOS"].values[0]
                    pontos_maximos = linha_matriz["PONTOS_MAXIMOS"].values[0]
                    total_por_arquetipo[arq_nome] += pontos_obtidos
                    max_por_arquetipo[arq_nome] += pontos_maximos
                else:
                    print(f"⚠️ Chave '{chave}' não encontrada na matriz para {cod_pergunta} com nota {nota} e arquétipo {arq_nome}.")

        except ValueError:
            print(f"⚠️ Erro de conversão para número em {cod_pergunta}: '{raw_nota}' não é um número válido.")
            continue
        except Exception as e:
            print(f"⚠️ Erro inesperado ao processar {cod_pergunta} com nota '{raw_nota}': {e}")
            continue

    percentuais = {}
    for arq_nome in arquetipos:
        if max_por_arquetipo[arq_nome] > 0:
            percentuais[arq_nome] = round((total_por_arquetipo[arq_nome] / max_por_arquetipo[arq_nome]) * 100, 1)
        else:
            percentuais[arq_nome] = 0

    print(f"📊 [DEBUG] Percentuais calculados: {percentuais}")
    return percentuais


def calcular_percentuais_equipes(lista_de_respostas):
    print("📥 [DEBUG] Entrou em calcular_percentuais_equipes")
    print(f"📥 [DEBUG] Total de avaliações de equipe recebidas: {len(lista_de_respostas)}")

    soma_percentuais_por_arquetipo = {a: 0 for a in arquetipos}
    total_avaliacoes_validas = 0

    for respostas_dict_membro in lista_de_respostas:
        if not respostas_dict_membro:
            print("⚠️ Dicionário de respostas de um membro da equipe está vazio, ignorando.")
            continue
        
        percentuais_individuais = calcular_percentuais(respostas_dict_membro)
        
        if percentuais_individuais:
            for arq_nome in arquetipos:
                soma_percentuais_por_arquetipo[arq_nome] += percentuais_individuais.get(arq_nome, 0)
            total_avaliacoes_validas += 1
        else:
            print("⚠️ Cálculo individual de percentuais retornou vazio para um membro da equipe.")

    percentuais_medios = {}
    if total_avaliacoes_validas == 0:
        print("⚠️ Nenhuma avaliação de equipe válida para calcular a média. Retornando zeros.")
        return {a: 0 for a in arquetipos}

    for arq_nome in arquetipos:
        percentuais_medios[arq_nome] = round(soma_percentuais_por_arquetipo[arq_nome] / total_avaliacoes_validas, 1)

    print(f"📊 [DEBUG] Percentuais médios da equipe calculados: {percentuais_medios}")
    return percentuais_medios


# Configuração global do Supabase
SUPABASE_REST_URL = os.environ.get("SUPABASE_REST_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_REST_URL or not SUPABASE_KEY:
    print("ERRO: Variáveis de ambiente SUPABASE_REST_URL ou SUPABASE_KEY não configuradas.")
else:
    print("✅ Credenciais Supabase carregadas com sucesso.")

# Carrega a matriz de pontuação de arquétipos
matriz = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
print("📄 Matriz com chave carregada. Total de linhas:", len(matriz))

# Lista de arquétipos
arquetipos = ["Formador", "Resoluto", "Cuidativo", "Consultivo", "Imperativo", "Prescritivo"]

# Lista de perguntas válidas
perguntas = [f"Q{str(i).zfill(2)}" for i in range(1, 50)]

def extrair_valor(matriz_df, cod, nota, arquetipos_list):
    """
    Extrai tendência e percentual da matriz para UMA nota individual.
    """
    try:
        nota = int(round(float(nota)))
        if nota < 1 or nota > 6:
            return None
    except (ValueError, TypeError):
        return None

    for arq_item in arquetipos_list:
        chave = f"{arq_item}{nota}{cod}"
        linha = matriz_df[matriz_df["CHAVE"] == chave]
        if not linha.empty:
            percentual = round(float(linha['% Tendência'].values[0]) * 100, 1)
            return {
                "tendencia": linha['Tendência'].values[0],
                "percentual": percentual,
                "afirmacao": linha['AFIRMACAO'].values[0]
            }
    return None


def salvar_relatorio_analitico_no_supabase(dados_relatorio_json, empresa, codrodada, emaillider_val, tipo_relatorio_str):
    """
    Salva os dados gerados no Supabase na tabela relatorios_gerados.
    """
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        print("❌ Não foi possível salvar no Supabase: Variáveis de ambiente não configuradas.")
        return False

    url = f"{SUPABASE_REST_URL}/relatorios_gerados"
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emaillider_val,
        "tipo_relatorio": tipo_relatorio_str,
        "dados_json": dados_relatorio_json,
        "data_criacao": datetime.now().isoformat()
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        print(f"✅ JSON do '{tipo_relatorio_str}' salvo no Supabase com sucesso.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao salvar JSON do '{tipo_relatorio_str}' no Supabase: {e}")
        return False


def salvar_json_ia_no_drive(dados, nome_base, service, id_lider):
    from io import BytesIO
    from googleapiclient.http import MediaIoBaseUpload

    nome_json = f"IA_{nome_base}.json"

    def buscar_ou_criar_pasta(nome, pai, service):
        query = f"'{pai}' in parents and name='{nome}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        resultado = service.files().list(q=query, fields="files(id)").execute().get("files", [])
        if resultado:
            return resultado[0]["id"]
        else:
            metadata = {"name": nome, "parents": [pai], "mimeType": "application/vnd.google-apps.folder"}
            pasta = service.files().create(body=metadata, fields="id").execute()
            return pasta["id"]

    id_subpasta = buscar_ou_criar_pasta("ia_json", id_lider, service)
    conteudo_bytes = BytesIO(json.dumps(dados, indent=2, ensure_ascii=False).encode("utf-8"))
    media = MediaIoBaseUpload(conteudo_bytes, mimetype="application/json")
    metadata = {"name": nome_json, "parents": [id_subpasta]}
    service.files().create(body=metadata, media_body=media, fields="id").execute()
    print(f"✅ JSON IA salvo no Drive: {nome_json}")


# Carrega o dicionário de arquétipos dominantes por questão
with open("arquetipos_dominantes_por_questao.json", encoding="utf-8") as f:
    arquetipos_dominantes = json.load(f)

# Lista dos códigos das 49 perguntas
perguntas = [f"Q{str(i).zfill(2)}" for i in range(1, 50)]

# Carrega a matriz de cálculo com os arquétipos reais da planilha
matriz = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
arquetipos = sorted(matriz["ARQUETIPO"].unique())

# Autenticação Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
    scopes=SCOPES
)
service = build('drive', 'v3', credentials=creds)
PASTA_RAIZ = "1ekQKwPchEN_fO4AK0eyDd_JID5YO3hAF"


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
        print("🔎 empresa recebida:", empresa)
        codrodada = dados.get("codrodada")
        email_lider = dados.get("emailLider")

        if not all([empresa, codrodada, email_lider]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        def buscar_id_pasta(nome_pasta, id_pasta_mae):
            query = f"'{id_pasta_mae}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            resultados = service.files().list(q=query, fields="files(id, name)").execute()
            arquivos = resultados.get('files', [])
            return arquivos[0]['id'] if arquivos else None

        try:
            empresa_id = buscar_id_pasta(empresa, PASTA_RAIZ)
            print("🧩 empresa_id:", empresa_id)
            rodada_id = buscar_id_pasta(codrodada, empresa_id)
            print("🧩 rodada_id:", rodada_id)
            lider_id = buscar_id_pasta(email_lider, rodada_id)
            print("🧩 lider_id:", lider_id)
        except Exception as e:
            print("❌ ERRO AO BUSCAR IDs:", str(e))
            raise

        if not lider_id:
            return jsonify({"erro": f"Pasta do líder '{email_lider}' não encontrada."}), 404

        antigos = service.files().list(
            q=f"'{lider_id}' in parents and name contains 'relatorio_consolidado_' and trashed = false and mimeType = 'application/json'",
            fields="files(id)").execute().get("files", [])

        for arq in antigos:
            service.files().delete(fileId=arq["id"]).execute()

        query = f"'{lider_id}' in parents and (mimeType = 'application/json' or mimeType = 'text/plain') and trashed = false"
        arquivos = service.files().list(q=query, fields="files(id, name)").execute().get('files', [])

        auto = None
        equipe = []

        for arquivo in arquivos:
            nome = arquivo['name']
            file_id = arquivo['id']

            if nome.lower().startswith("relatorio_microambiente_"):
                continue

            request_drive = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_drive)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)
            conteudo = json.load(fh)
            tipo = conteudo.get("tipo", "").lower()

            if "microambiente" in tipo or "microambiente" in nome.lower():
                continue

            if "auto" in tipo:
                auto = conteudo
            elif "equipe" in tipo:
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
        import requests
        from datetime import datetime

        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        emaillider_req = dados.get("emailLider")
        print("📥 Dados recebidos:", empresa, codrodada, emaillider_req)

        tipo_relatorio_grafico_atual = "arquetipos_grafico_comparativo"

        if not SUPABASE_REST_URL or not SUPABASE_KEY:
            return jsonify({"erro": "Configuração do Supabase ausente no servidor."}), 500

        url_busca_cache = f"{SUPABASE_REST_URL}/relatorios_gerados"
        params_cache = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}",
            "tipo_relatorio": f"eq.{tipo_relatorio_grafico_atual}",
            "order": "data_criacao.desc",
            "limit": 1
        }

        cache_response = requests.get(url_busca_cache, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }, params=params_cache, timeout=15)
        cache_response.raise_for_status()
        cached_data_list = cache_response.json()

        if cached_data_list:
            cached_report = cached_data_list[0]
            data_criacao_cache_str = cached_report.get("data_criacao")
            if data_criacao_cache_str:
                data_criacao_cache = datetime.fromisoformat(data_criacao_cache_str.replace('Z', '+00:00'))
                cache_validity_period = timedelta(hours=1)
                if datetime.now(data_criacao_cache.tzinfo) - data_criacao_cache < cache_validity_period:
                    print(f"✅ Cache válido encontrado. Retornando dados cacheados.")
                    return jsonify(cached_report.get("dados_json", {})), 200

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        filtro = f"?empresa=eq.{empresa}&codrodada=eq.{codrodada}&emaillider=eq.{emaillider_req}&select=dados_json"
        url = f"{SUPABASE_REST_URL}/consolidado_arquetipos{filtro}"
        print("🔎 Buscando consolidado no Supabase:", url)

        resp = requests.get(url, headers=headers)
        registros = resp.json()

        if not registros or "dados_json" not in registros[0]:
            print("❌ Consolidado não encontrado ou formato inválido.")
            return jsonify({"erro": "Consolidado não encontrado no Supabase."}), 404

        json_data = registros[0]["dados_json"]
        print("📄 Consolidado encontrado. Chaves:", list(json_data.keys()))

        percentuais_auto_result, percentuais_equipe_result, num_avaliacoes_result, dados_gerais_grafico = \
            gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emaillider_req)

        json_para_frontend = {
            "titulo": dados_gerais_grafico["titulo"],
            "subtitulo": dados_gerais_grafico["subtitulo"],
            "info_avaliacoes": dados_gerais_grafico["info_avaliacoes"],
            "arquetipos": arquetipos,
            "autoavaliacao": percentuais_auto_result,
            "mediaEquipe": percentuais_equipe_result,
            "n_avaliacoes": num_avaliacoes_result
        }

        salvar_relatorio_analitico_no_supabase(json_para_frontend, empresa, codrodada, emaillider_req, tipo_relatorio_grafico_atual)
        return jsonify(json_para_frontend), 200

    except Exception as e:
        print("💥 Erro geral na geração do gráfico:", str(e))
        return jsonify({"erro": str(e)}), 500


def gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emaillider_req):
    respostas_auto = json_data.get("autoavaliacao", {}).get("respostas", {})
    respostas_equipes = [
        avaliacao.get("respostas", {}) for avaliacao in json_data.get("avaliacoesEquipe", [])
    ]

    print("📄 Chaves em respostas_auto:", respostas_auto.keys())
    print("📄 Q01 =", respostas_auto.get("Q01", "vazio"))
    if respostas_equipes:
        print("📄 Q01 (equipe) da 1ª pessoa =", respostas_equipes[0].get("Q01", "vazio"))

    pct_auto = calcular_percentuais(respostas_auto)
    pct_equipes = calcular_percentuais_equipes(respostas_equipes)

    dados_gerais_grafico = {
        "titulo": "ARQUÉTIPOS DE GESTÃO",
        "subtitulo": f"{emaillider_req} | {codrodada} | {empresa}",
        "info_avaliacoes": f"Equipe: {len(respostas_equipes)} respondentes"
    }
    return pct_auto, pct_equipes, len(respostas_equipes), dados_gerais_grafico


@app.route("/ver-arquetipos")
def ver_arquetipos():
    return jsonify(arquetipos_dominantes)


@app.route("/gerar-relatorio-analitico", methods=["POST"])
def gerar_relatorio_analitico():
    try:
        dados_requisicao = request.get_json()
        empresa = dados_requisicao.get("empresa")
        codrodada = dados_requisicao.get("codrodada")
        emaillider_req = dados_requisicao.get("emailLider")

        if not all([empresa, codrodada, emaillider_req]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        if not SUPABASE_REST_URL or not SUPABASE_KEY:
            return jsonify({"erro": "Configuração do Supabase ausente no servidor."}), 500

        url_busca_cache = f"{SUPABASE_REST_URL}/relatorios_gerados"
        tipo_relatorio_atual = "arquetipos_analitico"

        params_cache = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}",
            "tipo_relatorio": f"eq.{tipo_relatorio_atual}",
            "order": "data_criacao.desc",
            "limit": 1
        }

        cache_response = requests.get(url_busca_cache, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }, params=params_cache, timeout=15)
        cache_response.raise_for_status()
        cached_data_list = cache_response.json()

        if cached_data_list:
            cached_report = cached_data_list[0]
            data_criacao_cache_str = cached_report.get("data_criacao")
            if data_criacao_cache_str:
                data_criacao_cache = datetime.fromisoformat(data_criacao_cache_str.replace('Z', '+00:00'))
                cache_validity_period = timedelta(hours=1)
                if datetime.now(data_criacao_cache.tzinfo) - data_criacao_cache < cache_validity_period:
                    print(f"✅ Cache válido encontrado. Retornando dados cacheados.")
                    return jsonify(cached_report.get("dados_json", {})), 200

        supabase_url_consolidado = f"{SUPABASE_REST_URL}/consolidado_arquetipos"
        supabase_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        params_consolidado = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}"
        }

        supabase_response = requests.get(supabase_url_consolidado, headers=supabase_headers, params=params_consolidado, timeout=30)
        supabase_response.raise_for_status()
        consolidated_data_list = supabase_response.json()

        if not consolidated_data_list:
            return jsonify({"erro": "Relatório consolidado não encontrado no Supabase."}), 404

        relatorio_consolidado = consolidated_data_list[-1].get("dados_json", {})

        if not relatorio_consolidado:
            return jsonify({"erro": "Dados JSON do relatório consolidado vazios."}), 404

        auto = relatorio_consolidado.get("autoavaliacao", {})
        equipes = relatorio_consolidado.get("avaliacoesEquipe", [])

        respostas_auto = auto.get("respostas", {})
        respostas_equipes = [r.get("respostas", {}) for r in equipes if r.get("respostas")]

        try:
            with open("arquetipos_dominantes_por_questao.json", encoding="utf-8") as f:
                mapa_dom = json.load(f)
        except FileNotFoundError:
            return jsonify({"erro": "Arquivo 'arquetipos_dominantes_por_questao.json' não encontrado."}), 500
        except Exception as e:
            return jsonify({"erro": f"Erro ao carregar arquetipos_dominantes_por_questao.json: {str(e)}"}), 500

        try:
            matriz_df = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
        except FileNotFoundError:
            return jsonify({"erro": "Arquivo 'TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx' não encontrado."}), 500
        except Exception as e:
            return jsonify({"erro": f"Erro ao carregar TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx: {str(e)}"}), 500

        # Define lista de arquétipos para extrair_valor
        arquetipos_list_for_extrair_valor = set()
        for cod, dupla in mapa_dom.items():
            for arq in dupla:
                arquetipos_list_for_extrair_valor.add(arq)
        arquetipos_list_for_extrair_valor = sorted(list(arquetipos_list_for_extrair_valor))

        dados_gerados = {
            "titulo": "RELATÓRIO ANALÍTICO ARQUÉTIPOS - POR QUESTÃO",
            "empresa": empresa,
            "codrodada": codrodada,
            "emaillider": emaillider_req,
            "n_avaliacoes": len(respostas_equipes),
            "analitico": []
        }

        agrupado_para_frontend = {}
        for cod_questao, duplas_arquetipos in mapa_dom.items():
            chave_grupo = " e ".join(sorted(duplas_arquetipos))
            if chave_grupo not in agrupado_para_frontend:
                agrupado_para_frontend[chave_grupo] = []
            agrupado_para_frontend[chave_grupo].append(cod_questao)

        for grupo, codigos in agrupado_para_frontend.items():
            for cod in codigos:
                # ✅ AUTOAVALIAÇÃO: nota individual, busca direta na tabela
                info_auto = extrair_valor(matriz_df, cod, respostas_auto.get(cod), arquetipos_list_for_extrair_valor)

                # ✅ MÉDIA EQUIPE: busca na tabela para cada respondente individualmente
                # depois faz média dos percentuais obtidos
                percentuais_individuais = []
                soma_notas = 0
                qtd_notas = 0

                for r in respostas_equipes:
                    try:
                        nota = int(round(float(r.get(cod, 0))))
                        if 1 <= nota <= 6:
                            info_individual = extrair_valor(matriz_df, cod, nota, arquetipos_list_for_extrair_valor)
                            if info_individual:
                                percentuais_individuais.append(info_individual["percentual"])
                                soma_notas += nota
                                qtd_notas += 1
                    except (ValueError, TypeError):
                        continue

                info_eq = None
                if percentuais_individuais:
                    percentual_medio = round(sum(percentuais_individuais) / len(percentuais_individuais), 2)
                    # Busca tendência pela nota média arredondada
                    media_arredondada = round(soma_notas / qtd_notas)
                    info_tendencia = extrair_valor(matriz_df, cod, media_arredondada, arquetipos_list_for_extrair_valor)
                    if info_tendencia:
                        info_eq = {
                            "tendencia": info_tendencia["tendencia"],
                            "percentual": percentual_medio,
                            "afirmacao": info_tendencia["afirmacao"]
                        }

                if info_auto or info_eq:
                    dados_gerados["analitico"].append({
                        "grupoArquetipo": grupo,
                        "codigo": cod,
                        "afirmacao": (info_auto["afirmacao"] if info_auto else f"Afirmação para {cod}"),
                        "autoavaliacao": {
                            "tendencia": info_auto["tendencia"] if info_auto else "-",
                            "percentual": info_auto["percentual"] if info_auto else 0
                        },
                        "mediaEquipe": {
                            "tendencia": info_eq["tendencia"] if info_eq else "-",
                            "percentual": info_eq["percentual"] if info_eq else 0
                        }
                    })

        salvar_relatorio_analitico_no_supabase(dados_gerados, empresa, codrodada, emaillider_req, tipo_relatorio_atual)
        return jsonify(dados_gerados), 200

    except requests.exceptions.RequestException as e:
        error_message = f"Erro de comunicação com o Supabase: {str(e)}"
        detailed_traceback = traceback.format_exc()
        print(f"ERRO DE COMUNICAÇÃO SUPABASE: {error_message}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500
    except FileNotFoundError as e:
        error_message = f"Arquivo necessário não encontrado: {str(e)}"
        detailed_traceback = traceback.format_exc()
        print(f"ERRO DE ARQUIVO: {error_message}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500
    except Exception as e:
        error_message = str(e)
        detailed_traceback = traceback.format_exc()
        print(f"ERRO CRÍTICO NO BACKEND: {error_message}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
