"""
run_queries.py
==============
Exécute les 8 requêtes SQL depuis Python (notebook ou ligne de commande).
Chaque requête retourne un DataFrame qu'on affiche et qu'on sauvegarde en CSV.

Exécution dans Jupyter : copier les cellules ci-dessous.
Exécution en ligne de commande : python run_queries.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

# ── Configuration ──
load_dotenv()

MYSQL_USER     = os.getenv("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST     = os.getenv("MYSQL_HOST",     "localhost")
MYSQL_PORT     = os.getenv("MYSQL_PORT",     "3306")
MYSQL_DB       = os.getenv("MYSQL_DB",       "cosmetics_regulatory_db")

CONNECTION_STRING = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"

OUTPUT_DIR = Path.cwd() / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Connexion ──
engine = create_engine(CONNECTION_STRING)


# ─────────────────────────────────────────────
# Q1 — Extraction de base (tous les produits Sephora)
# ─────────────────────────────────────────────
q1 = text("""
    SELECT product_id, product_name, brand_name, product_type, price_usd, rating
    FROM sephora_products
    ORDER BY brand_name ASC, product_name ASC
    LIMIT 100
""")
df_q1 = pd.read_sql(q1, engine)
df_q1.to_csv(OUTPUT_DIR / "q1_sephora_base.csv", index=False)
print("Q1 — Extraction de base :", df_q1.shape)
df_q1.head()


# ─────────────────────────────────────────────
# Q2 — Produits avec ingrédients restreints
# ─────────────────────────────────────────────
q2 = text("""
    SELECT product_id, product_name, brand_name, product_type,
           price_usd, rating, restricted_ingredient_count, cmr_count
    FROM sephora_products
    WHERE has_restricted_ingredient = 1
    ORDER BY restricted_ingredient_count DESC
    LIMIT 50
""")
df_q2 = pd.read_sql(q2, engine)
df_q2.to_csv(OUTPUT_DIR / "q2_produits_restreints.csv", index=False)
print("Q2 — Produits restreints :", df_q2.shape)
df_q2.head()


# ─────────────────────────────────────────────
# Q3 — Filtrage multicritères (CMR + premium + rating)
# ─────────────────────────────────────────────
q3 = text("""
    SELECT product_id, product_name, brand_name, product_type,
           price_usd, rating, restricted_ingredient_count, cmr_count
    FROM sephora_products
    WHERE has_cmr = 1
      AND price_usd > 50
      AND rating IS NOT NULL
    ORDER BY cmr_count DESC, price_usd DESC
""")
df_q3 = pd.read_sql(q3, engine)
df_q3.to_csv(OUTPUT_DIR / "q3_produits_risque_eleve.csv", index=False)
print("Q3 — Risque élevé (CMR + premium) :", df_q3.shape)
df_q3.head()


# ─────────────────────────────────────────────
# Q4 — Agrégation par type de produit
# ─────────────────────────────────────────────
q4 = text("""
    SELECT
        product_type,
        COUNT(*)                                                   AS total_produits,
        ROUND(AVG(restricted_ingredient_count), 2)                 AS moy_ingredients_restreints,
        ROUND(AVG(cmr_count), 2)                                   AS moy_cmr,
        SUM(has_restricted_ingredient)                             AS nb_produits_restreints,
        SUM(has_cmr)                                               AS nb_produits_cmr,
        ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1)  AS pct_restreints,
        ROUND(SUM(has_cmr) / COUNT(*) * 100, 1)                    AS pct_cmr,
        MAX(restricted_ingredient_count)                           AS max_ingredients_restreints
    FROM sephora_products
    GROUP BY product_type
    HAVING COUNT(*) > 10
    ORDER BY pct_restreints DESC
""")
df_q4 = pd.read_sql(q4, engine)
df_q4.to_csv(OUTPUT_DIR / "q4_aggregation_par_type.csv", index=False)
print("Q4 — Agrégation par type :", df_q4.shape)
df_q4


# ─────────────────────────────────────────────
# Q5 — Top 10 marques par produits restreints
# ─────────────────────────────────────────────
q5 = text("""
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
    LIMIT 10
""")
df_q5 = pd.read_sql(q5, engine)
df_q5.to_csv(OUTPUT_DIR / "q5_top10_marques.csv", index=False)
print("Q5 — Top 10 marques :", df_q5.shape)
df_q5


# ─────────────────────────────────────────────
# Q6 — Jointure Sephora vs Skincare
# ─────────────────────────────────────────────
q6 = text("""
    SELECT
        s.product_type,
        s.total_sephora,
        s.pct_restreints_sephora,
        s.prix_moyen_sephora,
        sk.total_skincare,
        sk.pct_restreints_skincare,
        sk.prix_moyen_skincare
    FROM (
        SELECT
            product_type,
            COUNT(*)                                                   AS total_sephora,
            ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1)  AS pct_restreints_sephora,
            ROUND(AVG(price_usd), 2)                                   AS prix_moyen_sephora
        FROM sephora_products
        GROUP BY product_type
    ) s
    INNER JOIN (
        SELECT
            product_type,
            COUNT(*)                                                   AS total_skincare,
            ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1)  AS pct_restreints_skincare,
            ROUND(AVG(price), 2)                                       AS prix_moyen_skincare
        FROM skincare_products
        GROUP BY product_type
    ) sk
    ON s.product_type = sk.product_type
    ORDER BY s.pct_restreints_sephora DESC
""")
df_q6 = pd.read_sql(q6, engine)
df_q6.to_csv(OUTPUT_DIR / "q6_jointure_sephora_skincare.csv", index=False)
print("Q6 — Jointure Sephora vs Skincare :", df_q6.shape)
df_q6


# ─────────────────────────────────────────────
# Q7 — Produits au-dessus de la moyenne de risque
# ─────────────────────────────────────────────
q7 = text("""
    SELECT product_id, product_name, brand_name, product_type,
           restricted_ingredient_count, cmr_count
    FROM sephora_products
    WHERE restricted_ingredient_count > (
        SELECT AVG(restricted_ingredient_count)
        FROM sephora_products
    )
    ORDER BY restricted_ingredient_count DESC
    LIMIT 30
""")
df_q7 = pd.read_sql(q7, engine)
df_q7.to_csv(OUTPUT_DIR / "q7_dessus_moyenne.csv", index=False)
print("Q7 — Au-dessus de la moyenne :", df_q7.shape)
df_q7.head()


# ─────────────────────────────────────────────
# Q8 — Skincare avec ingrédients CMR
# ─────────────────────────────────────────────
q8 = text("""
    SELECT brand, product_name, product_type, price, rating,
           restricted_ingredient_count, cmr_count
    FROM skincare_products
    WHERE has_cmr = 1
    ORDER BY price DESC
""")
df_q8 = pd.read_sql(q8, engine)
df_q8.to_csv(OUTPUT_DIR / "q8_skincare_cmr.csv", index=False)
print("Q8 — Skincare CMR :", df_q8.shape)
df_q8


# ── Nettoyage ──
engine.dispose()
print("\n✓ Les 8 requêtes ont été exécutées et sauvegardées dans data/processed/")
