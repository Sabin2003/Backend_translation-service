from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import logging
import requests

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE = 'translations.db'
MODEL_TRANSLATION_ENDPOINT = 'URL_DE_VOTRE_MODELE_DE_TRADUCTION'  # À remplacer par l'URL réelle du modèle

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Ouvre une connexion à la base de données SQLite."""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

@app.route('/api/translate', methods=['POST', 'OPTIONS'])
def translate():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    try:
        data = request.json
        logger.info(f"Translation request: {data}")

        # Gestion des champs flexibles (snake_case et camelCase)
        source_lang = data.get('source_lang') or data.get('sourceLang', '').lower().strip()
        target_lang = data.get('target_lang') or data.get('targetLang', '').lower().strip()
        text = (data.get('text') or '').strip()

        # Validation des données
        if not all([source_lang, target_lang, text]):
            return jsonify({
                'error': 'Missing required fields',
                'details': {
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'text': bool(text)
                }
            }), 400

        # Recherche dans la base de données
        table_name = f"{source_lang}_{target_lang}"
        conn = get_db_connection()
        cursor = conn.cursor()

        # Vérifie si la table existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'error': 'Unsupported language pair',
                'supportedPairs': get_supported_pairs()
            }), 404

        # Recherche exacte insensible à la casse
        cursor.execute(f"SELECT target FROM {table_name} WHERE source = ? COLLATE NOCASE", (text,))
        if result := cursor.fetchone():
            conn.close()
            return jsonify({
                'originalText': text,
                'translation': result['target'],  # Notez la clé 'translation' ici
                'sourceLang': source_lang,
                'targetLang': target_lang,
                'matchType': 'exact',
                'source': 'database'
            })

        # Fallback to model translation
        if model_translation := get_model_translation(text, source_lang, target_lang):
            return jsonify({
                'originalText': text,
                'translation': model_translation,
                'sourceLang': source_lang,
                'targetLang': target_lang,
                'matchType': 'model',
                'source': 'translationModel'
            })

        return jsonify({
            'originalText': text,
            'translation': None,
            'message': 'No translation found',
            'sourceLang': source_lang,
            'targetLang': target_lang
        }), 404

    except Exception as e:
        logger.error(f"Translation error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

def get_model_translation(text, source_lang, target_lang):
    """Appelle un modèle externe de traduction."""
    try:
        if not MODEL_TRANSLATION_ENDPOINT or MODEL_TRANSLATION_ENDPOINT == 'URL_DE_VOTRE_MODELE_DE_TRADUCTION':
            logger.warning("Model translation endpoint is not configured.")
            return None
            
        response = requests.post(
            MODEL_TRANSLATION_ENDPOINT,
            json={
                'text': text,
                'source_lang': source_lang,
                'target_lang': target_lang
            },
            timeout=5
        )
        
        if response.status_code == 200:
            return response.json().get('translation')
        logger.error(f"Model translation failed with status {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Model translation error: {str(e)}")
        return None

def get_supported_pairs():
    """Retourne les paires de langues supportées."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        
        pairs = []
        for table in tables:
            name = table['name']
            if '_' in name:
                source, target = name.split('_')
                pairs.append(f"{source}-{target}")
        
        return pairs
    except Exception as e:
        logger.error(f"Error getting supported pairs: {str(e)}")
        return []

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
