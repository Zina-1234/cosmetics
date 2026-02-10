-- =============================================================
-- queries.sql
-- Requêtes SQL d'extraction de données
-- Projet : Regulatory Analysis of Cosmetic Ingredients
-- Base de données : cosmetics_regulatory_db (MySQL)
-- =============================================================
-- Tables disponibles :
--   sephora_products   (7 380 lignes)
--   skincare_products  (1 352 lignes)
-- =============================================================


-- -------------------------------------------------------------
-- Q1. EXTRACTION DE BASE — tous les produits Sephora
-- -------------------------------------------------------------
-- Objectif   : récupérer l'ensemble du catalogue avec un tri
--              par marque puis par nom pour un parcours lisible.
-- Optimisation : INDEX sur brand_name si la table est grande ;
--               ici on limite à 100 lignes pour un premier regard.
-- -------------------------------------------------------------
SELECT
    product_id,
    product_name,
    brand_name,
    product_type,
    price_usd,
    rating
FROM sephora_products
ORDER BY brand_name ASC, product_name ASC
LIMIT 100;


-- -------------------------------------------------------------
-- Q2. FILTRAGE — produits contenant au moins un ingrédient
--     réglementairement restreint
-- -------------------------------------------------------------
-- Objectif    : identifier les produits à risque réglementaire.
-- Condition   : has_restricted_ingredient = 1
-- Tri         : par nombre d'ingrédients restreints DESC pour
--               mettre les plus risqués en tête.
-- Optimisation: le filtre sur une colonne booléenne (0/1) est
--               très rapide ; un INDEX sur has_restricted_ingredient
--               accélère encore la requête sur grande volume.
-- -------------------------------------------------------------
SELECT
    product_id,
    product_name,
    brand_name,
    product_type,
    price_usd,
    rating,
    restricted_ingredient_count,
    cmr_count
FROM sephora_products
WHERE has_restricted_ingredient = 1
ORDER BY restricted_ingredient_count DESC
LIMIT 50;


-- -------------------------------------------------------------
-- Q3. FILTRAGE MULTICRITÈRES — produits à risque élevé
-- -------------------------------------------------------------
-- Objectif    : combiner plusieurs conditions pour cibler les
--               produits les plus problématiques :
--                 • au moins 1 ingrédient CMR
--                 • prix > 50 $ (segment premium)
--                 • rating connu (pas NULL)
-- Condition   : AND entre les trois critères → intersection
-- Tri         : cmr_count DESC puis price DESC
-- -------------------------------------------------------------
SELECT
    product_id,
    product_name,
    brand_name,
    product_type,
    price_usd,
    rating,
    restricted_ingredient_count,
    cmr_count
FROM sephora_products
WHERE has_cmr = 1
  AND price_usd > 50
  AND rating IS NOT NULL
ORDER BY cmr_count DESC, price_usd DESC;


-- -------------------------------------------------------------
-- Q4. AGRÉGATION — nombre de produits et risque moyen par
--     type de produit (Sephora)
-- -------------------------------------------------------------
-- Objectif     : produire un résumé par catégorie pour le
--                tableau de bord.
-- GROUP BY     : product_type
-- Fonctions    : COUNT, AVG, SUM, MAX pour synthétiser chaque groupe
-- HAVING       : on n'affiche que les catégories avec > 10 produits
--               pour éviter les résultats non significatifs.
-- Optimisation : GROUP BY sur une colonne de faible cardinalité
--               (7 catégories) → très rapide même sans index.
-- -------------------------------------------------------------
SELECT
    product_type,
    COUNT(*)                                          AS total_produits,
    ROUND(AVG(restricted_ingredient_count), 2)        AS moy_ingredients_restreints,
    ROUND(AVG(cmr_count), 2)                          AS moy_cmr,
    SUM(has_restricted_ingredient)                    AS nb_produits_restreints,
    SUM(has_cmr)                                      AS nb_produits_cmr,
    ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1) AS pct_restreints,
    ROUND(SUM(has_cmr) / COUNT(*) * 100, 1)           AS pct_cmr,
    MAX(restricted_ingredient_count)                  AS max_ingredients_restreints
