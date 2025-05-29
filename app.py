
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

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
