from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
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

def emit_badge_event(user_did, badge_name, negate=False):
    """
    Função de alto nível para emitir eventos de moderação (Labels)
    Usa 'emit_moderation_event' compatível com atproto 0.0.65+
    
    - negate=False: ADICIONA o badge (createLabelVals=[badge])
    - negate=True: REMOVE o badge (negateLabelVals=[badge])
    """
    c = get_client()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # 1. Definir o que será criado e o que será negado
    create_vals = []
    negate_vals = []
    
    if negate:
        negate_vals = [badge_name]
        action_name = "REMOVING (NEGATE)"
    else:
        create_vals = [badge_name]
        action_name = "ADDING (CREATE)"

    print(f"🔄 {action_name} BADGE '{badge_name}' PARA {user_did}")
    
    # 2. Montar o payload do evento manual
    event_data = {
        "event": {
            "$type": "com.atproto.admin.defs#modEventLabel",
            "createLabelVals": create_vals,
            "negateLabelVals": negate_vals,
            "comment": "Changed via Diva Labeler API"
        },
        "subject": {
            "$type": "com.atproto.admin.defs#repoRef",
            "did": user_did
        },
        "createdBy": c.me.did,
        "createdAt": now
    }

    try:
        # 3. Enviar evento
        print(f"📤 Sending moderation event...")
        response = c.com.atproto.admin.emit_moderation_event(data=event_data)
        
        print(f"✅ Success: {response}")
        return {
            "success": True,
            "data": str(response)
        }
        
    except Exception as e:
        print(f"❌ Error in emit_moderation_event: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '3.4.0',
        'method': 'emit_moderation_event (0.0.65+ Compliant)',
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
        
        if not user_did.startswith('did:'):
            return jsonify({'success': False, 'error': 'Invalid DID format'}), 400
            
        print(f"\n{'='*60}\n📝 APPLYING BADGE\n   User: {user_did}\n   Badge: {label_value}\n{'='*60}\n")
        
        # negate=False -> ADICIONAR
        result = emit_badge_event(user_did, label_value, negate=False)
        
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
        result = emit_badge_event(user_did, label_value, negate=True)
        
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
    print(f"🚀 DIVA LABELER v3.4.0")
    print(f"   Port: {port}")
    print(f"   Method: emit_moderation_event")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port)