FROM sephora_products
GROUP BY product_type
HAVING COUNT(*) > 10
ORDER BY pct_restreints DESC;


-- -------------------------------------------------------------
-- Q5. AGRÉGATION — Top 10 marques par nombre de produits avec
--     ingrédients restreints
-- -------------------------------------------------------------
-- Objectif     : identifier les marques qui proposent le plus
--                de produits à risque réglementaire.
-- GROUP BY     : brand_name
-- Tri          : nb_produits_restreints DESC, puis total DESC
-- LIMIT        : on prend les 10 premières marques seulement.
-- -------------------------------------------------------------
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
LIMIT 10;


-- -------------------------------------------------------------
-- Q6. JOINTURE — comparaison Sephora vs Skincare sur les
--     types de produits communs
-- -------------------------------------------------------------
-- Objectif    : comparer les deux catalogues côte à côte sur
--               les mêmes types de produits.
-- Jointure    : INNER JOIN sur product_type pour ne garder que
--               les types présents dans les DEUX tables.
-- Sous-requêtes : on agrège d'abord chaque table séparément,
--                 puis on joint les résumés. C'est plus rapide
--                 qu'un GROUP BY sur la jointure complète car
--                 les sous-requêtes réduisent le volume avant
--                 le join.
-- Alias       : s = Sephora, sk = Skincare
-- -------------------------------------------------------------
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
        COUNT(*)                                              AS total_sephora,
        ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1) AS pct_restreints_sephora,
        ROUND(AVG(price_usd), 2)                              AS prix_moyen_sephora
    FROM sephora_products
    GROUP BY product_type
) s
INNER JOIN (
    SELECT
        product_type,
        COUNT(*)                                              AS total_skincare,
        ROUND(SUM(has_restricted_ingredient) / COUNT(*) * 100, 1) AS pct_restreints_skincare,
        ROUND(AVG(price), 2)                                  AS prix_moyen_skincare
    FROM skincare_products
    GROUP BY product_type
) sk
ON s.product_type = sk.product_type
ORDER BY s.pct_restreints_sephora DESC;


-- -------------------------------------------------------------
-- Q7. SOUS-REQUÊTE — produits dont le nombre d'ingrédients
--     restreints dépasse la moyenne globale
-- -------------------------------------------------------------
-- Objectif     : repérer les produits "au-dessus de la moyenne"
--                en termes de risque.
-- Sous-requête : AVG(restricted_ingredient_count) calculée une
--                seule fois dans le WHERE. MySQL optimise ça en
--                la calculant avant de scanner la table.
-- Condition    : strictement supérieur à la moyenne (>)
-- -------------------------------------------------------------
SELECT
    product_id,
    product_name,
    brand_name,
    product_type,
    restricted_ingredient_count,
    cmr_count
FROM sephora_products
WHERE restricted_ingredient_count > (
    SELECT AVG(restricted_ingredient_count)
    FROM sephora_products
)
ORDER BY restricted_ingredient_count DESC
LIMIT 30;


-- -------------------------------------------------------------
-- Q8. EXTRACTION SKINCARE — produits avec ingrédients CMR
--     triés par prix
-- -------------------------------------------------------------
-- Objectif    : même logique que Q2 mais appliquée à la table
--               skincare_products, pour vérifier la cohérence
--               entre les deux sources.
-- Condition   : has_cmr = 1
-- Tri         : price DESC pour voir les produits premium en tête
-- -------------------------------------------------------------
SELECT
    brand,
    product_name,
    product_type,
    price,
    rating,
    restricted_ingredient_count,
    cmr_count
FROM skincare_products
WHERE has_cmr = 1
ORDER BY price DESC;
