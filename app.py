"""
app.py
======
API REST pour le projet "Regulatory Analysis of Cosmetic Ingredients".

Endpoints :
    POST   /auth/token                  → obtenir un token d'authentification
    GET    /api/sephora/products        → liste des produits Sephora
    GET    /api/sephora/products/<id>   → un produit Sephora par ID
    GET    /api/sephora/brands          → Top marques par risque réglementaire
    GET    /api/sephora/by-type         → Agrégation par type de produit
    GET    /api/skincare/products       → liste des produits Skincare
    GET    /api/skincare/cmr            → produits Skincare avec ingrédients CMR
    GET    /api/comparaison             → jointure Sephora vs Skincare

Authentification :
    Toutes les routes /api/* nécessitent un header :
        Authorization: Bearer <token>
    Le token est obtenu via POST /auth/token avec les identifiants dans .env

Exécution :
    pip install -r requirements.txt
    python app.py
    → L'API sera disponible sur http://127.0.0.1:5000
    → La doc Swagger sur http://127.0.0.1:5000/swagger

Dépendances :
    flask, flask-cors, pymysql, sqlalchemy, python-dotenv, pyyaml
"""

import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

# ── Charger .env ──
load_dotenv()

# ── Config MySQL ──
MYSQL_USER     = os.getenv("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST     = os.getenv("MYSQL_HOST",     "localhost")
MYSQL_PORT     = os.getenv("MYSQL_PORT",     "3306")
MYSQL_DB       = os.getenv("MYSQL_DB",       "cosmetics_regulatory_db")

CONNECTION_STRING = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
engine = create_engine(CONNECTION_STRING, pool_pre_ping=True)

# ── Config Auth ──
# Identifiants pour obtenir un token (dans .env)
API_USERNAME = os.getenv("API_USERNAME", "admin")
API_PASSWORD = os.getenv("API_PASSWORD", "admin123")
TOKEN_EXPIRY_SECONDS = int(os.getenv("TOKEN_EXPIRY_SECONDS", "3600"))  # 1h par défaut

# Stockage en mémoire des tokens actifs : {token: expiry_timestamp}
active_tokens = {}

# ── Flask ──
app = Flask(__name__)
CORS(app)


# =============================================================
# MIDDLEWARE — Authentification par Bearer Token
# =============================================================
def require_auth(f):
    """Décorateur : vérifie la présence et la validité du token Bearer."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        # Vérifier le format "Bearer <token>"
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header manquant ou format incorrect. Utilisez : Bearer <token>"}), 401

        token = auth_header.split(" ")[1]

        # Vérifier que le token existe et n'est pas expiré
        if token not in active_tokens:
            return jsonify({"error": "Token invalide ou inexistant."}), 401

        if time.time() > active_tokens[token]:
            # Token expiré → on le supprime
            del active_tokens[token]
            return jsonify({"error": "Token expiré. Veuillez en obtenir un nouveau via POST /auth/token"}), 401

        return f(*args, **kwargs)
    return decorated


# =============================================================
# ROUTE — Obtenir un token d'authentification
# =============================================================
@app.route("/auth/token", methods=["POST"])
def get_token():
    """
    Génère un token Bearer valable TOKEN_EXPIRY_SECONDS.
    Body JSON attendu : {"username": "...", "password": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Body JSON requis avec username et password"}), 400

    username = data.get("username", "")
    password = data.get("password", "")

    if username != API_USERNAME or password != API_PASSWORD:
        return jsonify({"error": "Identifiants incorrects"}), 401

    # Générer un token aléatoire
    token = secrets.token_urlsafe(32)
    expiry = time.time() + TOKEN_EXPIRY_SECONDS
    active_tokens[token] = expiry

    return jsonify({
        "token": token,
        "expires_in": TOKEN_EXPIRY_SECONDS,
        "expires_at": datetime.fromtimestamp(expiry).isoformat()
    }), 200


# =============================================================
# ROUTES — Sephora Products
# =============================================================
@app.route("/api/sephora/products", methods=["GET"])
@require_auth
def get_sephora_products():
    """
    Liste des produits Sephora.
    Paramètres query string optionnels :
        - limit  : nombre max de résultats (défaut 50)
        - offset : décalage pour la pagination (défaut 0)
        - type   : filtrer par product_type
        - brand  : filtrer par brand_name (partiel, case-insensitive)
    """
    try:
        limit  = int(request.args.get("limit",  50))
        offset = int(request.args.get("offset", 0))
        product_type = request.args.get("type", None)
        brand = request.args.get("brand", None)

        # Construction dynamique de la requête
        query = """
            SELECT product_id, product_name, brand_name, product_type,
                   price_usd, rating, restricted_ingredient_count, cmr_count,
                   has_restricted_ingredient, has_cmr
            FROM sephora_products
            WHERE 1=1
        """
        params = {}

        if product_type:
            query += " AND product_type = :product_type"
            params["product_type"] = product_type

        if brand:
            query += " AND brand_name LIKE :brand"
            params["brand"] = f"%{brand}%"

        query += " ORDER BY brand_name ASC, product_name ASC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows), "limit": limit, "offset": offset}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sephora/products/<product_id>", methods=["GET"])
@require_auth
def get_sephora_product_by_id(product_id):
    """Retourne un seul produit Sephora par son product_id."""
    try:
        query = """
            SELECT product_id, product_name, brand_name, product_type,
                   price_usd, rating, restricted_ingredient_count, cmr_count,
                   has_restricted_ingredient, has_cmr
            FROM sephora_products
            WHERE product_id = :product_id
        """
        with engine.connect() as conn:
            result = conn.execute(text(query), {"product_id": product_id})
            row = result.fetchone()

        if not row:
            return jsonify({"error": f"Produit {product_id} introuvable"}), 404

        return jsonify({"data": dict(row._mapping)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sephora/brands", methods=["GET"])
@require_auth
def get_sephora_brands():
    """Top marques par nombre de produits avec ingrédients restreints."""
    try:
        limit = int(request.args.get("limit", 10))

        query = """
            SELECT
                brand_name,
                COUNT(*)                          AS total_produits,
                SUM(has_restricted_ingredient)    AS nb_produits_restreints,
                SUM(has_cmr)                      AS nb_produits_cmr,
                ROUND(AVG(price_usd), 2)          AS prix_moyen
            FROM sephora_products
            GROUP BY brand_name
            HAVING SUM(has_restricted_ingredient) > 0
            ORDER BY nb_produits_restreints DESC
            LIMIT :limit
        """
        with engine.connect() as conn:
            result = conn.execute(text(query), {"limit": limit})
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sephora/by-type", methods=["GET"])
@require_auth
def get_sephora_by_type():
    """Agrégation par type de produit : pourcentages de risque, moyennes."""
    try:
        query = """
            SELECT
                product_type,
                COUNT(*)                                                   AS total_produits,
                ROUND(AVG(restricted_ingredient_count), 2)                 AS moy_ingredients_restreints,
                SUM(has_restricted_ingredient)                             AS nb_produits_restreints,
                SUM(has_cmr)                                               AS nb_produits_cmr,
                ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1)  AS pct_restreints,
                ROUND(SUM(has_cmr) / COUNT(*) * 100, 1)                    AS pct_cmr
            FROM sephora_products
            GROUP BY product_type
            HAVING COUNT(*) > 10
            ORDER BY pct_restreints DESC
        """
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================
# ROUTES — Skincare Products
# =============================================================
@app.route("/api/skincare/products", methods=["GET"])
@require_auth
def get_skincare_products():
    """
    Liste des produits Skincare.
    Paramètres optionnels : limit, offset, type, brand.
    """
    try:
        limit  = int(request.args.get("limit",  50))
        offset = int(request.args.get("offset", 0))
        product_type = request.args.get("type", None)
        brand = request.args.get("brand", None)

        query = """
            SELECT brand, product_name, product_type, price, rating,
                   restricted_ingredient_count, cmr_count,
                   has_restricted_ingredient, has_cmr
            FROM skincare_products
            WHERE 1=1
        """
        params = {}

        if product_type:
            query += " AND product_type = :product_type"
            params["product_type"] = product_type

        if brand:
            query += " AND brand LIKE :brand"
            params["brand"] = f"%{brand}%"

        query += " ORDER BY brand ASC, product_name ASC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows), "limit": limit, "offset": offset}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/skincare/cmr", methods=["GET"])
@require_auth
def get_skincare_cmr():
    """Produits Skincare contenant des ingrédients CMR, triés par prix."""
    try:
        query = """
            SELECT brand, product_name, product_type, price, rating,
                   restricted_ingredient_count, cmr_count
            FROM skincare_products
            WHERE has_cmr = 1
            ORDER BY price DESC
        """
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================
# ROUTE — Comparaison Sephora vs Skincare (jointure)
# =============================================================
@app.route("/api/comparaison", methods=["GET"])
@require_auth
def get_comparaison():
    """
    Jointure Sephora vs Skincare.
    Les deux tables ont des catégories différentes :
        Sephora   → Skincare, Hair, Makeup, Fragrance, ...
        Skincare  → Moisturizer, Cleanser, Treatment, Eye Cream, Face Mask, Sun Protect
    On utilise un CASE WHEN pour mapper les sous-catégories Skincare
    vers les catégories larges de Sephora avant de faire la jointure.
    """
    try:
        query = """
            SELECT
                s.product_type                  AS categorie,
                s.total_sephora,
                s.pct_restreints_sephora,
                s.prix_moyen_sephora,
                sk.total_skincare,
                sk.pct_restreints_skincare,
                sk.prix_moyen_skincare
            FROM (
                SELECT product_type,
                       COUNT(*) AS total_sephora,
                       ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1) AS pct_restreints_sephora,
                       ROUND(AVG(price_usd), 2) AS prix_moyen_sephora
                FROM sephora_products
                GROUP BY product_type
            ) s
            INNER JOIN (
                SELECT
                    CASE
                        WHEN product_type IN ('Moisturizer','Cleanser','Treatment','Eye Cream','Face Mask','Sun Protect')
                            THEN 'Skincare'
                        ELSE product_type
                    END AS product_type,
                    COUNT(*) AS total_skincare,
                    ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1) AS pct_restreints_skincare,
                    ROUND(AVG(price), 2) AS prix_moyen_skincare
                FROM skincare_products
                GROUP BY CASE
                    WHEN product_type IN ('Moisturizer','Cleanser','Treatment','Eye Cream','Face Mask','Sun Protect')
                        THEN 'Skincare'
                    ELSE product_type
                END
            ) sk
            ON s.product_type = sk.product_type
            ORDER BY s.pct_restreints_sephora DESC
        """
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

        return jsonify({"data": rows, "count": len(rows)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================
# ROUTE — Documentation Swagger (OpenAPI)
# =============================================================
@app.route("/swagger", methods=["GET"])
def swagger_ui():
    """Sert la page Swagger UI pour la documentation de l'API."""
    return send_from_directory(Path(__file__).resolve().parent, "swagger.html")


# =============================================================
# POINT D'ENTRÉE
# =============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  API Cosmetics Regulatory — démarrage")
    print("  http://127.0.0.1:5000")
    print("  Doc : http://127.0.0.1:5000/swagger")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
