from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import mysql.connector
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv(override=True)

app = Flask(__name__)
CORS(app) # Permite conexões externas

# Configurações do Banco
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )

@app.route('/')
def home():
    return """
    <h1>Diva Labeler API 💅</h1>
    <p>O servidor está online!</p>
    <p>Acesse <a href="/debug">/debug</a> para ver o diagnóstico.</p>
    """

@app.route('/debug')
def debug():
    """Rota de diagnóstico para verificar saúde do sistema"""
    status = {
        "env_vars": {},
        "database": {"status": "UNKNOWN", "message": ""},
        "integrity": {"did_found": False, "did": "did:plc:bmx5j2ukbbixbn4lo5itsf5v"}
    }
    
    # 1. Verificar Variáveis de Ambiente (Mascarando senhas)
    vars_to_check = ['DB_HOST', 'DB_USER', 'DB_NAME', 'BLUESKY_HANDLE', 'BLUESKY_PASSWORD']
    for var in vars_to_check:
        value = os.getenv(var)
        if var == 'BLUESKY_PASSWORD' or var == 'DB_PASSWORD':
            display = "******" if value else "MISSING"
        else:
            display = value if value else "MISSING"
        status["env_vars"][var] = display

    # 2. Testar Conexão MySQL
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        status["database"]["status"] = "CONNECTED"
        status["database"]["message"] = f"MySQL Version: {version[0]}"
        
        # 3. Testar Integridade (Verificar se o DID do labeler existe)
        target_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Seu DID Fixo
        
        # Tenta buscar na tabela de perfis
        cursor.execute(f"SELECT handle FROM user_bluesky_profiles WHERE did = '{target_did}'")
        user = cursor.fetchone()
        
        if user:
            status["integrity"]["did_found"] = True
            status["integrity"]["message"] = f"Usuário encontrado: {user[0]}"
        else:
            status["integrity"]["did_found"] = False
            status["integrity"]["message"] = "DID do Labeler não está na tabela 'user_bluesky_profiles'"
            
        conn.close()
        
    except Exception as e:
        status["database"]["status"] = "ERROR"
        status["database"]["message"] = str(e)

    # Gerar HTML Bonito para visualização
    html = f"""
    <html>
    <head>
        <title>Diagnóstico Diva Labeler</title>
        <style>
            body {{ font-family: sans-serif; padding: 20px; background: #f4f4f9; }}
            .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }}
            h1 {{ color: #333; border-bottom: 2px solid #6200ea; padding-bottom: 10px; }}
            .status {{ font-weight: bold; padding: 5px 10px; border-radius: 4px; display: inline-block; }}
            .ok {{ background: #e8f5e9; color: #2e7d32; }}
            .error {{ background: #ffebee; color: #c62828; }}
            pre {{ background: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🔍 Diva Labeler Diagnostic</h1>
            
            <h3>1. Variáveis de Ambiente</h3>
            <ul>
                {''.join([f"<li><b>{k}:</b> {v}</li>" for k,v in status['env_vars'].items()])}
            </ul>

            <h3>2. Conexão MySQL</h3>
            <div class="status {'ok' if status['database']['status'] == 'CONNECTED' else 'error'}">
                Status: {status['database']['status']}
            </div>
            <p>{status['database']['message']}</p>

            <h3>3. Integridade (DID Mestre)</h3>
            <div class="status {'ok' if status['integrity']['did_found'] else 'error'}">
                {status['integrity']['message']}
            </div>
            <p>DID Buscado: {status['integrity']['did']}</p>
        </div>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    # Porta padrão do Render é dada pela variável PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
