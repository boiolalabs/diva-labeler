from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os
import mysql.connector
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONEXÃO COM O MYSQL (Lê as variáveis do Render)
# ============================================================================
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv('DB_HOST'),      # O Render vai preencher isso com o IP
            user=os.getenv('DB_USER'),      # O Render preenche o usuário
            password=os.getenv('DB_PASSWORD'), # O Render preenche a senha
            database=os.getenv('DB_NAME'),  # O Render preenche o nome do banco
            autocommit=True,
            connect_timeout=10 # Evita travar se o banco demorar
        )
    except Exception as e:
        print(f"❌ Erro fatal ao conectar no DB: {e}")
        return None

def get_active_badges_for_user(user_did):
    """
    Busca no MySQL quais badges o usuário tem aprovados.
    """
    badges = []
    conn = get_db_connection()
    
    if not conn:
        return []

    try:
        cursor = conn.cursor(dictionary=True)
        
        # --- QUERY SQL (Ajuste para bater com sua tabela do Admin) ---
        # Exemplo: Buscando da tabela 'requests' onde status é 'approved'
        # Se sua tabela tem outro nome (ex: user_badges), troque aqui.
        query = """
            SELECT badge_slug, created_at 
            FROM requests 
            WHERE user_did = %s AND status = 'approved'
        """
        
        cursor.execute(query, (user_did,))
        results = cursor.fetchall()
        
        for row in results:
            # Garante que temos uma data válida
            cts_val = datetime.now(timezone.utc).isoformat()
            if row.get('created_at'):
                cts_val = row['created_at'].isoformat() + "Z"

            badges.append({
                "val": row['badge_slug'], # ID do badge (ex: 'maconheira')
                "cts": cts_val
            })
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erro na Query MySQL: {e}")
        if conn and conn.is_connected():
            conn.close()
            
    return badges

# ============================================================================
# CLIENTE BLUESKY
# ============================================================================
client = None
def get_client():
    global client
    if client is None:
        client = Client()
        try:
            client.login(os.getenv('BLUESKY_HANDLE'), os.getenv('BLUESKY_PASSWORD'))
        except:
            print("⚠️ Erro no login do Bluesky (mas a leitura do banco segue funcionando)")
    return client

# ============================================================================
# ROTA PRINCIPAL (Query Labels)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    # O App pergunta: "Quais badges esses usuários têm?"
    uri_patterns = request.args.getlist('uriPatterns')
    
    labels = []
    
    # Tenta pegar nosso DID, se falhar usa o fixo
    try:
        my_did = get_client().me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v"

    for pattern in uri_patterns:
        if pattern.startswith('did:'):
            # 1. Consulta o MySQL
            user_badges = get_active_badges_for_user(pattern)
            
            # 2. Formata a resposta para o Bluesky
            for b in user_badges:
                labels.append({
                    "src": my_did,     # Nós (Emissor)
                    "uri": pattern,    # Usuário (Receptor)
                    "val": b['val'],   # Nome do Badge
                    "cts": b['cts'],   # Data
                    "ver": 1
                })
    
    return jsonify({
        "cursor": "0",
        "labels": labels
    })

@app.route('/')
def home():
    # Rota de debug para saber se as variáveis estão carregadas (sem mostrar a senha)
    db_host = os.getenv('DB_HOST', 'NÃO CONFIGURADO')
    return jsonify({
        'status': 'online',
        'service': 'Diva Labeler (MySQL)',
        'connected_to_db_host': db_host
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
