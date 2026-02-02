from flask import Flask, request, jsonify
from flask_cors import CORS
from atproto import Client
import os

app = Flask(__name__)
CORS(app)

# Login no Bluesky
client = None

def init_client():
    global client
    if client is None:
        client = Client()
        client.login(
            os.getenv('BLUESKY_HANDLE'),
            os.getenv('BLUESKY_PASSWORD')
        )
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
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({
                'success': False,
                'error': 'Missing parameters: did and label required'
            }), 400
        
        # Inicializar cliente
        c = init_client()
        
        # Aplicar label
        c.com.atproto.label.create_labels(
            repo=c.me.did,
            labels=[{
                'uri': f'at://{user_did}/app.bsky.actor.profile/self',
                'val': label_value,
                'neg': False,
                'cts': c._get_current_time_iso()
            }]
        )
        
        return jsonify({
            'success': True,
            'message': f'Badge {label_value} aplicado com sucesso'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/remove-badge', methods=['POST'])
def remove_badge():
    try:
        data = request.json
        user_did = data.get('did')
        label_value = data.get('label')
        
        if not user_did or not label_value:
            return jsonify({
                'success': False,
                'error': 'Missing parameters'
            }), 400
        
        c = init_client()
        
        # Remover label (negar)
        c.com.atproto.label.create_labels(
            repo=c.me.did,
            labels=[{
                'uri': f'at://{user_did}/app.bsky.actor.profile/self',
                'val': label_value,
                'neg': True,
                'cts': c._get_current_time_iso()
            }]
        )
        
        return jsonify({
            'success': True,
            'message': 'Badge removido com sucesso'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
