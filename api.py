from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os
import mysql.connector
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURAÇÕES DE BANCO
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
# 1. ROTA DE LEITURA (O QUE O BLUESKY CONSOME)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # 1. Pega o DID do Emissor (Nós)
    try:
        client = Client()
        client.login(os.getenv('BLUESKY_HANDLE'), os.getenv('BLUESKY_PASSWORD'))
        my_did = client.me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Fallback

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []})

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # ==================================================================
                # A QUERY PERFEITA (3 Tabelas)
                # ==================================================================
                # 1. user_badges (ub): Quem tem o badge (usa user_id)
                # 2. bluesky_badges (bb): O nome do badge (label_id)
                # 3. user_bluesky_profiles (ubp): Traduz o DID para user_id
                query = """
                    SELECT bb.label_id, ub.created_at
                    FROM user_badges ub
                    JOIN bluesky_badges bb ON ub.badge_id = bb.id
                    JOIN user_bluesky_profiles ubp ON ub.user_id = ubp.user_id
                    WHERE ubp.bluesky_did = %s
                """
                
                cursor.execute(query, (pattern,))
                results = cursor.fetchall()
                
                for row in results:
                    # Formata a data para o padrão UTC/ISO
                    cts = datetime.now(timezone.utc).isoformat()
                    if row.get('created_at'):
                        cts = row['created_at'].isoformat() + "Z"
                    
                    labels.append({
                        "src": my_did,           # Nós (Labeler)
                        "uri": pattern,          # Usuário (Dono do perfil)
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
# 2. ROTAS DE ESCRITA (DUMMY - Para seu Painel não dar erro 404)
# ============================================================================
# Como seu painel PHP já grava direto no banco, essas rotas servem apenas
# para responder "OK, recebi" quando o painel tentar notificar a API.

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    return jsonify({"success": True, "message": "PHP Panel handles DB write."})

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    return jsonify({"success": True, "message": "PHP Panel handles DB write."})

@app.route('/')
def home():
    return jsonify({
        'status': 'online', 
        'mode': 'Correct Schema (user_bluesky_profiles)', 
        'tables_used': ['bluesky_badges', 'user_badges', 'user_bluesky_profiles']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
