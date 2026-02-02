from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os
import mysql.connector
import time
import json
from datetime import datetime, timezone

# ============================================================================
# 1. INICIALIZAÇÃO DO APP (CRUCIAL: TEM QUE SER NO TOPO)
# ============================================================================
app = Flask(__name__)
CORS(app)

# ============================================================================
# 2. FUNÇÕES AUXILIARES (BANCO E CLIENTE)
# ============================================================================
client = None

def get_client():
    """Get authenticated Bluesky client"""
    global client
    
    if client is None:
        client = Client()
        handle = os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
        password = os.getenv('BLUESKY_PASSWORD')
        
        if not password:
            # Fallback seguro se a senha não estiver setada (evita crash no boot)
            print("⚠️ BLUESKY_PASSWORD not set. Client features will fail.")
            return None
        
        try:
            client.login(handle, password)
            print(f"✅ Logged in as {handle}")
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

def get_db_connection():
    """Establish database connection"""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            connect_timeout=10
        )
        return connection
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def apply_label_via_repo(subject_did, badge_name, negate=False):
    """Cria ou remove um label gravando DIRETAMENTE no Repositório do Labeler."""
    c = get_client()
    if not c:
        return {"success": False, "error": "Bluesky Client not connected"}

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # 1. Criar o objeto Label usando o Modelo Oficial
    label_record = models.ComAtprotoLabelDefsLabel(
        src=c.me.did,
        uri=subject_did,
        val=badge_name,
        neg=negate,
        cts=now
    )

    # 2. Montar o payload
    data_payload = {
        "repo": c.me.did,
        "collection": "com.atproto.label.defs",
        "record": label_record
    }

    try:
        print(f"📤 Sending create_record to Self Repo (Badge: {badge_name})...")
        response = c.com.atproto.repo.create_record(data=data_payload)
        return {"success": True, "data": str(response)}
    except Exception as e:
        print(f"❌ Error in create_record: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# 3. ROTA DE LEITURA (O ATENDENTE DO BLUESKY)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # Tenta pegar DID do labeler
    try:
        c = get_client()
        if c:
            my_did = c.me.did
        else:
            my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v"
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Fallback

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []})

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # A QUERY PODEROSA (JOIN 3 TABELAS)
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
                    cts = datetime.now(timezone.utc).isoformat()
                    if row.get('created_at'):
                        try:
                            cts = row['created_at'].isoformat() + "Z"
                        except:
                            cts = str(row['created_at'])
                    
                    labels.append({
                        "src": my_did,
                        "uri": pattern,
                        "val": row['label_id'],
                        "cts": cts,
                        "ver": 1
                    })
        
        cursor.close()
        conn.close()
    
    except Exception as e:
        print(f"❌ Erro na Query de Leitura: {e}")
        if conn and conn.is_connected(): conn.close()

    return jsonify({"cursor": "0", "labels": labels})

# ============================================================================
# 4. ROTA DE DEBUG (O RAIO-X)
# ============================================================================
@app.route('/debug')
def debug_page():
    html_output = """
    <html>
    <head>
        <title>Diva Labeler Debugger</title>
        <style>
            body { background: #0f172a; color: #f8fafc; font-family: monospace; padding: 2rem; }
            h1 { color: #818cf8; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; }
            h2 { color: #cbd5e1; margin-top: 2rem; border-left: 4px solid #6366f1; padding-left: 10px; }
            .status-ok { color: #4ade80; font-weight: bold; }
            .status-err { color: #f87171; font-weight: bold; }
            .status-missing { color: #fbbf24; font-weight: bold; }
            .card { background: #1e293b; padding: 1.5rem; border-radius: 0.5rem; border: 1px solid #334155; margin-bottom: 1rem; }
            pre { background: #000; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; color: #a5f3fc; }
        </style>
    </head>
    <body>
        <h1>🔍 Diva Labeler Diagnostic Tool</h1>
    """

    # 1. Variáveis
    html_output += "<h2>1. Variáveis de Ambiente</h2><div class='card'>"
    env_vars = ['DB_HOST', 'DB_USER', 'DB_NAME', 'BLUESKY_HANDLE', 'BLUESKY_PASSWORD']
    for var in env_vars:
        val = os.getenv(var)
        status = "<span class='status-ok'>OK</span>" if val else "<span class='status-missing'>MISSING</span>"
        safe_val = "******" if 'PASSWORD' in var and val else (val if val else "Not Set")
        html_output += f"<div>{var}: {status} <span style='color: #64748b'>({safe_val})</span></div>"
    html_output += "</div>"

    # 2. MySQL
    html_output += "<h2>2. Conexão MySQL</h2><div class='card'>"
    conn = get_db_connection()
    if conn:
        html_output += f"<div>Status: <span class='status-ok'>CONNECTED</span></div>"
        html_output += f"<div>Server Info: {conn.get_server_info()}</div>"
    else:
        html_output += f"<div>Status: <span class='status-err'>FAILED</span></div>"
    html_output += "</div>"

    # 3. Integridade (Teste Real)
    TEST_DID = "did:plc:bmx5j2ukbbixbn4lo5itsf5v"
    html_output += f"<h2>3. Integridade de Dados (DID: {TEST_DID})</h2><div class='card'>"
    
    badges_found = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # Verifica perfil
            cursor.execute("SELECT user_id, bluesky_handle FROM user_bluesky_profiles WHERE bluesky_did = %s", (TEST_DID,))
            profile = cursor.fetchone()
            
            if profile:
                html_output += f"<div>✅ Perfil encontrado: <strong>{profile['bluesky_handle']}</strong> (User ID: {profile['user_id']})</div>"
                # Verifica badges
                q = "SELECT bb.label_id, bb.badge_name FROM user_badges ub JOIN bluesky_badges bb ON bb.id = ub.badge_id WHERE ub.user_id = %s"
                cursor.execute(q, (profile['user_id'],))
                badges = cursor.fetchall()
                if badges:
                    html_output += f"<div>✅ Badges encontrados: <span class='status-ok'>{len(badges)}</span></div><ul>"
                    for b in badges:
                        html_output += f"<li>{b['label_id']} ({b['badge_name']})</li>"
                        badges_found.append(b['label_id'])
                    html_output += "</ul>"
                else:
                    html_output += "<div>⚠️ Perfil existe, mas sem badges.</div>"
            else:
                html_output += f"<div>❌ DID não encontrado na tabela 'user_bluesky_profiles'.</div>"
            cursor.close()
            conn.close()
        except Exception as e:
            html_output += f"<div class='status-err'>Erro SQL: {str(e)}</div>"
    html_output += "</div>"
    
    html_output += "</body></html>"
    return html_output

# ============================================================================
# 5. ROTAS DE ESCRITA (PARA O PAINEL)
# ============================================================================
@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value: return jsonify({'error': 'Missing params'}), 400
        
        # Grava no Repo do Bluesky
        result = apply_label_via_repo(user_did, label_value, negate=False)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value: return jsonify({'error': 'Missing params'}), 400
        
        result = apply_label_via_repo(user_did, label_value, negate=True)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def home():
    return jsonify({'status': 'online', 'service': 'Diva Labeler v4.0'})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
