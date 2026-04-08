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
import pandas as pdIF
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import tempfile
import numpy as np
import re
import time
import base64

import json

from math import pi
from reportlab.lib.units import cm
import pandas as pd
import os
import traceback # NOVO: Para depuração detalhada

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

    for cod_pergunta in perguntas: # Itera por "Q01", "Q02", ..., "Q49"
        raw_nota = respostas_dict.get(cod_pergunta, "") # Pega a nota bruta (string)
        
        try:
            # Tenta converter a nota para float e depois para int
            nota = int(round(float(raw_nota)))
            
            # Valida se a nota está no intervalo esperado (1 a 6)
            if nota < 1 or nota > 6:
                print(f"⚠️ Nota fora do intervalo ignorada para {cod_pergunta}: '{raw_nota}' -> {nota}")
                continue # Pula para a próxima pergunta se a nota for inválida

            # Para cada arquétipo, constrói a chave e busca na matriz
            for arq_nome in arquetipos:
                # Constrói a chave no formato "ARQUETIPO_NOME_NOTA_COD_PERGUNTA"
                # Exemplo: "Formador2Q01"
                chave = f"{arq_nome}{nota}{cod_pergunta}"
                
                # Busca a linha correspondente na matriz
                # 'matriz' é o DataFrame carregado do seu Excel
                linha_matriz = matriz[matriz["CHAVE"] == chave]

                if not linha_matriz.empty:
                    # Se a chave for encontrada, extrai os pontos obtidos e máximos
                    pontos_obtidos = linha_matriz["PONTOS_OBTIDOS"].values[0]
                    pontos_maximos = linha_matriz["PONTOS_MAXIMOS"].values[0]

                    # Acumula os pontos para o arquétipo atual
                    total_por_arquetipo[arq_nome] += pontos_obtidos
                    max_por_arquetipo[arq_nome] += pontos_maximos
                else:
                    # Mensagem de depuração se a chave não for encontrada
                    print(f"⚠️ Chave '{chave}' não encontrada na matriz para {cod_pergunta} com nota {nota} e arquétipo {arq_nome}.")

        except ValueError:
            # Captura erro se 'raw_nota' não puder ser convertido para número
            print(f"⚠️ Erro de conversão para número em {cod_pergunta}: '{raw_nota}' não é um número válido.")
            continue
        except Exception as e:
            # Captura qualquer outro erro inesperado durante o processamento da pergunta
            print(f"⚠️ Erro inesperado ao processar {cod_pergunta} com nota '{raw_nota}': {e}")
            continue

    percentuais = {}
    for arq_nome in arquetipos:
        # Calcula o percentual apenas se houver pontos máximos para evitar divisão por zero
        if max_por_arquetipo[arq_nome] > 0:
            percentuais[arq_nome] = round((total_por_arquetipo[arq_nome] / max_por_arquetipo[arq_nome]) * 100, 1)
        else:
            percentuais[arq_nome] = 0 # Se não houver pontos máximos, o percentual é 0

    print(f"📊 [DEBUG] Percentuais calculados: {percentuais}")
    return percentuais


def calcular_percentuais_equipes(lista_de_respostas):
    print("📥 [DEBUG] Entrou em calcular_percentuais_equipes")
    print(f"📥 [DEBUG] Total de avaliações de equipe recebidas: {len(lista_de_respostas)}")

    soma_percentuais_por_arquetipo = {a: 0 for a in arquetipos}
    total_avaliacoes_validas = 0

    for respostas_dict_membro in lista_de_respostas:
        # Verifica se o dicionário de respostas do membro não está vazio
        if not respostas_dict_membro:
            print("⚠️ Dicionário de respostas de um membro da equipe está vazio, ignorando.")
            continue
        
        # Chama a função calcular_percentuais para cada conjunto de respostas de um membro
        percentuais_individuais = calcular_percentuais(respostas_dict_membro)
        
        # Verifica se o cálculo individual retornou percentuais válidos
        if percentuais_individuais:
            for arq_nome in arquetipos:
                # Soma os percentuais individuais para cada arquétipo
                soma_percentuais_por_arquetipo[arq_nome] += percentuais_individuais.get(arq_nome, 0)
            total_avaliacoes_validas += 1
        else:
            print("⚠️ Cálculo individual de percentuais retornou vazio para um membro da equipe. Não será incluído na média.")

    percentuais_medios = {}
    if total_avaliacoes_validas == 0:
        print("⚠️ Nenhuma avaliação de equipe válida para calcular a média. Retornando zeros.")
        return {a: 0 for a in arquetipos} # Retorna todos os percentuais como 0 se não houver avaliações válidas

    for arq_nome in arquetipos:
        # Calcula a média dos percentuais para cada arquétipo
        percentuais_medios[arq_nome] = round(soma_percentuais_por_arquetipo[arq_nome] / total_avaliacoes_validas, 1)

    print(f"📊 [DEBUG] Percentuais médios da equipe calculados: {percentuais_medios}")
    return percentuais_medios


