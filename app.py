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
        emailLider = dados.get("emailLider")
        print("📥 Dados recebidos:", empresa, codrodada, emailLider)

       

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        filtro = f"?empresa=eq.{empresa}&codrodada=eq.{codrodada}&emaillider=eq.{emailLider}&select=dados_json"
        url = f"{SUPABASE_REST_URL}/consolidado_arquetipos{filtro}"
        print("🔎 Buscando consolidado no Supabase:", url)

        resp = requests.get(url, headers=headers)
        registros = resp.json()

        if not registros or "dados_json" not in registros[0]:
            print("❌ Consolidado não encontrado ou formato inválido.")
            return jsonify({"erro": "Consolidado não encontrado no Supabase."}), 404

        json_data = registros[0]["dados_json"]
        print("📄 Consolidado encontrado. Chaves:", list(json_data.keys()))

        gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emailLider)

        return jsonify({
            "titulo": dados_do_grafico["titulo"], # Supondo que você tenha os dados em uma variável
            "subtitulo": dados_do_grafico["subtitulo"],
            "mediaEquipe": dados_do_grafico["mediaEquipe"],
            "n_avaliacoes": dados_do_grafico["n_avaliacoes"],
            "autoavaliacao": dados_do_grafico["autoavaliacao"]
            # E talvez a mensagem também, se quiser que ela apareça no console do frontend
            # "mensagem": "✅ PDF e JSON gerados com sucesso e salvos no Supabase."
        }), 200

    except Exception as e:
        print("💥 Erro geral na geração do gráfico:", str(e))
        return jsonify({"erro": str(e)}), 500


def gerar_grafico_completo_com_titulo(json_data, empresa, codrodada, emailLider):
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
    print("📊 Percentuais AUTO:", pct_auto)
    print("📊 Percentuais EQUIPE:", pct_equipes)
    print("🖨️ Gerando gráfico...")

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
    nome_arquivo = f"ARQUETIPOS_AUTO_VS_EQUIPE_{emailLider}_{codrodada}.pdf"

    dados_ia = {
        "titulo": "ARQUÉTIPOS AUTOAVALIAÇÃO vs EQUIPE",
        "subtitulo": f"{empresa} / {emailLider} / {codrodada} / {datetime.now().strftime('%d/%m/%Y')}",
        "n_avaliacoes": len(respostas_equipes),
        "autoavaliacao": pct_auto,
        "mediaEquipe": pct_equipes
    }

    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emailLider,
        "data_criacao": datetime.utcnow().isoformat(),
        "dados_json": dados_ia,
        "nome_arquivo": nome_arquivo,
        "arquivo_pdf_base64": pdf_base64
    }

    
    
    
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

