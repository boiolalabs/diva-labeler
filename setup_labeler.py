"""
Script para configurar perfil como Labeler no Bluesky
Busca badges DINAMICAMENTE do MySQL
Rode UMA VEZ para configurar o labeler
"""

from atproto import Client
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_badges_from_mysql():
    """Buscar badges ativos do MySQL"""
    
    try:
        print("🔌 Conectando no MySQL...")
        
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
        
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT 
                id,
                badge_name,
                artist_name,
                fanbase_name,
                description,
                emoji,
                image_url,
                image_local,
                use_emoji,
                label_id
            FROM bluesky_badges
            WHERE is_active = 1
            ORDER BY artist_name, fanbase_name
        """
        
        cursor.execute(query)
        badges = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        print(f"✅ Encontrados {len(badges)} badges ativos no banco")
        
        return badges
        
    except mysql.connector.Error as e:
        print(f"❌ Erro MySQL: {e}")
        return []
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return []

def setup_labeler():
    """Configurar perfil como labeler"""
    
    print("\n" + "="*60)
    print("🦋 SETUP DO BLUESKY LABELER - BOIO.LA")
    print("="*60 + "\n")
    
    # 1. Buscar badges do MySQL
    badges_data = get_badges_from_mysql()
    
    if not badges_data:
        print("❌ Nenhum badge encontrado! Verifique:")
        print("  - Credenciais do MySQL")
        print("  - Tabela bluesky_badges existe")
        print("  - Há badges com is_active = 1")
        return
    
    # 2. Login no Bluesky
    handle = os.getenv('BLUESKY_HANDLE', 'labeler.boio.la')
    password = os.getenv('BLUESKY_PASSWORD')
    
    if not password:
        print("❌ BLUESKY_PASSWORD não configurado!")
        return
    
    print(f"\n🔐 Fazendo login no Bluesky como: {handle}")
    
    try:
        client = Client()
        client.login(handle, password)
        print(f"✅ Login bem-sucedido!")
        print(f"   DID: {client.me.did}")
        print(f"   Handle: {client.me.handle}")
    except Exception as e:
        print(f"❌ Erro no login: {e}")
        return
    
    # 3. Preparar labels
    print(f"\n📝 Preparando {len(badges_data)} labels...")
    
    label_definitions = []
    
    for badge in badges_data:
        # Decidir qual visual usar
        if badge['use_emoji'] and badge['emoji']:
            visual = badge['emoji']
            visual_type = "emoji"
        elif badge['image_url']:
            visual = badge['image_url']
            visual_type = "image"
        elif badge['image_local']:
            # Converter path local para URL
            visual = f"https://boio.la{badge['image_local']}"
            visual_type = "image"
        else:
            visual = "🎵"  # Fallback
            visual_type = "emoji"
        
        label_def = {
            'identifier': badge['badge_name'],
            'severity': 'none',  # Não é moderação
            'blurs': 'none',
            'defaultSetting': 'hide',  # Usuário opt-in
            'adultOnly': False,
            'locales': [
                {
                    'lang': 'pt',
                    'name': badge['fanbase_name'],
                    'description': badge['description'] or f"Fã de {badge['artist_name']}"
                },
                {
                    'lang': 'en',
                    'name': badge['fanbase_name'],
                    'description': f"{badge['artist_name']} fan"
                }
            ]
        }
        
        label_definitions.append(label_def)
        
        print(f"  {visual} {badge['fanbase_name']:20} ({badge['badge_name']})")
    
    # 4. Configurar labeler no Bluesky
    print(f"\n🚀 Configurando labeler no Bluesky...")
    
    try:
        labeler_record = {
            '$type': 'app.bsky.labeler.service',
            'policies': {
                'labelValues': [label['identifier'] for label in label_definitions],
                'labelValueDefinitions': label_definitions
            },
            'createdAt': client._get_current_time_iso()
        }
        
        # Criar/atualizar registro do labeler
        client.com.atproto.repo.put_record(
            repo=client.me.did,
            collection='app.bsky.labeler.service',
            rkey='self',
            record=labeler_record
        )
        
        print("✅ Labeler configurado com sucesso!")
        
    except Exception as e:
        print(f"⚠️  Erro ao configurar: {e}")
        print("   (Isso é normal se já estiver configurado)")
    
    # 5. Resultado
    print("\n" + "="*60)
    print("🎉 CONFIGURAÇÃO COMPLETA!")
    print("="*60)
    print(f"\n🔗 Acesse seu labeler em:")
    print(f"   https://bsky.app/profile/{handle}/labeler")
    print(f"\n📊 Badges disponíveis: {len(badges_data)}")
    print(f"\n💡 Próximos passos:")
    print(f"   1. Acesse o link acima")
    print(f"   2. Usuários podem 'Subscribe' ao labeler")
    print(f"   3. Use a API para aplicar badges:")
    print(f"      POST /apply-badge")
    print(f"      {{ \"did\": \"...\", \"label\": \"badge_name\" }}")
    print()

if __name__ == '__main__':
    setup_labeler()
