"""
extract_data.py
===============
Script d'extraction de données pour le projet "Regulatory Analysis of Cosmetic Ingredients".

Sources d'extraction :
    1. Fichiers locaux       → COSING_Annex_III_v2.xls, product_info.csv, cosmetics.csv
    2. API REST              → Open Beauty Facts API (produits cosmétiques, format JSON)
    3. Web Scraping          → Page HTML Open Beauty Facts (même site, mais parsing HTML avec BeautifulSoup)
    4. Base de données MySQL → Tables sephora_products / skincare_products déjà importées

Exécution :
    python extract_data.py
    OU dans un notebook Jupyter : exécuter les cellules de haut en bas

Dépendances (voir requirements.txt) :
    pandas, openpyxl, xlrd, requests, beautifulsoup4, lxml, pymysql, sqlalchemy, python-dotenv
"""

# ─────────────────────────────────────────────
# 0. POINT DE LANCEMENT & INITIALISATION
# ─────────────────────────────────────────────
import sys
import os
import logging
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ── Charger les variables d'environnement (.env) ──
load_dotenv()

# ── Configuration des chemins ──
# Path.cwd() marche dans un notebook Jupyter ET en ligne de commande
BASE_DIR      = Path.cwd()
RAW_DIR       = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration du logging ──
LOG_FILE = BASE_DIR / "logs" / "extraction.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ── Lecture des paramètres depuis .env ──
MYSQL_USER     = os.getenv("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST     = os.getenv("MYSQL_HOST",     "localhost")
MYSQL_PORT     = os.getenv("MYSQL_PORT",     "3306")
MYSQL_DB       = os.getenv("MYSQL_DB",       "cosmetics_regulatory_db")

# Chemins des fichiers locaux
FILE_COSING   = os.getenv("FILE_COSING",   str(BASE_DIR / "data" / "raw" / "COSING_Annex_III_v2.xls"))
FILE_SEPHORA  = os.getenv("FILE_SEPHORA",  str(BASE_DIR / "data" / "raw" / "product_info.csv"))
FILE_SKINCARE = os.getenv("FILE_SKINCARE", str(BASE_DIR / "data" / "raw" / "cosmetics.csv"))

# URL pour l'API REST et le scraping
API_OPEN_BEAUTY_FACTS_URL      = "https://world.openfoodfacts.org/cgi/search.pl"
SCRAPING_WIKIPEDIA_COSM_URL    = "https://en.wikipedia.org/wiki/Ingredients_of_cosmetics"


# ─────────────────────────────────────────────
# 1. EXTRACTION DEPUIS LES FICHIERS LOCAUX
# ─────────────────────────────────────────────
def extract_from_files() -> dict[str, pd.DataFrame]:
    """
    Lit les trois fichiers de données brutes locaux.
    Retourne un dictionnaire {nom_source: DataFrame}.
    """
    logger.info("── Source 1 : Extraction depuis les fichiers locaux ──")
    results = {}

    # 1a. COSING (fichier Excel)
    try:
        logger.info(f"  Lecture de {FILE_COSING} ...")
        df = pd.read_excel(FILE_COSING, engine="xlrd")
        results["cosing"] = df
        logger.info(f"  ✓ COSING chargé : {df.shape[0]} lignes, {df.shape[1]} colonnes")
    except FileNotFoundError:
        logger.error(f"  ✗ Fichier introuvable : {FILE_COSING}")
        results["cosing"] = pd.DataFrame()
    except Exception as e:
        logger.error(f"  ✗ Erreur lors de la lecture COSING : {e}")
        results["cosing"] = pd.DataFrame()

    # 1b. SEPHORA (fichier CSV)
    try:
        logger.info(f"  Lecture de {FILE_SEPHORA} ...")
        df = pd.read_csv(FILE_SEPHORA)
        results["sephora"] = df
        logger.info(f"  ✓ SEPHORA chargé : {df.shape[0]} lignes, {df.shape[1]} colonnes")
    except FileNotFoundError:
        logger.error(f"  ✗ Fichier introuvable : {FILE_SEPHORA}")
        results["sephora"] = pd.DataFrame()
    except Exception as e:
        logger.error(f"  ✗ Erreur lors de la lecture SEPHORA : {e}")
        results["sephora"] = pd.DataFrame()

    # 1c. SKINCARE (fichier CSV)
    try:
        logger.info(f"  Lecture de {FILE_SKINCARE} ...")
        df = pd.read_csv(FILE_SKINCARE)
        results["skincare"] = df
        logger.info(f"  ✓ SKINCARE chargé : {df.shape[0]} lignes, {df.shape[1]} colonnes")
    except FileNotFoundError:
        logger.error(f"  ✗ Fichier introuvable : {FILE_SKINCARE}")
        results["skincare"] = pd.DataFrame()
    except Exception as e:
        logger.error(f"  ✗ Erreur lors de la lecture SKINCARE : {e}")
        results["skincare"] = pd.DataFrame()

    return results


# ─────────────────────────────────────────────
# 2. EXTRACTION VIA API REST (Open Beauty Facts — JSON)
# ─────────────────────────────────────────────
def extract_from_api(max_pages: int = 3) -> pd.DataFrame:
    """
    Appelle l'API Open Beauty Facts avec json=1 → on récupère du JSON directement.
    Paramètre :
        max_pages : nombre de pages de résultats à récupérer.
    Retourne un DataFrame avec les produits extraits.
    """
    logger.info("── Source 2 : Extraction via API REST (Open Beauty Facts — JSON) ──")

    all_products = []
    headers = {"User-Agent": "Cosmetics-Regulatory-Project/1.0 (educational)"}

    for page in range(1, max_pages + 1):
        try:
            logger.info(f"  Requête API page {page}/{max_pages} ...")
            params = {
                "search_terms": "cosmetics",
                "search_simple": "1",
                "action": "process",
                "json": "1",            # ← on demande du JSON
                "page": page,
                "count": 25
            }
            response = requests.get(
                API_OPEN_BEAUTY_FACTS_URL,
                params=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            products = data.get("products", [])

            if not products:
                logger.info(f"  Aucun produit sur la page {page}, arrêt de la pagination.")
                break

            for product in products:
                all_products.append({
                    "product_name":     product.get("product_name", ""),
                    "brand":            product.get("brands", ""),
                    "ingredients_text": product.get("ingredients_text", ""),
                    "categories":       product.get("categories", ""),
                    "country":          product.get("countries", ""),
                    "barcode":          product.get("code", ""),
                    "source":           "open_beauty_facts_api"
                })

            logger.info(f"  ✓ Page {page} : {len(products)} produits récupérés")

        except requests.exceptions.Timeout:
            logger.warning(f"  ⚠ Timeout sur la page {page} — on continue avec la suivante.")
            continue
        except requests.exceptions.HTTPError as e:
            logger.error(f"  ✗ Erreur HTTP page {page} : {e}")
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"  ✗ Erreur réseau page {page} : {e}")
            break
        except (ValueError, KeyError) as e:
            logger.error(f"  ✗ Erreur de parsing JSON page {page} : {e}")
            continue

    df = pd.DataFrame(all_products)
    logger.info(f"  ✓ API REST — total : {len(df)} produits extraits")
    return df


# ─────────────────────────────────────────────
# 3. EXTRACTION PAR WEB SCRAPING (Wikipedia — Ingredients of cosmetics)
# ─────────────────────────────────────────────
def extract_by_scraping() -> pd.DataFrame:
    """
    Scrape la page Wikipedia "Ingredients of cosmetics" pour extraire
    la liste des ingrédients cosmétiques courants et leurs liens.

    Structure du DOM confirmée :
        - Le heading est <h2 id="Common_ingredients"> à l'intérieur d'un
          <div class="mw-heading mw-heading2">
        - Le grand-parent de ce <div> contient tous les <p> du contenu
        - Chaque <p> contient des liens <a href="/wiki/..."> vers les ingrédients
        - On s'arrête quand on rencontre le prochain <div class="mw-heading mw-heading2">
          (qui est "Types of cosmetics")

    Retourne un DataFrame avec : ingredient, wikipedia_link, description, source
    """
    logger.info("── Source 3 : Extraction par Web Scraping (Wikipedia — Ingredients of cosmetics) ──")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    scraped_ingredients = []

    try:
        logger.info(f"  Requête GET vers {SCRAPING_WIKIPEDIA_COSM_URL} ...")
        response = requests.get(SCRAPING_WIKIPEDIA_COSM_URL, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        logger.info(f"  ✓ Page HTML récupérée — taille : {len(response.text)} caractères")

        # ── Trouver le heading "Common_ingredients" ──
        heading_h2 = soup.find("h2", {"id": "Common_ingredients"})
        if not heading_h2:
            logger.warning("  ⚠ Section 'Common_ingredients' introuvable sur la page")
            return pd.DataFrame(columns=["ingredient", "wikipedia_link", "description", "source"])

        # ── Remonter au grand-parent qui contient le contenu ──
        # heading_h2 est à l'intérieur d'un <div class="mw-heading mw-heading2">
        # le grand-parent de ce div contient tous les <p> de la section
        heading_div = heading_h2.parent   # <div class="mw-heading mw-heading2">
        container   = heading_div.parent  # le conteneur avec tous les <p>

        logger.info(f"  Container trouvé : <{container.name}>")

        # ── Parcourir les enfants du container après le heading_div ──
        found_heading = False
        for child in container.children:
            # On commence à collecter après le heading "Common_ingredients"
            if child is heading_div:
                found_heading = True
                continue

            if not found_heading:
                continue

            # On s'arrête au prochain <div class="mw-heading mw-heading2"> (= section suivante)
            if child.name == "div" and "mw-heading2" in child.get("class", []):
                logger.info(f"  Fin de section détectée : '{child.get_text(strip=True)[:40]}'")
                break

            # On traite uniquement les <p> (paragraphes du contenu)
            if child.name == "p":
                paragraph_text = child.get_text(strip=True)

                # Extraire tous les liens <a href="/wiki/..."> dans ce paragraphe
                for a in child.find_all("a", href=True):
                    href = a["href"]
                    # On ne garde que les liens internes Wikipedia (/wiki/...)
                    # et on exclut les liens vers des references ([1], [2], etc.)
                    if href.startswith("/wiki/") and not href.startswith("/wiki/Special:"):
                        ingredient_name = a.get_text(strip=True)
                        # Filtrer : on ignore les textes très courts ou très génériques
                        if len(ingredient_name) > 2:
                            scraped_ingredients.append({
                                "ingredient":      ingredient_name.upper(),
                                "wikipedia_link":  "https://en.wikipedia.org" + href,
                                "description":     paragraph_text[:200],
                                "source":          "wikipedia_scraping"
                            })

        # ── Dédupliquer par nom d'ingrédient ──
        df = pd.DataFrame(scraped_ingredients)
        if not df.empty:
            df = df.drop_duplicates(subset=["ingredient"]).reset_index(drop=True)

        logger.info(f"  ✓ Scraping — total : {len(df)} ingrédients extraits")
        return df

    except requests.exceptions.Timeout:
        logger.error("  ✗ Timeout lors du scraping Wikipedia")
        return pd.DataFrame(columns=["ingredient", "wikipedia_link", "description", "source"])
    except requests.exceptions.HTTPError as e:
        logger.error(f"  ✗ Erreur HTTP lors du scraping : {e}")
        return pd.DataFrame(columns=["ingredient", "wikipedia_link", "description", "source"])
    except requests.exceptions.RequestException as e:
        logger.error(f"  ✗ Erreur réseau lors du scraping : {e}")
        return pd.DataFrame(columns=["ingredient", "wikipedia_link", "description", "source"])
    except Exception as e:
        logger.error(f"  ✗ Erreur inattendue lors du scraping : {e}")
        return pd.DataFrame(columns=["ingredient", "wikipedia_link", "description", "source"])


# ─────────────────────────────────────────────
# 4. EXTRACTION DEPUIS LA BASE DE DONNÉES MySQL
# ─────────────────────────────────────────────
def extract_from_database() -> dict[str, pd.DataFrame]:
    """
    Se connecte à la base MySQL et extrait les données des tables
    sephora_products et skincare_products.
    Retourne un dictionnaire {table_name: DataFrame}.
    """
    logger.info("── Source 4 : Extraction depuis la base de données MySQL ──")

    connection_string = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    results = {}

    try:
        logger.info(f"  Connexion à MySQL : {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB} ...")
        engine = create_engine(connection_string, pool_pre_ping=True)

        # ── Test de connexion ──
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("  ✓ Connexion MySQL réussie")

        # ── Extraction table sephora_products ──
        try:
            query_sephora = text("""
                SELECT
                    product_id,
                    product_name,
                    brand_name,
                    product_type,
                    price_usd,
                    rating,
                    has_restricted_ingredient,
                    has_cmr,
                    restricted_ingredient_count,
                    cmr_count
                FROM sephora_products
                WHERE product_name IS NOT NULL
                ORDER BY product_id
            """)
            df_sephora = pd.read_sql(query_sephora, engine)
            results["db_sephora"] = df_sephora
            logger.info(f"  ✓ sephora_products : {len(df_sephora)} lignes extraites")
        except Exception as e:
            logger.error(f"  ✗ Erreur extraction sephora_products : {e}")
            results["db_sephora"] = pd.DataFrame()

        # ── Extraction table skincare_products ──
        try:
            query_skincare = text("""
                SELECT
                    brand,
                    product_name,
                    product_type,
                    price,
                    rating,
                    has_restricted_ingredient,
                    has_cmr,
                    restricted_ingredient_count,
                    cmr_count
                FROM skincare_products
                WHERE product_name IS NOT NULL
                ORDER BY brand, product_name
            """)
            df_skincare = pd.read_sql(query_skincare, engine)
            results["db_skincare"] = df_skincare
            logger.info(f"  ✓ skincare_products : {len(df_skincare)} lignes extraites")
        except Exception as e:
            logger.error(f"  ✗ Erreur extraction skincare_products : {e}")
            results["db_skincare"] = pd.DataFrame()

        engine.dispose()

    except Exception as e:
        logger.error(f"  ✗ Impossible de se connecter à MySQL : {e}")
        logger.info("  ⚠ Source MySQL ignorée — le script continue avec les autres sources.")
        results["db_sephora"]  = pd.DataFrame()
        results["db_skincare"] = pd.DataFrame()

    return results


# ─────────────────────────────────────────────
# 5. SAUVEGARDE DES DONNÉES BRUTES EXTRAITES
# ─────────────────────────────────────────────
def save_raw(name: str, df: pd.DataFrame) -> None:
    """Sauvegarde un DataFrame brut dans le dossier data/raw avec un horodatage."""
    if df.empty:
        logger.warning(f"  ⚠ DataFrame '{name}' vide — pas de sauvegarde.")
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DIR / f"{name}_{timestamp}.csv"
    df.to_csv(filepath, index=False, encoding="utf-8")
    logger.info(f"  💾 Sauvegardé : {filepath} ({len(df)} lignes)")


# ─────────────────────────────────────────────
# 6. POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────
def main():
    """
    Point d'entrée du script.
    Orchestre l'extraction depuis les 4 sources,
    sauvegarde les résultats bruts, puis produit un rapport de synthèse.
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("  DÉBUT DE L'EXTRACTION — " + start_time.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    extraction_report = {}  # pour le rapport final

    # ── 1. Fichiers locaux ──
    try:
        files_data = extract_from_files()
        for name, df in files_data.items():
            save_raw(name, df)
            extraction_report[f"fichier_{name}"] = len(df)
    except Exception as e:
        logger.error(f"Erreur non gérée dans extract_from_files : {e}\n{traceback.format_exc()}")

    # ── 2. API REST ──
    try:
        api_data = extract_from_api(max_pages=3)
        save_raw("api_open_beauty_facts", api_data)
        extraction_report["api_open_beauty_facts"] = len(api_data)
    except Exception as e:
        logger.error(f"Erreur non gérée dans extract_from_api : {e}\n{traceback.format_exc()}")

    # ── 3. Web Scraping ──
    try:
        scraping_data = extract_by_scraping()
        save_raw("scraping_wikipedia_cosmetics", scraping_data)
        extraction_report["scraping_wikipedia"] = len(scraping_data)
    except Exception as e:
        logger.error(f"Erreur non gérée dans extract_by_scraping : {e}\n{traceback.format_exc()}")

    # ── 4. Base de données MySQL ──
    try:
        db_data = extract_from_database()
        for name, df in db_data.items():
            save_raw(name, df)
            extraction_report[name] = len(df)
    except Exception as e:
        logger.error(f"Erreur non gérée dans extract_from_database : {e}\n{traceback.format_exc()}")

    # ── Rapport de synthèse ──
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info("  RAPPORT D'EXTRACTION")
    logger.info("=" * 60)
    for source, count in extraction_report.items():
        status = "✓" if count > 0 else "✗ (vide)"
        logger.info(f"  {status}  {source:.<40} {count} lignes")
    logger.info(f"  Durée totale : {duration:.2f} secondes")
    logger.info("=" * 60)


# ── Exécution ──
if __name__ == "__main__":
    main()