def inserir_rodape(c, width, empresa, emailLider, codrodada):
    if c.getPageNumber() > 1:
        c.setFont("Helvetica", 8)
        rodape_y = 1.5 * cm
        info1 = f"Empresa: {empresa} | Líder: {emailLider} | Rodada: {codrodada}"
        info2 = datetime.now().strftime("%d/%m/%Y %H:%M")
        c.drawString(2 * cm, rodape_y, f"{info1} | {info2}")
        c.drawRightString(width - 2 * cm, rodape_y, f"Página {c.getPageNumber() - 1}")


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

        c.setFont("Helvetica-Bold", 30)
        titulo = "Relatório Analítico por Arquétipos"
        c.drawCentredString(width / 2, height / 2, titulo)

        c.setFont("Helvetica", 12)
        info1 = f"Empresa: {empresa} | Líder: {emailLider} | Rodada: {codrodada}"
        info2 = datetime.now().strftime("%d/%m/%Y %H:%M")

        linha1_y = (height / 2) - 1.2 * cm
        linha2_y = linha1_y - 0.6 * cm

        c.drawCentredString(width / 2, linha1_y, info1)
        c.drawCentredString(width / 2, linha2_y, info2)
        c.showPage()


        y = height - 3 * cm
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
            cor = (1.0, 0.5, 0.0) if any(w in label.lower() for w in ["desfavorável", "pouco desfavorável", "muito desfavorável"]) else (0.2, 0.6, 0.2)
            largura = largura_max * (percentual / 100)
            c.setFillColorRGB(*cor)
            c.rect(x, y, largura, altura, fill=True, stroke=False)
            c.setFillColorRGB(0, 0, 0)
            for i in range(0, 110, 10):
                xi = x + (largura_max * i / 100)
                c.line(xi, y, xi, y + altura)
                c.setFont("Helvetica", 6)
                c.drawString(xi - 0.2 * cm, y - 0.3 * cm, f"{i}%")

        primeiro_grupo = True
        for grupo, codigos in agrupado.items():
            if not primeiro_grupo:
                c.showPage()
            else:
                primeiro_grupo = False

            y = height - 3 * cm
            c.setFont("Helvetica-Bold", 12)
            c.drawString(2 * cm, y, f"🔹 Afirmações que impactam os arquétipos: {grupo}")
            y -= espacamento / 2


            for cod in codigos:
                info_auto = extrair_valor(matriz_df, cod, respostas_auto.get(cod))
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

                texto_afirmacao = f"{cod}: {texto}"
                linhas_afirmacao = wrap(texto_afirmacao, width=100)
                textobj = c.beginText()
                textobj.setTextOrigin(2 * cm, y)
                textobj.setFont("Helvetica", 10)
                for linha in linhas_afirmacao:
                    textobj.textLine(linha)
                c.drawText(textobj)
                y -= espacamento / 2 + (len(linhas_afirmacao) - 1) * 0.5 * cm

                c.drawString(2.5 * cm, y, f"Autoavaliação → Tendência: {tendencia_auto} | %: {percentual_auto}%")
                y -= 0.6 * cm
                desenhar_barra(c, 2.5 * cm, y, percentual_auto, tendencia_auto)
                y -= espacamento / 2

                c.setFont("Helvetica", 10)
                c.drawString(2.5 * cm, y, f"Média Equipe → Tendência: {tendencia_eq} | %: {percentual_eq}%")
                y -= 0.6 * cm
                desenhar_barra(c, 2.5 * cm, y, percentual_eq, tendencia_eq)
                y -= espacamento / 1

                if y < 4 * cm and cod != codigos[-1]:  # Evita página em branco no último item
                    c.setFont("Helvetica", 8)
                    c.drawRightString(width - 2 * cm, 2.1 * cm, f"Página {c.getPageNumber()}")
                    c.showPage()
                    y = height - 4 * cm


        c.save()

        file_metadata = {"name": nome_pdf, "parents": [id_lider]}
        media = MediaFileUpload(tmp_path, mimetype="application/pdf", resumable=False)
        enviado = service.files().create(body=file_metadata, media_body=media, fields="id").execute()





        # 🔁 Salvar JSON com os dados do relatório analítico
        dados_gerados = {
            "titulo": "RELATÓRIO ANALÍTICO ARQUÉTIPOS - POR QUESTÃO",
            "empresa": empresa,
            "codrodada": codrodada,
            "emailLider": emailLider,
            "n_avaliacoes": len(respostas_equipes),
            "analitico": []
        }

        for grupo, codigos in agrupado.items():
            for cod in codigos:
                info_auto = extrair_valor(matriz_df, cod, respostas_auto.get(cod))
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

                dados_gerados["analitico"].append({
                    "codigo": cod,
                    "afirmacao": info_auto["afirmacao"] if info_auto else cod,
                    "autoavaliacao": {
                        "tendencia": info_auto["tendencia"] if info_auto else "-",
                        "percentual": info_auto["percentual"] if info_auto else 0
                    },
                    "mediaEquipe": {
                        "tendencia": info_eq["tendencia"] if info_eq else "-",
                        "percentual": info_eq["percentual"] if info_eq else 0
                    }
                })

        nome_base = nome_pdf.replace(".pdf", "")
        salvar_json_ia_no_drive(dados_gerados, nome_base, service, id_lider)


        return jsonify({"mensagem": "✅ Relatório analítico gerado e salvo com sucesso."})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


def salvar_json_ia_no_drive(dados, nome_base, service, id_lider):
    try:
        from io import BytesIO
        import json
        from googleapiclient.http import MediaIoBaseUpload

        # Verifica (ou cria) subpasta ia_json
        def buscar_id(nome, pai):
            q = f"'{pai}' in parents and name='{nome}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            resp = service.files().list(q=q, fields="files(id)").execute().get("files", [])
            return resp[0]["id"] if resp else None

        id_pasta_ia = buscar_id("ia_json", id_lider)
        if not id_pasta_ia:
            pasta = service.files().create(
                body={"name": "ia_json", "mimeType": "application/vnd.google-apps.folder", "parents": [id_lider]},
                fields="id"
            ).execute()
            id_pasta_ia = pasta["id"]

        nome_arquivo = f"IA_{nome_base}.json"
        conteudo_bytes = BytesIO(json.dumps(dados, indent=2, ensure_ascii=False).encode("utf-8"))
        media = MediaIoBaseUpload(conteudo_bytes, mimetype="application/json")

        file_metadata = {"name": nome_arquivo, "parents": [id_pasta_ia]}
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        print(f"✅ JSON IA salvo no Drive: {nome_arquivo}")
    except Exception as e:
        print(f"❌ Erro ao salvar JSON IA: {str(e)}")




def salvar_json_ia_no_supabase(dados_ia, empresa, codrodada, emailLider, nome_arquivo):
    url = f"{SUPABASE_REST_URL}/consolidado_arquetipos"
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    payload = {
        "empresa": empresa,
        "codrodada": codrodada,
        "emaillider": emailLider,
        "dados_json": dados_ia,
        "nome_arquivo": nome_arquivo,
        "data_criacao": datetime.now().isoformat()
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if not response.ok:
        print("❌ Erro ao salvar no Supabase:", response.status_code, response.text)
    else:
        print("✅ JSON do gráfico salvo no Supabase com sucesso.")



