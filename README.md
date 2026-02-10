# extract_data.py — Documentation technique

## Contexte du projet

**Projet** : Regulatory Analysis of Cosmetic Ingredients  
**Objectif** : Collecter, depuis plusieurs sources hétérogènes, les données nécessaires à l'analyse de la conformité réglementaire des ingrédients cosmétiques (directive européenne CosIng vs. produits du marché).  
**Service numérique cible** : Tableau de bord de surveillance réglementaire permettant aux équipes produit d'identifier les ingrédients à risque dans leur catalogue.

---

## Arborescence

```
project/
├── extract_data.py          ← script principal d'extraction
├── requirements.txt         ← dépendances Python
├── .env.example             ← template de configuration (copier en .env)
├── .gitignore
├── README.md                ← ce fichier
├── data/
│   └── raw/                 ← données brutes sauvegardées par le script
└── logs/
    └── extraction.log       ← log détaillé de chaque exécution
```

---

## Dépendances

| Paquet           | Rôle                                              |
|------------------|---------------------------------------------------|
| pandas           | Manipulation et sauvegarde des DataFrames         |
| openpyxl / xlrd  | Lecture des fichiers Excel (.xlsx / .xls)         |
| requests         | Requêtes HTTP pour l'API REST et le scraping      |
| beautifulsoup4   | Parsing du HTML pour le scraping                  |
| lxml             | Parseur HTML rapide utilisé par BeautifulSoup     |
| pymysql          | Driver MySQL pour SQLAlchemy                      |
| SQLAlchemy       | Abstraction de connexion base de données          |
| python-dotenv    | Chargement des variables d'environnement (.env)   |

**Installation** :
```bash
pip install -r requirements.txt
```

---

## Configuration

1. Copier `.env.example` en `.env`
2. Remplir les valeurs (mot de passe MySQL, chemins vers les fichiers bruts)
3. Le fichier `.env` n'est jamais commité sur Git (cf. `.gitignore`)

---

## Commande d'exécution

```bash
python extract_data.py
```

Le script s'exécute de façon autonome : il lit la configuration, extrait les données, les sauvegarde, puis affiche un rapport.

---

## Sources d'extraction

Le script collecte les données depuis **4 types de sources** :

### 1. Fichiers de données locaux
- **COSING_Annex_III_v2.xls** : liste réglementaire des ingrédients cosmétiques (Annexe III de la directive européenne). Format Excel.
- **product_info.csv** : catalogue de produits Sephora avec ingrédients. Format CSV.
- **cosmetics.csv** : catalogue de produits skincare avec ingrédients. Format CSV.

### 2. API REST — Open Beauty Facts
- **URL** : `https://world.openfoodfacts.org/cgi/search.pl`
- **Méthode** : GET avec paramètres de requête (`search_terms=cosmetics`, pagination)
- **Données récupérées** : nom du produit, marque, liste des ingrédients, catégories, pays d'origine, code-barres
- **Pagination** : 25 résultats par page, 3 pages par défaut (configurable via le paramètre `max_pages`)
- **Authentification** : aucune clé nécessaire (API publique)

### 3. Web Scraping — CosIng (Commission européenne)
- **URL** : `https://cosing.ec.europa.eu/cosing-annexes_en`
- **Objectif** : extraire la liste officielle des ingrédients réglementés depuis la source institutionnelle
- **Stratégies de parsing** (par ordre de priorité) :
  1. Extraction des tableaux HTML (`<table>`) contenant les données réglementaires
  2. Si pas de tableau : identification des liens vers les annexes
  3. Fallback : extraction des blocs texte contenant les mots-clés réglementaires

### 4. Base de données MySQL
- **Tables cibles** : `sephora_products`, `skincare_products`
- **Données récupérées** : produits déjà importés avec leurs flags réglementaires (`has_restricted_ingredient`, `has_cmr`)
- **Connexion** : via SQLAlchemy avec les identifiants dans `.env`
- **Comportement si indisponible** : le script continue avec les autres sources (pas de blocage)

---

## Enchaînement logique de l'algorithme

```
START
  │
  ├─► 1. Chargement de la configuration (.env)
  ├─► 2. Initialisation du logging
  │
  ├─► 3. extract_from_files()       → lecture des 3 fichiers locaux
  ├─► 4. extract_from_api()         → appels API REST avec pagination
  ├─► 5. extract_by_scraping()      → requête HTTP + parsing HTML
  ├─► 6. extract_from_database()    → connexion MySQL + requêtes SQL
  │
  ├─► 7. save_raw()                 → sauvegarde de chaque source en CSV horodaté
  └─► 8. Rapport de synthèse        → nombre de lignes par source + durée
END
```

---

## Gestion des erreurs

| Scénario                              | Comportement                                          |
|---------------------------------------|-------------------------------------------------------|
| Fichier local introuvable             | Log `ERROR`, DataFrame vide, script continue          |
| Timeout API / réseau                  | Log `WARNING`, passage à la page suivante             |
| Erreur HTTP (4xx/5xx)                 | Log `ERROR`, source ignorée                           |
| Erreur de parsing JSON                | Log `ERROR`, page ignorée                             |
| MySQL indisponible ou identifiants incorrects | Log `ERROR`, source ignorée, script continue   |
| Erreur inattendue (exception générique) | Log `ERROR` avec traceback complet                  |

Chaque fonction est isolée dans un bloc `try/except` propre : l'échec d'une source ne bloque jamais les suivantes.

---

## Fichier de log

Chaque exécution génère un log détaillé dans `logs/extraction.log` avec :
- Horodatage de chaque étape
- Nombre de lignes extraites par source
- Tous les avertissements et erreurs rencontrés
- Durée totale d'exécution
