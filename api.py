from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os
import mysql.connector
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURAÇÕES DO BANCO
# ============================================================================
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            autocommit=True
        )
    except Exception as e:
        print(f"❌ Erro de conexão MySQL: {e}")
        return None

# ============================================================================
# 1. ROTA DE LEITURA (O QUE FAZ O BADGE APARECER NO APP)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # Pega o DID do Labeler (Emissor)
    try:
        client = Client()
        client.login(os.getenv('BLUESKY_HANDLE'), os.getenv('BLUESKY_PASSWORD'))
        my_did = client.me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Seu DID fixo

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []})

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # -----------------------------------------------------------
                # A QUERY DE JOIN (A Correção Principal)
                # -----------------------------------------------------------
                # Liga: user_badges -> bluesky_badges (para pegar o nome 'arianators')
                # Liga: user_badges -> users (para pegar o DID do usuário)
                # ⚠️ ATENÇÃO: Confirme se sua tabela de usuários se chama 'users'
                # e se a coluna do did se chama 'did'.
                query = """
                    SELECT bb.label_id, ub.created_at
                    FROM user_badges ub
                    JOIN bluesky_badges bb ON ub.badge_id = bb.id
                    JOIN users u ON ub.user_id = u.id
                    WHERE u.did = %s
                """
                
                cursor.execute(query, (pattern,))
                results = cursor.fetchall()
                
                for row in results:
                    # Formata a data
                    cts = datetime.now(timezone.utc).isoformat()
                    if row.get('created_at'):
                        cts = row['created_at'].isoformat() + "Z"
                    
                    labels.append({
                        "src": my_did,           # Nós
                        "uri": pattern,          # Usuário
                        "val": row['label_id'],  # O Slug (ex: 'arianators')
                        "cts": cts,
                        "ver": 1
                    })
        
        cursor.close()
        conn.close()
    
    except Exception as e:
        print(f"❌ Erro na Query: {e}")
        if conn and conn.is_connected(): conn.close()

    return jsonify({"cursor": "0", "labels": labels})

# ============================================================================
# 2. ROTAS DE ESCRITA (PARA PARAR O ERRO 404 DO PAINEL)
# ============================================================================
# Se o seu painel PHP já grava no banco, essas rotas só precisam retornar OK
# para o painel não travar com erro crítico.

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    # O PHP já gravou no banco? Se sim, só retornamos sucesso.
    # Se o PHP espera que a API grave, me avise que ajustamos aqui.
    return jsonify({"success": True, "message": "Recebido. Assumindo que o PHP já gravou no banco."})

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    return jsonify({"success": True, "message": "Recebido. Assumindo que o PHP já removeu do banco."})

@app.route('/')
def home():
    return jsonify({
        'status': 'online', 
        'mode': 'MySQL Normalized (Joined Tables)',
        'tables_used': ['bluesky_badges', 'user_badges', 'users']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
