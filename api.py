from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os
import sqlite3
import json
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURAÇÃO DO BANCO DE DADOS (O "Bibliotecário")
# ============================================================================
DB_NAME = "badges.db"

def init_db():
    """Cria a tabela de badges se não existir."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                did TEXT,
                val TEXT,
                neg INTEGER,
                cts TEXT,
                PRIMARY KEY (did, val)
            )
        """)
    print("📚 Banco de dados (SQLite) inicializado.")

def save_badge_local(did, val, neg, cts):
    """Salva ou remove o badge do banco local para leitura rápida."""
    with sqlite3.connect(DB_NAME) as conn:
        if neg:
            # Se for negate (remover), deletamos do banco
            conn.execute("DELETE FROM badges WHERE did = ? AND val = ?", (did, val))
        else:
            # Se for adicionar, gravamos (ou atualizamos)
            conn.execute("""
                INSERT OR REPLACE INTO badges (did, val, neg, cts)
                VALUES (?, ?, ?, ?)
            """, (did, val, 0, cts))

def get_badges_local(did):
    """Lê os badges de um usuário específico."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.execute("SELECT val, cts FROM badges WHERE did = ?", (did,))
        return cursor.fetchall()

# Inicializa o banco ao ligar
init_db()

# ============================================================================
# CLIENTE BLUESKY
# ============================================================================
client = None

def get_client():
    global client
    if client is None:
        client = Client()
        handle = os.getenv('BLUESKY_HANDLE')
        password = os.getenv('BLUESKY_PASSWORD')
        if not password: raise ValueError('BLUESKY_PASSWORD not set')
        client.login(handle, password)
    return client

# ============================================================================
# 1. ROTA DE LEITURA (O QUE O APP DO BLUESKY CHAMA)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    """
    O App do Bluesky bate AQUI para saber quais badges mostrar.
    """
    uri_patterns = request.args.getlist('uriPatterns')
    
    labels = []
    c = get_client() # Precisamos do DID do labeler (nós mesmos)
    my_did = c.me.did

    # Para cada usuário que o App perguntou...
    for pattern in uri_patterns:
        # Se for um DID de usuário (ex: did:plc:123...)
        if pattern.startswith('did:'):
            badges = get_badges_local(pattern)
            for val, cts in badges:
                labels.append({
                    "src": my_did,     # Quem deu o badge (nós)
                    "uri": pattern,    # Quem recebeu
                    "val": val,        # Nome do badge
                    "cts": cts,        # Data
                    "ver": 1
                })
    
    # Retorna no formato que o Bluesky exige
    return jsonify({
        "cursor": "0",
        "labels": labels
    })

# ============================================================================
# 2. ROTAS DE ESCRITA (ADMIN)
# ============================================================================

def apply_label_logic(subject_did, badge_name, negate=False):
    c = get_client()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # 1. Gravar no Repositório Oficial (Backup/Histórico)
    try:
        label_record = {
            "$type": "com.atproto.label.defs",
            "src": c.me.did,
            "uri": subject_did,
            "val": badge_name,
            "neg": negate,
            "cts": now
        }
        c.com.atproto.repo.create_record({
            "repo": c.me.did,
            "collection": "com.atproto.label.defs",
            "record": label_record
        })
        print(f"✅ Gravado no Repo: {badge_name} -> {subject_did}")
    except Exception as e:
        print(f"⚠️ Erro ao gravar no repo (mas vou tentar salvar local): {e}")

    # 2. Gravar no Banco Local (Para o App conseguir ler)
    try:
        save_badge_local(subject_did, badge_name, negate, now)
        print(f"✅ Gravado no SQLite: {badge_name} -> {subject_did}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    data = request.json
    result = apply_label_logic(data.get('did'), data.get('label'), negate=False)
    return jsonify(result), (200 if result['success'] else 500)

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    data = request.json
    result = apply_label_logic(data.get('did'), data.get('label'), negate=True)
    return jsonify(result), (200 if result['success'] else 500)

@app.route('/')
def home():
    return jsonify({
        'status': 'online', 
        'service': 'Diva Labeler v4.0 (Full)', 
        'did': get_client().me.did
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
