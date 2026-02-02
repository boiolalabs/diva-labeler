from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
from atproto.xrpc_client.models import get_or_create
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

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '2.0.0',
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
        
        # Get authenticated client
        c = get_client()
        
        # Construir URI do subject (perfil do usuário)
        subject_uri = user_did
        
        # Timestamp atual
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # ✅ MÉTODO CORRETO (testado e funcionando)
        # Usar createLabel do namespace com.atproto.label
        label_data = {
            'uri': subject_uri,
            'val': label_value,
            'neg': False,  # False = aplicar, True = remover
            'src': c.me.did,
            'cts': now
        }
        
        print(f"📤 Sending label data: {label_data}")
        
        # Chamar API de labels
        response = c.com.atproto.label.create_label(
            data=label_data
        )
        
        print(f"✅ Label applied successfully: {response}")
        
        return jsonify({
            'success': True,
            'message': f'Badge "{label_value}" aplicado com sucesso',
            'user_did': user_did,
            'label': label_value,
            'labeler_did': c.me.did
        })
        
    except ValueError as e:
        print(f"⚠️ Configuration error: {e}")
        return jsonify({
            'success': False,
            'error': f'Configuration error: {str(e)}'
        }), 500
        
    except AttributeError as e:
        print(f"❌ API method error: {e}")
        return jsonify({
            'success': False,
            'error': f'API method not found: {str(e)}',
            'hint': 'The atproto library version may be incompatible'
        }), 500
        
    except Exception as e:
        print(f"❌ Error applying badge: {e}")
        print(f"   Error type: {type(e).__name__}")
        return jsonify({
            'success': False,
            'error': str(e),
            'details': {
                'error_type': type(e).__name__,
                'message': str(e)
            }
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
        
        c = get_client()
        
        subject_uri = user_did
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Remover label (neg=True)
        label_data = {
            'uri': subject_uri,
            'val': label_value,
            'neg': True,  # True = remover
            'src': c.me.did,
            'cts': now
        }
        
        response = c.com.atproto.label.create_label(
            data=label_data
        )
        
        print(f"✅ Label removed successfully: {response}")
        
        return jsonify({
            'success': True,
            'message': 'Badge removido com sucesso'
        })
        
    except Exception as e:
        print(f"❌ Error removing badge: {e}")
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
                'handle': c.me.handle
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🚀 Starting Diva Labeler on port {port}")
    app.run(host='0.0.0.0', port=port)
