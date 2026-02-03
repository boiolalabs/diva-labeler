from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os
import mysql.connector
import time
import json
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# Cliente Bluesky (singleton)
client = None

def get_client():
    """Get authenticated Bluesky client"""
    global client
    
    if client is None:
        client = Client()
        handle = os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
        password = os.getenv('BLUESKY_PASSWORD')
        
        if not password:
            raise ValueError('BLUESKY_PASSWORD not set')
        
        try:
            client.login(handle, password)
            print(f"✅ Logged in as {handle}")
            try:
                print(f"   DID: {client.me.did}")
            except:
                pass
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
        raise e

def apply_label_via_repo(subject_did, badge_name, negate=False):
    """
    Cria ou remove um label gravando DIRETAMENTE no Repositório do Labeler.
    (Self-Labeling / Repo Labeler)
    """
    c = get_client()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    action_name = "REMOVING" if negate else "ADDING"
    print(f"🔄 {action_name} BADGE '{badge_name}' PARA {subject_did}")

    # 1. Criar o objeto Label usando o Modelo Oficial
    # Fix: Usar a classe aninhada ComAtprotoLabelDefs.Label
    label_record = models.ComAtprotoLabelDefs.Label(
        src=c.me.did,
        uri=subject_did,
        val=badge_name,
        neg=negate,
        cts=now
    )

    # 2. Montar o payload para o create_record
    data_payload = {
        "repo": c.me.did,
        "collection": "com.atproto.label.defs",
        "record": label_record
    }

    try:
        print(f"📤 Sending create_record to Self Repo...")
        
        # 3. Enviar
        response = c.com.atproto.repo.create_record(data=data_payload)
        
        print(f"✅ Success: {response}")
        return {
            "success": True,
            "data": str(response)
        }
        
    except Exception as e:
        print(f"❌ Error in create_record: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# ROTA QUE FALTAVA: ATENDER O TELEFONE DO BLUESKY (LEITURA)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # Tenta pegar DID do labeler
    try:
        c = get_client()
        my_did = c.me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Fallback DID

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []})

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # A MESMA QUERY PODEROSA QUE USA AS 3 TABELAS
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
                            # Tenta converter se for objeto datetime
                            cts = row['created_at'].isoformat() + "Z"
                        except:
                            # Se já for string
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

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '3.6.1',
        'method': 'Repo Writer (Simple Labeler)',
        'labeler': os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/debug')
