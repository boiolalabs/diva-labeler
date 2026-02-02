from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client, models
import os

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
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise
    
    return client

@app.route('/')
def home():
    return jsonify({
        'status': 'healthy',
        'service': 'Diva Labeler',
        'version': '1.0.0'
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
                'error': 'Invalid DID format. Must start with "did:"'
            }), 400
        
        # Get authenticated client
        c = get_client()
        
        # Construir URI do perfil do usuário
        profile_uri = f'at://{user_did}/app.bsky.actor.profile/self'
        
        # ✅ MÉTODO CORRETO (atproto 0.0.65+)
        c.app.bsky.labeler.apply_labels(
            labels=[
                models.ComAtprotoLabelDefs.Label(
                    src=c.me.did,
                    uri=profile_uri,
                    val=label_value,
                    neg=False,
                    cts=c._get_current_time_iso()
                )
            ]
        )
        
        return jsonify({
            'success': True,
            'message': f'Badge "{label_value}" aplicado com sucesso',
            'user_did': user_did,
            'label': label_value
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Configuration error: {str(e)}'
        }), 500
        
    except Exception as e:
        print(f"❌ Error applying badge: {e}")
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
        
        c = get_client()
        
        profile_uri = f'at://{user_did}/app.bsky.actor.profile/self'
        
        # Remover label (neg=True)
        c.app.bsky.labeler.apply_labels(
            labels=[
                models.ComAtprotoLabelDefs.Label(
                    src=c.me.did,
                    uri=profile_uri,
                    val=label_value,
                    neg=True,
                    cts=c._get_current_time_iso()
                )
            ]
        )
        
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
