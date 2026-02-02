from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURAÇÃO E CLIENTE BLUESKY
# ============================================================================

# Cliente Bluesky (singleton)
client = None

def get_client():
    """Retorna o cliente Bluesky autenticado, fazendo login se necessário."""
    global client
    
    if client is None:
        client = Client()
        handle = os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
        password = os.getenv('BLUESKY_PASSWORD')
        
        if not password:
            print("❌ ERRO: A variável de ambiente BLUESKY_PASSWORD não está definida.")
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

# ============================================================================
# LÓGICA DE APLICAÇÃO DE LABELS (REPO WRITER)
# ============================================================================

def apply_label_via_repo(subject_did, badge_name, negate=False):
    """
    Cria ou remove um label gravando DIRETAMENTE no Repositório do Labeler.
    (Self-Labeling / Repo Labeler)
    
    Collection: com.atproto.label.defs
    """
    c = get_client()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    action_name = "REMOVING (Negate)" if negate else "ADDING"
    
    # CORREÇÃO FEITA: Agora usa a variável correta 'subject_did' no print
    print(f"🔄 {action_name} BADGE '{badge_name}' PARA {subject_did}")

    # 1. Criar o objeto Label usando o Modelo Oficial
    label_record = models.ComAtprotoLabelDefsLabel(
        src=c.me.did,      # Quem está dando o label (nós)
        uri=subject_did,   # Quem está recebendo (o usuário)
        val=badge_name,    # O nome do badge (ex: 'maconheira')
        neg=negate,        # Se é true, anula um label anterior
        cts=now            # Timestamp
    )

    # 2. Montar o payload para o create_record
    data_payload = {
        "repo": c.me.did,
        "collection": "com.atproto.label.defs",
        "record": label_record
    }

    try:
        print(f"📤 Gravando registro no Repo do Labeler...")
        
        # 3. Enviar gravação
        response = c.com.atproto.repo.create_record(data=data_payload)
        
        print(f"✅ Sucesso! URI do registro: {response.uri}")
        return {
            "success": True,
            "data": str(response)
        }
        
    except Exception as e:
        print(f"❌ Erro ao gravar no repo: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ============================================================================
# ROTAS DA API (FLASK)
# ============================================================================

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '3.6.1',
        'method': 'Repo Writer (Direct Record)',
        'note': 'Writes to com.atproto.label.defs collection',
        'labeler': os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    try:
        data = request.json
        if not data:
             return jsonify({'success': False, 'error': 'No JSON body provided'}), 400

        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({'success': False, 'error': 'Missing parameters (did, label)'}), 400
        
        if not user_did.startswith('did:'):
            return jsonify({'success': False, 'error': 'Invalid DID format'}), 400
            
        print(f"\n{'='*60}\n📝 REQUEST: APPLY BADGE\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # negate=False -> ADICIONAR
        result = apply_label_via_repo(user_did, label_value, negate=False)
        
        status_code = 200 if result['success'] else 500
        return jsonify(result), status_code
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    try:
        data = request.json
        if not data:
             return jsonify({'success': False, 'error': 'No JSON body provided'}), 400

        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({'success': False, 'error': 'Missing parameters (did, label)'}), 400
            
        print(f"\n{'='*60}\n🗑️  REQUEST: REMOVE BADGE\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # negate=True -> REMOVER
        result = apply_label_via_repo(user_did, label_value, negate=True)
        
        status_code = 200 if result['success'] else 500
        return jsonify(result), status_code
        
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
