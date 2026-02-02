from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os
import requests
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
            print(f"   Access JWT: {client.me.access_jwt[:20]}...")
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

def create_label_via_http(subject_did, label_value, negate=False):
    """
    Criar label usando API HTTP direta do AT Protocol
    Não depende dos métodos Python instáveis
    """
    c = get_client()
    
    # Endpoint para criar labels
    endpoint = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
    
    # Timestamp atual
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Payload do label
    record = {
        '$type': 'com.atproto.label.defs#label',
        'src': c.me.did,
        'uri': subject_did,
        'val': label_value,
        'neg': negate,
        'cts': now
    }
    
    # Request body
    body = {
        'repo': c.me.did,
        'collection': 'com.atproto.label.defs',
        'record': record
    }
    
    # Headers com autenticação
    headers = {
        'Authorization': f'Bearer {c.me.access_jwt}',
        'Content-Type': 'application/json'
    }
    
    print(f"📤 HTTP Request to: {endpoint}")
    print(f"   Body: {body}")
    
    # Fazer request
    response = requests.post(endpoint, json=body, headers=headers)
    
    print(f"📥 HTTP Response: {response.status_code}")
    print(f"   Body: {response.text}")
    
    if response.status_code in [200, 201]:
        return {
            'success': True,
            'data': response.json()
        }
    else:
        return {
            'success': False,
            'error': response.text,
            'status_code': response.status_code
        }

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '3.0.0',
        'method': 'HTTP Direct API',
        'labeler': os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/apply-badge', methods=['POST'])
def apply_badge():
    """
    Aplicar badge em um usuário
    Body: {
        "did": "did:plc:abc123xyz",
        "label": "arianators"
    }
    """
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        # Validar parâmetros
        if not user_did or not label_value:
            return jsonify({
                'success': False,
                'error': 'Missing parameters: did and label required',
                'received': data
            }), 400
        
        # Validar formato do DID
        if not user_did.startswith('did:'):
            return jsonify({
                'success': False,
                'error': 'Invalid DID format. Must start with "did:"',
                'received_did': user_did
            }), 400
        
        print(f"📝 Applying badge '{label_value}' to {user_did}")
        
        # Aplicar label via HTTP
        result = create_label_via_http(user_did, label_value, negate=False)
        
        if result['success']:
            print(f"✅ Badge applied successfully!")
            return jsonify({
                'success': True,
                'message': f'Badge "{label_value}" aplicado com sucesso',
                'user_did': user_did,
                'label': label_value,
                'data': result.get('data')
            })
        else:
            print(f"❌ Failed to apply badge: {result['error']}")
            return jsonify({
                'success': False,
                'error': f'Failed to apply badge: {result["error"]}',
                'status_code': result.get('status_code')
            }), 500
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    """
    Remover badge de um usuário
    Body: {
        "did": "did:plc:abc123xyz",
        "label": "arianators"
    }
    """
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({
                'success': False,
                'error': 'Missing parameters'
            }), 400
        
        print(f"🗑️ Removing badge '{label_value}' from {user_did}")
        
        # Remover label via HTTP (negate=True)
        result = create_label_via_http(user_did, label_value, negate=True)
        
        if result['success']:
            print(f"✅ Badge removed successfully!")
            return jsonify({
                'success': True,
                'message': 'Badge removido com sucesso'
            })
        else:
            print(f"❌ Failed to remove badge: {result['error']}")
            return jsonify({
                'success': False,
                'error': f'Failed to remove badge: {result["error"]}'
            }), 500
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/test-connection', methods=['GET'])
def test_connection():
    """Testar conexão com Bluesky"""
    try:
        c = get_client()
        return jsonify({
            'success': True,
            'message': 'Connected to Bluesky',
            'labeler': {
                'did': c.me.did,
                'handle': c.me.handle,
                'has_jwt': bool(c.me.access_jwt)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🚀 Starting Diva Labeler v3.0.0 on port {port}")
    print(f"   Method: HTTP Direct API")
    app.run(host='0.0.0.0', port=port)
