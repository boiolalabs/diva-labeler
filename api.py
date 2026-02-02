# ============================================================================
# ROTA QUE FALTAVA: ATENDER O TELEFONE DO BLUESKY (LEITURA)
# ============================================================================
@app.route('/xrpc/com.atproto.label.queryLabels', methods=['GET'])
def query_labels():
    uri_patterns = request.args.getlist('uriPatterns')
    labels = []
    
    # Tenta pegar DID do labeler
    try:
        c = get_client()
        my_did = c.me.did
    except:
        my_did = "did:plc:bmx5j2ukbbixbn4lo5itsf5v" # Fallback DID

    conn = get_db_connection()
    if not conn:
        return jsonify({"cursor": "0", "labels": []})

    try:
        cursor = conn.cursor(dictionary=True)
        
        for pattern in uri_patterns:
            if pattern.startswith('did:'):
                # A MESMA QUERY PODEROSA QUE USA AS 3 TABELAS
                query = """
                    SELECT bb.label_id, ub.created_at
                    FROM user_badges ub
                    JOIN bluesky_badges bb ON ub.badge_id = bb.id
                    JOIN user_bluesky_profiles ubp ON ub.user_id = ubp.user_id
                    WHERE ubp.bluesky_did = %s
                """
                
                cursor.execute(query, (pattern,))
                results = cursor.fetchall()
                
                for row in results:
                    cts = datetime.now(timezone.utc).isoformat()
                    if row.get('created_at'):
                        try:
                            # Tenta converter se for objeto datetime
                            cts = row['created_at'].isoformat() + "Z"
                        except:
                            # Se já for string
                            cts = str(row['created_at'])
                    
                    labels.append({
                        "src": my_did,
                        "uri": pattern,
                        "val": row['label_id'],
                        "cts": cts,
                        "ver": 1
                    })
        
        cursor.close()
        conn.close()
    
    except Exception as e:
        print(f"❌ Erro na Query de Leitura: {e}")
        if conn and conn.is_connected(): conn.close()

    return jsonify({"cursor": "0", "labels": labels})
