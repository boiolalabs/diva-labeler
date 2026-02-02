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
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

def get_jwt_token(client):
    """
    Obter JWT token usando método interno da biblioteca
    """
    try:
        # SOLUÇÃO: Usar método interno _get_access_auth_headers()
        auth_headers = client._get_access_auth_headers()
        
        if auth_headers and 'Authorization' in auth_headers:
            # Extrair JWT do header "Bearer eyJ..."
            auth_value = auth_headers['Authorization']
            if auth_value.startswith('Bearer '):
                jwt = auth_value[7:]  # Remove "Bearer "
                print(f"   ✅ JWT: {jwt[:20]}...")
                return jwt
        
        print("   ⚠️  No JWT in auth headers")
        return None
        
    except Exception as e:
        print(f"   ❌ Error getting JWT: {e}")
        return None

def create_label_via_http(subject_did, label_value, negate=False):
    """
    Criar label usando API HTTP direta do AT Protocol
    """
    c = get_client()
    
    # Obter JWT usando método interno
    jwt = get_jwt_token(c)
    
    if not jwt:
        raise ValueError("Could not obtain JWT token from client")
    
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
        'Authorization': f'Bearer {jwt}',
        'Content-Type': 'application/json'
    }
    
    print(f"📤 HTTP Request to: {endpoint}")
    print(f"   Subject: {subject_did}")
    print(f"   Label: {label_value}")
    print(f"   Negate: {negate}")
    
    # Fazer request
    try:
        response = requests.post(endpoint, json=body, headers=headers, timeout=10)
        
        print(f"📥 HTTP Response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            print(f"   ✅ Success!")
            return {
                'success': True,
                'data': response.json()
            }
        else:
            print(f"   ❌ Error: {response.text}")
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '4.0.0',
        'method': 'Internal Auth Headers',
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
                'error': 'Missing parameters: did and label required'
            }), 400
        
        # Validar formato do DID
        if not user_did.startswith('did:'):
            return jsonify({
                'success': False,
                'error': 'Invalid DID format'
            }), 400
        
        print(f"\n{'='*60}")
        print(f"📝 APPLYING BADGE")
        print(f"   User: {user_did}")
        print(f"   Badge: {label_value}")
        print(f"{'='*60}\n")
        
        # Aplicar label via HTTP
        result = create_label_via_http(user_did, label_value, negate=False)
        
        if result['success']:
            print(f"\n✅ SUCCESS: Badge applied!\n")
            return jsonify({
                'success': True,
                'message': f'Badge "{label_value}" aplicado com sucesso',
                'user_did': user_did,
                'label': label_value
            })
        else:
            print(f"\n❌ FAILED: {result.get('error')}\n")
            return jsonify({
                'success': False,
                'error': f'Failed to apply badge: {result["error"]}'
            }), 500
        
    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}\n")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    """
    Remover badge de um usuário
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
        
        print(f"\n{'='*60}")
        print(f"🗑️  REMOVING BADGE")
        print(f"   User: {user_did}")
        print(f"   Badge: {label_value}")
        print(f"{'='*60}\n")
        
        result = create_label_via_http(user_did, label_value, negate=True)
        
        if result['success']:
            print(f"\n✅ SUCCESS: Badge removed!\n")
            return jsonify({
                'success': True,
                'message': 'Badge removido com sucesso'
            })
        else:
            print(f"\n❌ FAILED: {result.get('error')}\n")
            return jsonify({
                'success': False,
                'error': f'Failed to remove badge: {result["error"]}'
            }), 500
        
    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}\n")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/test-connection', methods=['GET'])
def test_connection():
    """Testar conexão e JWT"""
    try:
        c = get_client()
        jwt = get_jwt_token(c)
        
        return jsonify({
            'success': True,
            'message': 'Connected to Bluesky',
            'labeler': {
                'did': c.me.did,
                'handle': c.me.handle,
                'has_jwt': bool(jwt),
                'jwt_preview': jwt[:30] if jwt else None
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"\n{'='*60}")
    print(f"🚀 DIVA LABELER v4.0.0")
    print(f"   Method: Internal Auth Headers")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port)
