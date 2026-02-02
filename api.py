from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os
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
            print(f"   DID: {client.me.did}")
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

def create_label_native(subject_did, label_value, negate=False):
    """
    Criar label usando a função de alto nível emit_label (atproto 0.0.65+)
    Isso evita erros de tipagem manual ($type) e gerencia o neg=True corretamente.
    """
    c = get_client()
    
    # Timestamp atual
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    print(f"📤 ATProto Emit Label")
    print(f"   Subject: {subject_did}")
    print(f"   Label: {label_value}")
    print(f"   Negate: {negate}")
    
    try:
        # CHAMADA OFICIAL DA LIB PARA LABELS
        # A própria lib cuida da estrutura de dados e tipagem
        response = c.emit_label(
            subject=subject_did,
            val=label_value,
            neg=negate,
            created_at=now
        )
        
        print(f"   ✅ Success: {response}")
        return {
            'success': True,
            'data': str(response)
        }
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '3.3.0',
        'method': 'Native emit_label (Official Method)',
        'labeler': os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400
        
        # Validar formato do DID
        if not user_did.startswith('did:'):
            return jsonify({'success': False, 'error': 'Invalid DID format'}), 400
            
        print(f"\n{'='*60}\n📝 APPLYING BADGE (emit_label)\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        result = create_label_native(user_did, label_value, negate=False)
        
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
            
        print(f"\n{'='*60}\n🗑️  REMOVING BADGE (emit_label via neg=True)\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # Para remover, usamos neg=True
        result = create_label_native(user_did, label_value, negate=True)
        
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
            'message': 'Connected to Bluesky (Native Client)',
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
    print(f"🚀 DIVA LABELER v3.3.0")
    print(f"   Port: {port}")
    print(f"   Method: emit_label (Best Practice)")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port)
