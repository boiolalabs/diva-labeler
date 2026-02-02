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
            
            # Testar acesso ao JWT
            jwt = get_jwt_token(client)
            if jwt:
                print(f"   JWT: {jwt[:20]}...")
            else:
                print("   ⚠️  JWT not found!")
                
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

def get_jwt_token(client):
    """
    Obter JWT token do client de forma segura
    Tenta múltiplos locais onde o JWT pode estar
    """
    # Tentar diferentes locais onde o JWT pode estar
    
    # Opção 1: session (mais comum)
    if hasattr(client, 'session') and client.session:
        if isinstance(client.session, dict):
            return client.session.get('accessJwt') or client.session.get('access_jwt')
        elif hasattr(client.session, 'access_jwt'):
            return client.session.access_jwt
        elif hasattr(client.session, 'accessJwt'):
            return client.session.accessJwt
    
    # Opção 2: atributo direto
    if hasattr(client, 'access_jwt'):
        return client.access_jwt
    
    if hasattr(client, '_access_jwt'):
        return client._access_jwt
    
    # Opção 3: dentro de _session
    if hasattr(client, '_session') and client._session:
        if isinstance(client._session, dict):
            return client._session.get('accessJwt') or client._session.get('access_jwt')
    
    # Opção 4: método de autenticação
    if hasattr(client, 'auth') and hasattr(client.auth, 'jwt'):
        return client.auth.jwt
    
    print("⚠️  Could not find JWT token in client object")
    print(f"   Available attributes: {dir(client)}")
    
    return None

def create_label_via_http(subject_did, label_value, negate=False):
    """
    Criar label usando API HTTP direta do AT Protocol
    """
    c = get_client()
    
    # Obter JWT
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
    print(f"   Repo: {c.me.did}")
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
        'version': '3.1.0',
        'method': 'HTTP Direct API with JWT Fix',
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
                'label': label_value,
                'data': result.get('data')
            })
        else:
            print(f"\n❌ FAILED: {result.get('error')}\n")
            return jsonify({
                'success': False,
                'error': f'Failed to apply badge: {result["error"]}',
                'status_code': result.get('status_code')
            }), 500
        
    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}\n")
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
        
        print(f"\n{'='*60}")
        print(f"🗑️  REMOVING BADGE")
        print(f"   User: {user_did}")
        print(f"   Badge: {label_value}")
        print(f"{'='*60}\n")
        
        # Remover label via HTTP (negate=True)
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
    """Testar conexão com Bluesky"""
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
                'jwt_preview': jwt[:20] if jwt else None
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
    print(f"🚀 DIVA LABELER v3.1.0")
    print(f"   Port: {port}")
    print(f"   Method: HTTP Direct API with JWT Fix")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port)