# NOVO: Configuração global do Supabase (manter este bloco)
SUPABASE_REST_URL = os.environ.get("SUPABASE_REST_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Verifica se as variáveis de ambiente foram carregadas
if not SUPABASE_REST_URL or not SUPABASE_KEY:
    print("ERRO: Variáveis de ambiente SUPABASE_REST_URL ou SUPABASE_KEY não configuradas. Verifique suas configurações no Render.")
else:
    print("✅ Credenciais Supabase carregadas com sucesso.")

# ✅ Carrega a matriz de pontuação de arquétipos (manter estas linhas)
matriz = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
print("📄 Matriz com chave carregada. Total de linhas:", len(matriz))

# ✅ Lista de arquétipos reconhecidos na matriz (manter estas linhas)
arquetipos = ["Formador", "Resoluto", "Cuidativo", "Consultivo", "Imperativo", "Prescritivo"] # Mantenha a lista explícita que você me deu
# Se você quiser que o código determine os arquétipos da matriz, use a linha original:
# arquetipos = sorted(list(set([a[:3] for a in matriz.columns if len(a) == 6 and a[3:].isdigit()])))

# ✅ Lista de perguntas válidas (manter esta linha)
perguntas = [f"Q{str(i).zfill(2)}" for i in range(1, 50)]

def extrair_valor(matriz_df, cod, nota, arquetipos_list):
    """
    Extrai informações de tendência e percentual da matriz_df
    com base no código da questão e na nota.
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
# --- NOVA FUNÇÃO PARA SALVAR RELATÓRIO ANALÍTICO NO SUPABASE ---
# Cole esta função no seu app.py, em um local adequado para funções auxiliares.
def salvar_relatorio_analitico_no_supabase(dados_relatorio_json, empresa, codrodada, emaillider_val, tipo_relatorio_str):
    """
    Salva os dados gerados de um relatório ou gráfico no Supabase na tabela relatorios_gerados.
    Utiliza 'emaillider' e 'data_criacao' para consistência com o DB.
    """
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        print("❌ Não foi possível salvar no Supabase: Variáveis de ambiente não configuradas.")
        return False

    url = f"{SUPABASE_REST_URL}/relatorios_gerados" # Nome da tabela confirmada no Supabase

    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}" # Use a chave de serviço para escrita se for o caso
    }

    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emaillider_val, # Coluna no Supabase é 'emaillider' (minúsculo)
        "tipo_relatorio": tipo_relatorio_str,
        "dados_json": dados_relatorio_json, # O JSON completo do relatório/gráfico
        "data_criacao": datetime.now().isoformat(), # Nome da coluna ajustado para data_criacao
        # expiracao_cache pode ser omitido ou definido aqui se houver uma política
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status() # Lança um erro para status de resposta HTTP ruins (4xx ou 5xx)
        print(f"✅ JSON do '{tipo_relatorio_str}' salvo no Supabase com sucesso.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao salvar JSON do '{tipo_relatorio_str}' no Supabase: {e}")
        if hasattr(response, 'status_code') and hasattr(response, 'text'):
            print(f"Detalhes da resposta do Supabase: Status {response.status_code} - {response.text}")
        else:
            print("Não foi possível obter detalhes da resposta do Supabase.")
        return False
def salvar_relatorio_analitico_no_supabase(dados_ia, empresa, codrodada, emailLider, nome_arquivo):
    """
    Salva os dados gerados do relatório analítico no Supabase.
    """
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        print("❌ Não foi possível salvar o relatório analítico no Supabase: Variáveis de ambiente não configuradas.")
        return

    # Ajuste o nome da tabela no Supabase se for diferente.
    # Esta tabela deve ser para os dados do relatório analítico por questão.
    url = f"{SUPABASE_REST_URL}/relatorios_analiticos_hrkey" # Sugestão de nome de tabela
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}" # Use a chave de serviço para escrita se for o caso
    }

    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emailLider,
        "dados_json": dados_ia, # Os dados JSON completos do relatório analítico
        "nome_arquivo": nome_arquivo,
        "data_criacao": datetime.now().isoformat()
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status() # Lança um erro para status de resposta HTTP ruins (4xx ou 5xx)
        print("✅ JSON do relatório analítico salvo no Supabase com sucesso.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao salvar JSON do relatório analítico no Supabase: {e}")
        if hasattr(response, 'status_code') and hasattr(response, 'text'):
            print(f"Detalhes da resposta do Supabase: Status {response.status_code} - {response.text}")
        else:
            print("Não foi possível obter detalhes da resposta do Supabase.")


def salvar_json_ia_no_drive(dados, nome_base, service, id_lider):
    from io import BytesIO
    import json
    from googleapiclient.http import MediaIoBaseUpload

    nome_json = f"IA_{nome_base}.json"

    # Verifica ou cria a subpasta 'ia_json' dentro da pasta do líder
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
PASTA_RAIZ = "1ekQKwPchEN_fO4AK0eyDd_JID5YO3hAF"

# 🚀 App Flask

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

            # ⚠️ Ignorar relatórios já consolidados de microambiente
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

            # 🚫 Ignorar qualquer coisa de microambiente (campo tipo ou nome)
            if "microambiente" in tipo or "microambiente" in nome.lower():
                continue

            # ✅ Arquétipos - separar auto e equipe
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
        import requests
        from datetime import datetime

        dados = request.get_json()
        empresa = dados.get("empresa")
        codrodada = dados.get("codrodada")
        emaillider_req = dados.get("emailLider")
        print("📥 Dados recebidos:", empresa, codrodada, emaillider_req)

       # --- Lógica de Caching: Buscar JSON do Gráfico Salvo ---
        # Definir um identificador único para este gráfico
        # Usaremos 'arquetipos_grafico_comparativo'
        tipo_relatorio_grafico_atual = "arquetipos_grafico_comparativo" 

        if not SUPABASE_REST_URL or not SUPABASE_KEY:
            return jsonify({"erro": "Configuração do Supabase ausente no servidor."}), 500

        url_busca_cache = f"{SUPABASE_REST_URL}/relatorios_gerados"

        params_cache = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}", # Variável emaillider_req
            "tipo_relatorio": f"eq.{tipo_relatorio_grafico_atual}",
            "order": "data_criacao.desc",
            "limit": 1
        }

        print(f"DEBUG: Buscando cache do gráfico '{tipo_relatorio_grafico_atual}' no Supabase...")
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
                cache_validity_period = timedelta(hours=1) # Cache válido por 1 hora

                if datetime.now(data_criacao_cache.tzinfo) - data_criacao_cache < cache_validity_period:
                    print(f"✅ Cache válido encontrado para o gráfico '{tipo_relatorio_grafico_atual}'. Retornando dados cacheados.")
                    return jsonify(cached_report.get("dados_json", {})), 200
                else:
                    print(f"Cache do gráfico '{tipo_relatorio_grafico_atual}' expirado. Recalculando...")
            else:
                print("Cache encontrado, mas sem data de criação válida. Recalculando...")
        else:
            print(f"Cache do gráfico '{tipo_relatorio_grafico_atual}' não encontrado. Recalculando...")

        # --- SEU CÓDIGO DA ROTA ORIGINAL CONTINUA A PARTIR DAQUI SE O CACHE NÃO FOR ENCONTRADO OU ESTIVER EXPIRADO ---

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        filtro = f"?empresa=eq.{empresa}&codrodada=eq.{codrodada}&emaillider=eq.{emaillider_req}&select=dados_json" # <-- ALTERADO AQUI
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
            gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emaillider_req) # <-- ALTERADO AQUI

        # AS VARIÁVEIS A SEGUIR JÁ EXISTEM NO SEU CÓDIGO E TÊM OS VALORES CORRETOS:
        # - 'pct_auto' (seus Percentuais AUTO calculados)
        # - 'pct_equipes' (seus Percentuais EQUIPE calculados)
        # - 'len(respostas_equipes)' (o total de avaliações da equipe)

        # Montando o dicionário final para enviar ao frontend com os valores corretos
        json_para_frontend = {
            "titulo": dados_gerais_grafico["titulo"], # Pega do novo dicionário
            "subtitulo": dados_gerais_grafico["subtitulo"], # Pega do novo dicionário
            "info_avaliacoes": dados_gerais_grafico["info_avaliacoes"], # Pega do novo dicionário
            "arquetipos": arquetipos, # Envia a lista de arquétipos também
            "autoavaliacao": percentuais_auto_result,    # Seus percentuais de autoavaliação
            "mediaEquipe": percentuais_equipe_result,    # Seus percentuais da média da equipe
            "n_avaliacoes": num_avaliacoes_result        # A contagem de avaliações
        }

        # --- Chamar a função para salvar os dados do gráfico gerados no Supabase ---
        # Salvamos o JSON completo que será enviado ao frontend
        salvar_relatorio_analitico_no_supabase(json_para_frontend, empresa, codrodada, emaillider_req, tipo_relatorio_grafico_atual)

        # Retornando o JSON completo para o navegador
        return jsonify(json_para_frontend), 200
        

    except Exception as e:
        print("💥 Erro geral na geração do gráfico:", str(e))
        return jsonify({"erro": str(e)}), 500


def gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emaillider_req): # <-- ALTERADO AQUI
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import tempfile
    from datetime import datetime
    import base64
    import requests

    respostas_auto = json_data.get("autoavaliacao", {}).get("respostas", {})
    respostas_equipes = [
        avaliacao.get("respostas", {}) for avaliacao in json_data.get("avaliacoesEquipe", [])
    ]
    
    # 🔍 Diagnóstico antes do cálculo
    print("📄 Chaves em respostas_auto:", respostas_auto.keys())
    print("📄 Q01 =", respostas_auto.get("Q01", "vazio"))
    if respostas_equipes:
        print("📄 Q01 (equipe) da 1ª pessoa =", respostas_equipes[0].get("Q01", "vazio"))
    
    # 📊 Cálculos
    pct_auto = calcular_percentuais(respostas_auto)
    pct_equipes = calcular_percentuais_equipes(respostas_equipes)
    
    # ✅ Verificação final
    # Este bloco prepara os dados para o gráfico de barras (se você fosse gerar um no backend)
    # e também para os títulos/subtítulos do frontend.
    # Estamos mantendo ele aqui para organização e como base para futuros desenvolvimentos
    # de relatórios ou outros gráficos que possam ser gerados no backend.

    # Dados para o título/subtítulo e número de avaliações,
    # serão usados no JSON final.
    dados_gerais_grafico = {
        "titulo": "ARQUÉTIPOS DE GESTÃO",
        "subtitulo": f"{emaillider_req} | {codrodada} | {empresa}", # <-- ALTERADO AQUI
        "info_avaliacoes": f"Equipe: {len(respostas_equipes)} respondentes"
    }
    return pct_auto, pct_equipes, len(respostas_equipes), dados_gerais_grafico

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
    ax.set_title(f"ARQUÉTIPOS DE GESTÃO\n{emaillider_req} | {codrodada} | {empresa}\nEquipe: {len(respostas_equipes)} respondentes", fontsize=12) # <-- ALTERADO AQUI
    ax.legend()
    plt.tight_layout()

    print("📦 Salvando PDF em memória...")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        with PdfPages(tmp.name) as pdf:
            pdf.savefig(fig)

        with open(tmp.name, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

    print("✅ PDF convertido em base64 com sucesso.")

    # NOVO: Definindo os headers para a requisição POST
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    nome_arquivo_json = f"ARQUETIPOS_AUTO_VS_EQUIPE_{emaillider_req}_{codrodada}.json" # Alterado para .json e usando emaillider_req

    dados_ia = {
        "titulo": "ARQUÉTIPOS AUTOAVALIAÇÃO vs EQUIPE",
        "subtitulo": f"{empresa} / {emaillider_req} / {codrodada} / {datetime.now().strftime('%d/%m/%Y')}", # Usando emaillider_req
        "n_avaliacoes": len(respostas_equipes),
        "autoavaliacao": percentuais_auto_result,  # Use percentuais_auto_result aqui
        "mediaEquipe": percentuais_equipe_result    # Use percentuais_equipe_result aqui
    }

    # O payload será simplificado e enviado para salvar_relatorio_analitico_no_supabase
    # Não precisamos mais montar o payload aqui, pois a função de salvamento faz isso.
    # Apenas o `dados_ia` e os parâmetros de identificação serão passados.
    
    
    
    # Garante que as variáveis de ambiente estão sendo usadas
    # SUPABASE_REST_URL e SUPABASE_KEY já estão definidas globalmente no topo do arquivo.

    # Agora, DEFINA o dicionário 'headers' imediatamente antes de usá-lo na requisição POST.
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    print("📤 Enviando JSON + PDF para Supabase...")
    url_post = f"{SUPABASE_REST_URL}/consolidado_arquetipos"
    response = requests.post(url_post, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print("✅ Envio finalizado com sucesso.")
    else:
        print(f"❌ Erro ao enviar para Supabase: {response.status_code} → {response.text}")

    return jsonify(dados_ia), 200

@app.route("/ver-arquetipos")
def ver_arquetipos():
    return jsonify(arquetipos_dominantes)

from textwrap import wrap



@app.route("/gerar-relatorio-analitico", methods=["POST"])
def gerar_relatorio_analitico():
    try:
        dados_requisicao = request.get_json()
        empresa = dados_requisicao.get("empresa")
        codrodada = dados_requisicao.get("codrodada")
        emaillider_req = dados_requisicao.get("emailLider") # Ajustado para minúsculo para usar na API e DB

        if not all([empresa, codrodada, emaillider_req]):
            return jsonify({"erro": "Campos obrigatórios ausentes."}), 400

        # --- BUSCAR RELATÓRIO CONSOLIDADO DO SUPABASE ---
        if not SUPABASE_REST_URL or not SUPABASE_KEY:
            return jsonify({"erro": "Configuração do Supabase ausente no servidor."}), 500

        # --- Lógica de Caching: Buscar Relatório Salvo (NÃO DUPLICAR A VERIFICAÇÃO DE CHAVES!) ---
        # Nome da tabela para buscar relatórios gerados
        url_busca_cache = f"{SUPABASE_REST_URL}/relatorios_gerados"
        tipo_relatorio_atual = "arquetipos_analitico" # Identificador único para este tipo de relatório

        # Parâmetros de busca para o cache
        params_cache = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}", # Usando emaillider_req para busca
            "tipo_relatorio": f"eq.{tipo_relatorio_atual}",
            "order": "data_criacao.desc", # Pega o mais recente pela nova coluna data_criacao
            "limit": 1
        }

        print(f"DEBUG: Buscando cache do relatório '{tipo_relatorio_atual}' no Supabase...")
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
                # O Supabase retorna timestamps em formato ISO 8601 (com 'Z' para UTC)
                # datetime.fromisoformat no Python 3.11+ lida bem com isso.
                # Para Python < 3.11, pode ser necessário .replace('Z', '+00:00')
                data_criacao_cache = datetime.fromisoformat(data_criacao_cache_str.replace('Z', '+00:00')) 
                
                # Define um período de validade do cache, ex: 1 hora
                # OU uma lógica mais complexa baseada na última atualização dos dados brutos
                cache_validity_period = timedelta(hours=1) 

                if datetime.now(data_criacao_cache.tzinfo) - data_criacao_cache < cache_validity_period:
                    print(f"✅ Cache válido encontrado para o relatório '{tipo_relatorio_atual}'. Retornando dados cacheados.")
                    return jsonify(cached_report.get("dados_json", {})), 200
                else:
                    print(f"Cache do relatório '{tipo_relatorio_atual}' expirado. Recalculando...")
            else:
                print("Cache encontrado, mas sem data de criação válida. Recalculando...")
        else:
            print(f"Cache do relatório '{tipo_relatorio_atual}' não encontrado. Recalculando...")

        # --- SEU CÓDIGO DA ROTA ORIGINAL CONTINUA A PARTIR DAQUI SE O CACHE NÃO FOR ENCONTRADO OU ESTIVER EXPIRADO ---

        

        # Ajuste o nome da tabela onde o relatório consolidado está salvo no Supabase
        supabase_url_consolidado = f"{SUPABASE_REST_URL}/consolidado_arquetipos" # Verifique se este é o nome correto da sua tabela
        supabase_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Filtra por empresa, codrodada e emaillider (ajuste os nomes das colunas conforme seu Supabase)
        params_consolidado = {
            "empresa": f"eq.{empresa}",
            "codrodada": f"eq.{codrodada}",
            "emaillider": f"eq.{emaillider_req}"
        }
        
        # Faz a requisição GET para o Supabase
        print(f"DEBUG: Buscando relatório consolidado no Supabase para Empresa: {empresa}, Rodada: {codrodada}, Líder: {emaillider_req}")
        supabase_response = requests.get(supabase_url_consolidado, headers=supabase_headers, params=params_consolidado, timeout=30)
        supabase_response.raise_for_status() # Lança um erro para status HTTP ruins

        consolidated_data_list = supabase_response.json()

        if not consolidated_data_list:
            return jsonify({"erro": "Relatório consolidado não encontrado no Supabase para os dados fornecidos."}), 404

        # Assume que o último registro é o mais recente ou que só há um
        # Ou adicione lógica para escolher o mais relevante se houver múltiplos
        relatorio_consolidado = consolidated_data_list[-1].get("dados_json", {})

        if not relatorio_consolidado:
            return jsonify({"erro": "Dados JSON do relatório consolidado vazios no Supabase para os dados fornecidos."}), 404

        auto = relatorio_consolidado.get("autoavaliacao", {})
        equipes = relatorio_consolidado.get("avaliacoesEquipe", [])

        respostas_auto = auto.get("respostas", {})
        respostas_equipes = [r.get("respostas", {}) for r in equipes if r.get("respostas")]

        # --- CARREGAR ARQUIVOS JSON E EXCEL LOCAIS ---
        # Certifique-se de que 'arquetipos_dominantes_por_questao.json' e 'TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx'
        # estão presentes no diretório raiz do seu projeto no Render.com.
        try:
            with open("arquetipos_dominantes_por_questao.json", encoding="utf-8") as f:
                mapa_dom = json.load(f)
            print("DEBUG: arquetipos_dominantes_por_questao.json carregado com sucesso.")
        except FileNotFoundError:
            return jsonify({"erro": "Arquivo 'arquetipos_dominantes_por_questao.json' não encontrado no servidor."}), 500
        except json.JSONDecodeError:
            return jsonify({"erro": "Erro ao decodificar 'arquetipos_dominantes_por_questao.json'. Verifique o formato JSON."}), 500
        except Exception as e:
            return jsonify({"erro": f"Erro ao carregar 'arquetipos_dominantes_por_questao.json': {str(e)}"}), 500

        try:
            matriz_df = pd.read_excel("TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx")
            print("DEBUG: TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx carregada com sucesso.")
        except FileNotFoundError:
            return jsonify({"erro": "Arquivo 'TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx' não encontrado no servidor."}), 500
        except Exception as e:
            return jsonify({"erro": f"Erro ao carregar 'TABELA_GERAL_ARQUETIPOS_COM_CHAVE.xlsx': {str(e)}"}), 500


        # Definir a lista de arquétipos para a função extrair_valor
        arquetipos_list_for_extrair_valor = set()
        for cod, dupla in mapa_dom.items():
            for arq in dupla:
                arquetipos_list_for_extrair_valor.add(arq)
        arquetipos_list_for_extrair_valor = sorted(list(arquetipos_list_for_extrair_valor))

        # Preparar dados para o frontend
        dados_gerados = {
            "titulo": "RELATÓRIO ANALÍTICO ARQUÉTIPOS - POR QUESTÃO",
            "empresa": empresa,
            "codrodada": codrodada,
            "emaillider": emaillider_req, # CORREÇÃO: Usando a variável correta 'emaillider_req'
            "n_avaliacoes": len(respostas_equipes), # Número de avaliações da equipe
            "analitico": []
        }

        # Recriar a estrutura 'agrupado' para o agrupamento consistente no frontend
        agrupado_para_frontend = {}
        for cod_questao, duplas_arquetipos in mapa_dom.items():
            chave_grupo = " e ".join(sorted(duplas_arquetipos))
            if chave_grupo not in agrupado_para_frontend:
                agrupado_para_frontend[chave_grupo] = []
            agrupado_para_frontend[chave_grupo].append(cod_questao)

        # Iterar sobre as questões agrupadas para popular 'analitico'
        for grupo, codigos in agrupado_para_frontend.items():
            for cod in codigos:
                info_auto = extrair_valor(matriz_df, cod, respostas_auto.get(cod), arquetipos_list_for_extrair_valor)
                
                somatorio = 0
                qtd_avaliacoes = 0
                for r in respostas_equipes:
                    try:
                        nota = int(round(float(r.get(cod, 0))))
                        if 1 <= nota <= 6:
                            somatorio += nota
                            qtd_avaliacoes += 1
                    except (ValueError, TypeError):
                        continue

                info_eq = None
                if qtd_avaliacoes > 0:
                    media_real = somatorio / qtd_avaliacoes
                    percentual_eq = round((media_real / 6) * 100, 2)
                    media_arredondada = round(media_real)
                    info_eq_base = extrair_valor(matriz_df, cod, media_arredondada, arquetipos_list_for_extrair_valor)
                    if info_eq_base:
                        info_eq = {
                            "tendencia": info_eq_base["tendencia"],
                            "percentual": percentual_eq,
                            "afirmacao": info_eq_base["afirmacao"]
                        }

                
                # Incluir a questão apenas se houver dados de autoavaliação ou equipe
                if info_auto or info_eq:
                    dados_gerados["analitico"].append({
                        "grupoArquetipo": grupo, # Adicionado este campo para o agrupamento no frontend
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
        
        # Chamar a NOVA função para salvar os dados analíticos gerados no Supabase
        nome_arquivo_supabase = f"RELATORIO_ANALITICO_DADOS_{empresa}_{emaillider_req}_{codrodada}"
        salvar_relatorio_analitico_no_supabase(dados_gerados, empresa, codrodada, emaillider_req, tipo_relatorio_atual)

        # Retorna os dados gerados como JSON para o frontend
        return jsonify(dados_gerados), 200

    except requests.exceptions.RequestException as e:
        # Erros específicos de requisição HTTP (Supabase)
        error_message = f"Erro de comunicação com o Supabase: {str(e)}"
        detailed_traceback = traceback.format_exc()
        print(f"ERRO DE COMUNICAÇÃO SUPABASE: {error_message}")
        print(f"TRACEBACK COMPLETO:\n{detailed_traceback}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500
    except FileNotFoundError as e:
        # Erros de arquivo não encontrado
        error_message = f"Arquivo necessário não encontrado no servidor: {str(e)}"
        detailed_traceback = traceback.format_exc()
        print(f"ERRO DE ARQUIVO: {error_message}")
        print(f"TRACEBACK COMPLETO:\n{detailed_traceback}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500
    except Exception as e:
        # Captura e retorna qualquer outro erro detalhado para depuração no frontend
        error_message = str(e)
        detailed_traceback = traceback.format_exc()
        print(f"ERRO CRÍTICO NO BACKEND (GENÉRICO): {error_message}")
        print(f"TRACEBACK COMPLETO:\n{detailed_traceback}")
        return jsonify({"erro": error_message, "traceback": detailed_traceback}), 500








# --- NOVA FUNÇÃO PARA SALVAR O RELATÓRIO ANALÍTICO NO SUPABASE ---
# Mantenha sua função 'salvar_json_ia_no_supabase' existente intacta.
# Esta nova função será usada APENAS para o Relatório Analítico.
def salvar_relatorio_analitico_no_supabase(dados_ia, empresa, codrodada, emaillider_val, tipo_relatorio_str):
    """
    Salva os dados gerados do relatório analítico no Supabase.
    """
    if not SUPABASE_REST_URL or not SUPABASE_KEY:
        print("❌ Não foi possível salvar o relatório analítico no Supabase: Variáveis de ambiente não configuradas.")
        return

    # Ajuste o nome da tabela no Supabase se for diferente.
    # Esta tabela deve ser para os dados do relatório analítico por questão.
    url = f"{SUPABASE_REST_URL}/relatorios_gerados" # CORREÇÃO: Nome da tabela é 'relatorios_gerados'
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}" # Use a chave de serviço para escrita se for o caso
    }

    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emaillider_val, # Agora usando o parâmetro correto da função
        "dados_json": dados_ia, # Os dados JSON completos do relatório analítico
        "tipo_relatorio": tipo_relatorio_str,
        "data_criacao": datetime.now().isoformat()
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status() # Lança um erro para status de resposta HTTP ruins (4xx ou 5xx)
        print("✅ JSON do relatório analítico salvo no Supabase com sucesso.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao salvar JSON do relatório analítico no Supabase: {e}")
        if hasattr(response, 'status_code') and hasattr(response, 'text'):
            print(f"Detalhes da resposta do Supabase: Status {response.status_code} - {response.text}")
        else:
            print("Não foi possível obter detalhes da resposta do Supabase.")

# --- EXECUÇÃO DO FLASK APP ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))

