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
    # Fix: Converter o modelo Pydantic para dicionário usando ALIASES (ver, cts, val) e removendo Nulos
    # O SDK espera um dict no campo 'record'
    record_dict = label_record.model_dump(by_alias=True, exclude_none=True)
    
    # Garantir que 'ver' (versão) esteja presente se for exigido (Label Defs v1)
    if 'ver' not in record_dict: # Opcional, mas bom forçar para v1
        record_dict['ver'] = 1

    # Fix: Remover $type e py_type se existirem, pois create_record pode adicionar o seu próprio
    # e o PDS pode rejeitar se vier duplicado ou específico demais (#label vs main)
    record_dict.pop('$type', None)
    record_dict.pop('py_type', None)

    data_payload = {
        "repo": c.me.did,
        "collection": "com.atproto.label.defs",
        "record": record_dict
    }

    print(f"📦 JSON Record Payload: {json.dumps(record_dict)}")

    try:
        print(f"📤 Sending create_record to Self Repo...")
        
        # 3. Enviar
        response = c.com.atproto.repo.create_record(data=data_payload)
        
        # Parse Response
        new_uri = getattr(response, 'uri', '')
        new_cid = getattr(response, 'cid', '')
        rkey = new_uri.split('/')[-1] if new_uri else 'unknown'
        
        print(f"✅ Success! URI: {new_uri} | CID: {new_cid}")

        # --- SIMULACAO JETSTREAM (O que a rede verá) ---
        js_event = {
            "did": c.me.did,
            "kind": "commit",
            "commit": {
                "operation": "create",
                "collection": "com.atproto.label.defs",
                "rkey": rkey,
                "record": record_dict, # Strict JSON we built earlier
                "cid": new_cid
            }
        }
        print(f"🌊 Jetstream Event Simulation:\n{json.dumps(js_event, indent=2)}")
        # ---------------------------------------------

        return {
            "success": True,
            "uri": new_uri,
            "cid": new_cid,
            "rkey": rkey,
            "jetstream_simulation": js_event
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
    today = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    html_output += f"<div style='color: #64748b; margin-top:-15px; margin-bottom:20px;'>Last Render Start: {today} | v3.6.2 (Simulação Global)</div>"
    # 0. DASHBOARD DE STATUS (Conectividade)
    html_output += "<div style='background: #1e293b; border: 1px solid #334155; padding: 20px; margin-bottom: 20px; border-radius: 8px; text-align:center;'>"
    html_output += "<h3 style='margin-top:0; color: #cbd5e1;'>📡 Connectivity Status</h3>"
    html_output += "<div style='display:flex; justify_content:space-around; align-items:center; font-weight:bold; font-size:1.1em;'>"

    # RENDER (SELF)
    html_output += "<div><span style='font-size:2em'>🐍</span><br>Render<br><small style='color:#4ade80'>ONLINE</small></div>"

    # SETA
    html_output += "<div style='font-size:1.5em; color:#94a3b8;'>➜</div>"

    # DB CHECK
    db_status = "UNKNOWN"
    db_color = "#f59e0b"
    try:
        conn = get_db_connection()
        if conn and conn.is_connected():
            db_status = "CONNECTED"
            db_color = "#4ade80"
            conn.close()
        else:
            db_status = "FAILED"
            db_color = "#f87171"
    except:
        db_status = "ERROR"
        db_color = "#f87171"

    html_output += f"<div><span style='font-size:2em'>🛢️</span><br>MySQL<br><small style='color:{db_color}'>{db_status}</small></div>"

    # SETA
    html_output += "<div style='font-size:1.5em; color:#94a3b8;'>➜</div>"

    # BLUESKY CHECK
    bsky_status = "UNKNOWN"
    bsky_color = "#f59e0b"
    try:
        c = get_client()
        # Ping rápido para verificar validade do token
        if c.me.did:
            bsky_status = "CONNECTED"
            bsky_color = "#4ade80"
    except:
        bsky_status = "FAILED"
        bsky_color = "#f87171"

    html_output += f"<div><span style='font-size:2em'>🦋</span><br>Bluesky<br><small style='color:{bsky_color}'>{bsky_status}</small></div>"

    html_output += "</div></div>"

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
    html_output += "<h2>1.5 Checagem de Conexão (Triangulação)</h2><div class='card'>"
    try:
        c = get_client()
        # Teste REAL de conexão (fetch profile)
        start_ping = time.time()
        profile = c.get_profile(actor=c.me.did)
        ping_ms = (time.time() - start_ping) * 1000
        
        html_output += f"<div>Status: <span class='status-ok'>CONNECTED</span> (Ping: {ping_ms:.0f}ms)</div>"
        html_output += f"<div>Handle: <strong>{c.me.handle}</strong></div>"
        html_output += f"<div>DID: <code>{c.me.did}</code></div>"
        
        # MARCADOR PARA O DEBUG-TOOL.PHP LER
        html_output += "<!-- BSKY_STATUS: CONNECTED -->"
        
    except Exception as e:
        html_output += f"<div>Status: <span class='status-err'>FAILED TO CONNECT</span></div>"
        html_output += f"<div>Error: {str(e)}</div>"
        html_output += "<!-- BSKY_STATUS: FAILED -->"
    html_output += "</div>"
    
    # 1.7 Inspeção do DID Document (Services)
    html_output += "<h2>1.7 Configuração de Rede (DID Document)</h2><div class='card'>"
    try:
        c = get_client()
        if c.me.did:
             # Resolver o DID Document publicamente
             # Usando o diretório PLC ou via client
             did_doc_url = f"https://plc.directory/{c.me.did}"
             html_output += f"<div><strong>DID:</strong> {c.me.did}</div>"
             html_output += f"<div style='margin-bottom:10px;'><a href='{did_doc_url}' target='_blank' style='color:#60a5fa'>Ver no PLC Directory ↗</a></div>"
             
             # Tentar fetch manual do JSON
             import requests
             res = requests.get(did_doc_url)
             if res.status_code == 200:
                 doc = res.json()
                 services = doc.get('service', [])
                 
                 found_labeler = False
                 html_output += "<table style='width:100%; font-size:0.9em; border-collapse:collapse;'>"
                 html_output += "<tr style='border-bottom:1px solid #334155; text-align:left;'><th>ID</th><th>Type</th><th>Endpoint</th></tr>"
                 
                 for s in services:
                     sid = s.get('id', '')
                     stype = s.get('type', '')
                     spt = s.get('serviceEndpoint', '')
                     
                     is_labeler = 'atproto_labeler' in sid or 'atproto_labeler' in stype
                     style = "color:#4ade80; font-weight:bold;" if is_labeler else ""
                     
                     if is_labeler: found_labeler = True
                     
                     html_output += f"<tr style='border-bottom:1px solid #334155;'>"
                     html_output += f"<td style='padding:5px; {style}'>{sid}</td>"
                     html_output += f"<td style='padding:5px;'>{stype}</td>"
                     html_output += f"<td style='padding:5px;'>{spt}</td>"
                     html_output += "</tr>"
                 html_output += "</table>"
                 
                 if found_labeler:
                      html_output += "<div style='margin-top:10px; color:#4ade80'>✅ Serviço de Labeler declarado.</div>"
                 else:
                      html_output += "<div style='margin-top:10px; color:#f87171'>❌ NENHUM serviço de Labeler (atproto_labeler) encontrado! O mundo não sabe que você é um labeler.</div>"
             else:
                 html_output += "<div>❌ Falha ao buscar DID Doc no PLC.</div>"
    except Exception as e:
        html_output += f"<div>Erro ao inspecionar DID Doc: {str(e)}</div>"
    html_output += "</div>"

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

    # 2.5 Inspeção Bruta (Visão do Python)
    html_output += f"<h2>2.5 Inspeção Bruta (user_badges)</h2><div class='card' style='background: #fffbeb; border-color: #fcd34d;'>"
    html_output += f"<p style='color:#b45309'>Consulta direta para DID: {TARGET_DID}</p>"
    
    try:
        raw_conn = get_db_connection()
        if raw_conn:
            raw_cursor = raw_conn.cursor(dictionary=True)
            
            # 1. Pegar User ID
            raw_cursor.execute("SELECT user_id, bluesky_handle FROM user_bluesky_profiles WHERE bluesky_did = %s", (TARGET_DID,))
            user_target = raw_cursor.fetchone()
            
            if user_target:
                html_output += f"<p><strong>Alvo:</strong> {user_target['bluesky_handle']} (ID: {user_target['user_id']})</p>"
                
                # 2. Query Bruta
                raw_cursor.execute("SELECT * FROM user_badges WHERE user_id = %s", (user_target['user_id'],))
                raw_rows = raw_cursor.fetchall()
                
                if raw_rows:
                    html_output += "<table style='width:100%; border-collapse: collapse; font-size: 0.9em; color:black; background:white;'>"
                    html_output += "<tr style='background: #fde68a;'><th>ID</th><th>Badge ID</th><th>Applied By</th><th>Date</th></tr>"
                    for r in raw_rows:
                        date_str = str(r['applied_at'])
                        html_output += "<tr style='border-bottom:1px solid #ddd;'>"
                        html_output += f"<td style='padding:4px;'>{r['id']}</td>"
                        html_output += f"<td style='padding:4px;'>{r['badge_id']}</td>"
                        html_output += f"<td style='padding:4px;'>{r['applied_by']}</td>"
                        html_output += f"<td style='padding:4px;'>{date_str}</td>"
                        html_output += "</tr>"
                    html_output += "</table>"
                else:
                    html_output += "<p style='color:red; font-weight:bold;'>ZERO registros encontrados na tabela 'user_badges'.</p>"
            else:
                 html_output += "<p>Usuário não encontrado para este DID.</p>"

            raw_cursor.close()
            raw_conn.close()
        else:
             html_output += "<div>Sem conexão DB.</div>"

    except Exception as e:
        html_output += f"<div class='status-err'>Erro Raw Check: {str(e)}</div>"
        
    html_output += "</div>"

    # 2.6 Inspeção de Definição de Badges (IDs 8 e 13)
    html_output += f"<h2>2.6 Definição de Badges (Tabela bluesky_badges)</h2><div class='card' style='background: #e0e7ff; border-color: #6366f1;'>"
    try:
        def_conn = get_db_connection()
        if def_conn:
            def_cursor = def_conn.cursor(dictionary=True)
            def_cursor.execute("SELECT id, badge_name, label_id, created_at FROM bluesky_badges WHERE id IN (8, 13)")
            def_rows = def_cursor.fetchall()
            
            if def_rows:
                html_output += "<table style='width:100%; border-collapse: collapse; font-size: 0.9em; color:black; background:white;'>"
                html_output += "<tr style='background: #c7d2fe;'><th>ID</th><th>Name</th><th>Label ID (val)</th><th>Created</th></tr>"
                for r in def_rows:
                    html_output += "<tr style='border-bottom:1px solid #ddd;'>"
                    html_output += f"<td style='padding:4px;'>{r['id']}</td>"
                    html_output += f"<td style='padding:4px;'>{r['badge_name']}</td>"
                    
                    lbl_val = r['label_id']
                    if not lbl_val:
                        lbl_val = "<span style='color:red; font-weight:bold;'>MISSING/NULL</span>"
                    else:
                        lbl_val = f"<code>{lbl_val}</code>"
                        
                    html_output += f"<td style='padding:4px;'>{lbl_val}</td>"
                    html_output += f"<td style='padding:4px;'>{r['created_at']}</td>"
                    html_output += "</tr>"
                html_output += "</table>"
            else:
                html_output += "<p>Nenhum badge encontrado com IDs 8 ou 13.</p>"
            
            def_cursor.close()
            def_conn.close()
    except Exception as e:
        html_output += f"<div>Erro Definition Check: {str(e)}</div>"
    html_output += "</div>"

    # 2.7 Definições de Serviço (Rede Bluesky)
    html_output += f"<h2>2.7 Definições de Serviço (Rede Bluesky)</h2><div class='card' style='background: #f0fdf4; border-color: #4ade80; color: #166534;'>"
    html_output += "<p>O que o mundo vê no seu <code>app.bsky.labeler.service</code> (rkey: self):</p>"
    
    try:
        c = get_client()
        # Fetch record 'self' da coleção app.bsky.labeler.service
        try:
            # Tentar importar de models se precisar, mas o response vem como objeto
            record_response = c.com.atproto.repo.get_record(
                params={
                    'repo': c.me.did,
                    'collection': 'app.bsky.labeler.service',
                    'rkey': 'self'
                }
            )
            
            # O 'value' contém o record real
            record_data = record_response.value
            
            # Verificar policies
            policies = getattr(record_data, 'policies', None)
            
            if policies:
                # O SDK retorna objetos, precisamos navegar
                lbl_defs = getattr(policies, 'label_value_definitions', [])
                lbl_vals = getattr(policies, 'label_values', [])
                
                html_output += f"<div>✅ <strong>Registro Encontrado!</strong></div>"
                html_output += f"<div>Definições (Definitions): <strong>{len(lbl_defs)}</strong></div>"
                html_output += f"<div>Valores Listados (Values): <strong>{len(lbl_vals)}</strong></div>"
                html_output += f"<div>Criado em: {getattr(record_data, 'created_at', '?')}</div>"
                
                # Listar primeiros 5 para conferência
                if lbl_defs:
                    html_output += "<div style='margin-top:10px; padding:10px; background:white; border-radius:4px; max-height:200px; overflow-y:auto; font-size:0.9em;'>"
                    html_output += "<strong>Amostra de Definições:</strong><br>"
                    for i, ld in enumerate(lbl_defs):
                        ident = getattr(ld, 'identifier', '?')
                        locales = getattr(ld, 'locales', [])
                        name = "?"
                        if locales and len(locales) > 0:
                            name = getattr(locales[0], 'name', '?')
                            
                        html_output += f"<code>{ident}</code> ({name})"
                        if i < len(lbl_defs) - 1: html_output += ", "
                    html_output += "</div>"
            else:
                 html_output += "<div>⚠️ Record existe mas 'policies' está vazio ou inválido.</div>"
                 html_output += f"<pre>{str(record_data)}</pre>"

        except Exception as  e_rec:
             html_output += f"<div>⚠️ Não foi possível ler o record 'self': {str(e_rec)}</div>"
             html_output += "<div>Provavelmente o setup inicial (setup_labeler.py) ainda não foi rodado ou o login falhou.</div>"

    except Exception as e:
        html_output += f"<div>Erro ao conectar para checar definições: {str(e)}</div>"
    
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
    
    
    # Abrir nova conexão específica para auditoria
    try:
        audit_conn = get_db_connection()
        if audit_conn:
            audit_cursor = audit_conn.cursor(dictionary=True)
            # Query já definida abaixo...
                
            audit_query = """
                SELECT 
                    ubp.user_id, 
                    ubp.bluesky_handle, 
                    ubp.bluesky_did,
                    GROUP_CONCAT(
                        CONCAT(
                            COALESCE(bb.badge_name, '?? BADGE DELETADO ??'), 
                            ' (ID: ', 
                            ub.badge_id, 
                            ') <span style="font-size:0.8em; color:#666">[RKey: ', 
                            COALESCE(ub.rkey, '-'), 
                            ']</span>'
                        ) SEPARATOR '<br>'
                    ) as badges_list
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
            audit_conn.close()
            
    except Exception as e:
        html_output += f"<div class='status-err'>Erro Audit: {str(e)}</div>"
    
    html_output += "</div>"

    # 4. Simulação Output JSON (ALL LABELS)
    html_output += "<h2>4. Simulação JSON Output (Todos os Usuários)</h2><div class='card'>"
    html_output += "<div><strong>Simulando resposta para TODOS os Badges ativos no sistema.</strong></div>"
    html_output += "<div style='margin-bottom:10px; color:#94a3b8; font-size:0.9em;'>Isto simula o que o Bluesky veria se pedisse 'tudo' (teoricamente) ou se consultasse cada DID individualmente.</div>"
    
    all_simulated_labels = []
    current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    labeler_did = "did:plc:placeholder_labeler_did"
    try:
        if client and hasattr(client, 'me'):
             labeler_did = client.me.did
    except:
        pass

    # Conexão para pegar TODOS os badges
    if conn:
        try:
            # Re-usar a conexão ou abrir nova se fechou (no bloco anterior fechou)
            if not conn.is_connected():
                conn = get_db_connection()
            
            sim_cursor = conn.cursor(dictionary=True)
            sim_query = """
                SELECT ubp.bluesky_did, bb.label_id, bb.badge_name, ub.rkey, ub.cid
                FROM user_badges ub
                JOIN bluesky_badges bb ON bb.id = ub.badge_id
                JOIN user_bluesky_profiles ubp ON ubp.user_id = ub.user_id
                ORDER BY ub.id DESC
                LIMIT 100
            """
            sim_cursor.execute(sim_query)
            all_badges = sim_cursor.fetchall()
            
            for b in all_badges:
                if b['bluesky_did'] and b['label_id']:
                    # Strict Label Def (Without _comment inside the object to be valid)
                    label_obj = {
                        "src": labeler_did,
                        "uri": b['bluesky_did'],
                        "val": b['label_id'],
                        "cts": current_time,
                        "ver": 1
                    }
                    if b.get('cid'):
                         label_obj['cid'] = b['cid'] # Simulation: we know the CID
                    
                    all_simulated_labels.append(label_obj)
            sim_cursor.close()
            conn.close()
        except Exception as e:
            html_output += f"<div class='status-err'>Erro ao buscar todos badges: {str(e)}</div>"

    
    json_output = {
        "cursor": "0",
        "labels": all_simulated_labels
    }
    
    html_output += f"<pre style='max-height:500px; overflow-y:scroll;'>{json.dumps(json_output, indent=2)}</pre>"
    
    if not all_simulated_labels:
        html_output += "<div class='status-err'>⚠️ ALERTA: Nenhum badge encontrado no sistema todo!</div>"
    else:
        html_output += f"<div class='status-ok'>✅ Total de Labels gerados: {len(all_simulated_labels)}</div>"
        
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
