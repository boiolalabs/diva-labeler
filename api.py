from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os
import mysql.connector
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURAÇÕES
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
# 1. ROTA DE LEITURA (A Mágica dos JOINS)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # 1. Pega o DID do Labeler (Nós)
    try:
        client = Client()
        client.login(os.getenv('BLUESKY_HANDLE'), os.getenv('BLUESKY_PASSWORD'))
        my_did = client.me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Seu DID fixo (fallback)

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []}) # Retorna vazio se sem banco

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # ==================================================================
                # A QUERY DE TRADUÇÃO (JOIN)
                # ==================================================================
                # 1. 'ub' (user_badges) diz quem tem o badge.
                # 2. 'bb' (bluesky_badges) traduz o ID numérico para o slug (label_id).
                # 3. 'u' (users) traduz o DID (texto) para o ID numérico.
                # ⚠️ Verifique se sua tabela de usuários se chama 'users' e tem coluna 'did'
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
                    # Define a data
                    cts = datetime.now(timezone.utc).isoformat()
                    if row.get('created_at'):
                        cts = row['created_at'].isoformat() + "Z"
                    
                    # Adiciona na lista de resposta
                    labels.append({
                        "src": my_did,           # Quem emite (Nós)
                        "uri": pattern,          # Quem recebe (Usuário)
                        "val": row['label_id'],  # O Slug (ex: 'maconheira') vindo da tabela bluesky_badges
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
# 2. ROTAS DE ESCRITA (Admin Panel)
# ============================================================================
# ATENÇÃO: Se o seu painel PHP já grava direto no banco, você NÃO precisa dessas rotas.
# Mas se o painel tentar chamar a API para gravar, elas precisam ser inteligentes
# para buscar os IDs antes de inserir. Manti simplificado para evitar erros de FK.

@app.route('/')
def home():
    return jsonify({
        'status': 'online', 
        'mode': 'Relational DB (Joins)', 
        'tables': ['bluesky_badges', 'user_badges', 'users']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