def debug_page():
    """
    Rota de Diagnóstico Visual (HTML) para rastrear falhas de Badges.
    Testa variáveis de ambiente, conexão DB, integridade de dados e saída JSON.
    Aceita ?did=did:plc:... para testar usuários específicos.
    """
    # 1. Parâmetros Dinâmicos
    TARGET_DID = request.args.get('did', 'did:plc:bmx5j2ukbbixbn4lo5itsf5v')
    
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

    # 1. Teste de Variáveis de Ambiente
    html_output += "<h2>1. Variáveis de Ambiente</h2><div class='card'>"
    env_vars = ['DB_HOST', 'DB_USER', 'DB_NAME', 'BLUESKY_HANDLE', 'BLUESKY_PASSWORD']
    
    for var in env_vars:
        val = os.getenv(var)
        status = "<span class='status-ok'>OK</span>" if val else "<span class='status-missing'>MISSING</span>"
        safe_val = "******" if 'PASSWORD' in var and val else (val if val else "Not Set")
        html_output += f"<div>{var}: {status} <span style='color: #64748b'>({safe_val})</span></div>"
    html_output += "</div>"

    # 1.5 Identidade Autenticada
    html_output += "<h2>1.5 Identidade Autenticada (Client)</h2><div class='card'>"
    try:
        c = get_client()
        html_output += f"<div>Handle: <span class='status-ok'>{c.me.handle}</span></div>"
        html_output += f"<div>DID: <span class='status-ok'>{c.me.did}</span></div>"
    except Exception as e:
        html_output += f"<div>Status: <span class='status-err'>Not Authenticated</span> ({str(e)})</div>"
    html_output += "</div>"
    
    # 2. Teste de Conexão MySQL
    html_output += "<h2>2. Conexão MySQL</h2><div class='card'>"
    conn = None
    try:
        start_time = time.time()
        conn = get_db_connection()
        latency = (time.time() - start_time) * 1000
        html_output += f"<div>Status: <span class='status-ok'>CONNECTED</span></div>"
        html_output += f"<div>Latency: {latency:.2f}ms</div>"
        html_output += f"<div>Server Info: {conn.get_server_info()}</div>"
    except Exception as e:
        html_output += f"<div>Status: <span class='status-err'>FAILED</span></div>"
        html_output += f"<div>Error: {str(e)}</div>"
    html_output += "</div>"

    # 3. Teste de Integridade de Dados (Query Real)
    html_output += f"<h2>3. Integridade de Dados (DID: {TARGET_DID})</h2><div class='card'>"
    
    badges_found = []
    
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            
            # 3.1 Verificar se o DID existe no user_bluesky_profiles
            cursor.execute("SELECT user_id, bluesky_handle FROM user_bluesky_profiles WHERE bluesky_did = %s", (TARGET_DID,))
            profile = cursor.fetchone()
            
            if profile:
                html_output += f"<div>✅ Perfil encontrado: <strong>{profile['bluesky_handle']}</strong> (User ID: {profile['user_id']})</div>"
                
                # 3.2 Buscar Badges para este usuário
                query = """
                    SELECT bb.label_id, bb.badge_name 
                    FROM user_badges ub
                    JOIN bluesky_badges bb ON bb.id = ub.badge_id
                    WHERE ub.user_id = %s
                """
                cursor.execute(query, (profile['user_id'],))
                badges = cursor.fetchall()
                
                if badges:
                    html_output += f"<div>✅ Badges encontrados: <span class='status-ok'>{len(badges)}</span></div><ul>"
                    for b in badges:
                        html_output += f"<li>Label Slug (val): <strong>{b['label_id']}</strong> ({b['badge_name']})</li>"
                        badges_found.append(b['label_id'])
                    html_output += "</ul>"
                else:
                    html_output += "<div>⚠️ Perfil existe, mas <strong>NÃO TEM BADGES</strong> associados na tabela 'user_badges'.</div>"
            else:
                html_output += f"<div>❌ DID não encontrado na tabela 'user_bluesky_profiles'.</div>"
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            html_output += f"<div class='status-err'>Erro SQL: {str(e)}</div>"
    else:
        html_output += "<div>Falha na conexão impediu este teste.</div>"
    
    html_output += "</div>"

    # 3.5 Auditoria Geral de Badges (Visão do Python)
    html_output += f"<h2>3.5 Auditoria Geral (Visão do Python)</h2><div class='card' style='background: #fff1f2; border-color: #fecdd3;'>"
    html_output += "<p style='color:#be123c'>O que este container (Render) enxerga no banco:</p>"
    
    if conn:
        try:
            audit_cursor = conn.cursor(dictionary=True)
            # Reconecta para garantir
            if not conn.is_connected():
                conn.reconnect()
                
            audit_query = """
                SELECT 
                    ubp.user_id, 
                    ubp.bluesky_handle, 
                    ubp.bluesky_did,
                    GROUP_CONCAT(CONCAT(bb.badge_name, ' (', bb.label_id, ')') SEPARATOR '<br>') as badges_list
                FROM user_bluesky_profiles ubp
                LEFT JOIN user_badges ub ON ubp.user_id = ub.user_id
                LEFT JOIN bluesky_badges bb ON ub.badge_id = bb.id
                GROUP BY ubp.user_id
                ORDER BY ubp.user_id DESC
                LIMIT 50
            """
            audit_cursor.execute(audit_query)
            audit_data = audit_cursor.fetchall()
            
            if audit_data:
                html_output += "<table style='width:100%; border-collapse: collapse; font-size: 0.85em; color: #000;'>"
                html_output += "<tr style='background: #ffe4e6; color: #881337;'><th style='padding:8px;'>User</th><th style='padding:8px;'>DID Status</th><th style='padding:8px;'>Badges</th></tr>"
                
                for row in audit_data:
                    did_str = row['bluesky_did']
                    did_display = f"<span style='color:green'>✅ OK</span><br><small>{did_str[:15]}...</small>" if did_str else "<span style='color:red'>❌ SEM DID</span>"
                    
                    badges_raw = row['badges_list']
                    badges_display = f"<strong style='color: #059669'>{badges_raw}</strong>" if badges_raw else "<span style='color: #999'>Nenhum</span>"
                    
                    html_output += f"<tr style='background: white; border-bottom: 1px solid #ddd;'>"
                    html_output += f"<td style='padding:8px;'><strong>{row['bluesky_handle']}</strong><br><small>ID: {row['user_id']}</small></td>"
                    html_output += f"<td style='padding:8px;'>{did_display}</td>"
                    html_output += f"<td style='padding:8px;'>{badges_display}</td>"
                    html_output += "</tr>"
                html_output += "</table>"
            else:
                html_output += "<p style='color:black'>Nenhum dado encontrado.</p>"
                
            audit_cursor.close()
        except Exception as e:
            html_output += f"<div class='status-err'>Erro Audit: {str(e)}</div>"
    else:
        html_output += "<div>Sem conexão DB.</div>"
    
    html_output += "</div>"

    # 4. Simulação output JSON (QueryLabels)
    html_output += "<h2>4. Simulação JSON Output</h2><div class='card'>"
    html_output += f"<div>Para QueryLabels(uri={TARGET_DID})</div>"
    
    simulated_labels = []
    current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    labeler_did = "did:plc:placeholder_labeler_did"
    try:
        if client and hasattr(client, 'me'):
             labeler_did = client.me.did
    except:
        pass

    for label_val in badges_found:
        simulated_labels.append({
            "src": labeler_did,
            "uri": TARGET_DID,
            "cid": "bafyre...",
            "val": label_val,
            "cts": current_time
        })
    
    json_output = {
        "cursor": "0",
        "labels": simulated_labels
    }
    
    html_output += f"<pre>{json.dumps(json_output, indent=2)}</pre>"
    
    if not badges_found:
        html_output += "<div class='status-err'>⚠️ ALERTA: A lista 'labels' está vazia! O usuário não verá labels.</div>"
    else:
        html_output += "<div class='status-ok'>✅ Tudo certo! JSON contém labels.</div>"
        
    html_output += "</div></body></html>"
    
    return html_output

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
        if not user_did.startswith('did:'):
            return jsonify({'success': False, 'error': 'Invalid DID format'}), 400
            
        print(f"\n{'='*60}\n📝 APPLYING BADGE\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # negate=False -> ADICIONAR
        result = apply_label_via_repo(user_did, label_value, negate=False)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Badge "{label_value}" aplicado com sucesso',
                'data': result.get('data')
            })
        else:
            return jsonify({'success': False, 'error': result['error']}), 500
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400
            
        print(f"\n{'='*60}\n🗑️  REMOVING BADGE\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # negate=True -> REMOVER
        result = apply_label_via_repo(user_did, label_value, negate=True)
        
        if result['success']:
            return jsonify({'success': True, 'message': 'Badge removido com sucesso'})
        else:
            return jsonify({'success': False, 'error': result['error']}), 500
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/test-connection', methods=['GET'])
def test_connection():
    try:
        c = get_client()
        return jsonify({
            'success': True,
            'message': 'Connected to Bluesky',
            'labeler': {
                'did': c.me.did,
                'handle': c.me.handle
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"\n{'='*60}")
    print(f"🚀 DIVA LABELER v3.6.1")
    print(f"   Port: {port}")
    print(f"   Method: Repo Writer (Simple)")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port)
