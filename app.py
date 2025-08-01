"""
*
* @author : Brandon C. ETOCHA
* @version : Version finale déployée le 01/08/2025 sur le serveur local de l'usine.
* @update : Cette version permet une gestion des catalogues de défaillance par projet.
* @update : Cette version permet également de faire une validation des modifications en deux temps, en affichant en orange les modifications non validées.
* @date : 01/08/2025
*
"""

import shutil
import streamlit as st
import pandas as pd
import os
from io import BytesIO
import io
import hashlib
import json
from datetime import datetime
import re
from difflib import SequenceMatcher, Differ
import numpy as np

# ==============================================================================
# 0. Helpers généraux
# ==============================================================================
def rerun():
    try:
        st.rerun()
    except AttributeError as e:
        st.error(f"Erreur lors du rerun : {e}")

def reload_dataframe(path: str) -> pd.DataFrame:
    try: 
        return pd.read_excel(path, dtype=str)
    except Exception as e:
        st.error(f"Erreur lors du chargement de {path}: {str(e)}")
        return pd.DataFrame()

def extract_clean(o: str) -> str:
    o = o.strip().upper()
    m1 = re.match(r"^(\d+)-[\w]+$", o)
    if m1:
        return "R" + m1.group(1)
    
    m2 = re.match(r"^(\d{3,4})[A-Z]+$", o)
    if m2:
        return m2.group(1)
    
    base = o.split("-", 1)[0].strip()
    m3 = re.match(r"^(\d+)", base)
    if m3:
        return m3.group(1)
    
    return str(base)

def clean_dataframe(df):
    for col in df.columns:
        try: 
            df[col] = df[col].astype(str).str.strip()
        except Exception:
            continue
    return df

def get_new_localisations(block_obj, df_corres):
    known_codes = df_corres["Code Loca"].astype(str).values
    return [code for code in block_obj["clean_set"] if code not in known_codes]

def get_new_or_updated_blocs(block_codes, df_blocs_fonctions):
    bloc_titles_in_data = df_blocs_fonctions["Libellé élément Schémathèque X82"].astype(str).unique().tolist()
    return [b for b in block_codes if b["title"] not in bloc_titles_in_data]

def generate_element_structure(bloc_obj, df_corres):
    new_locs = get_new_localisations(bloc_obj, df_corres)
    return pd.DataFrame([{
        "Code Loca": loc,
        "UET": "",
        "Famille": "",
        "Sous-famille": "",
    } for loc in new_locs])

def generate_empty_localisations(file_path):
    df_vierge = pd.DataFrame(columns=["LOCALISATION", "LABEL"])
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df_vierge.to_excel(file_path, index=False)
    st.success(f"✅ Fichier généré : {file_path}")
    rerun()
    return df_vierge

def ensure_blocs_fonctions_file(base_dir: str, project: str) -> str:
    """Vérifie l'existence du fichier blocs_fonctions pour le projet, le crée si nécessaire"""
    path = os.path.join(base_dir, f"data/blocs_fonctions_{project}.xlsx")
    if not os.path.exists(path):
        df = pd.DataFrame(columns=[
            "Code élément",
            "Libellé élément Schémathèque", 
            "Libéllé Retenu"
        ])
        df.to_excel(path, index=False)
    return path

# -----------------------------------------------------------------------------
# 1.1. Fonctions - Gestion de la copie de travail persistante
# -----------------------------------------------------------------------------
def ensure_working_copy(base_dir: str, project: str) -> tuple[str, str, str]:
    """
    Crée une copie de travail si absente.
    Retourne les chemins : (fichier officiel, fichier de travail, backup de l'officiel)
    """
    official_path = os.path.join(base_dir, f"data/blocs_fonctions_{project}.xlsx")
    working_path = os.path.join(base_dir, f"data/working_blocs_fonctions_{project}.xlsx")
    backup_path = os.path.join(base_dir, f"data/old_blocs_fonctions_{project}.xlsx")

    if not os.path.exists(working_path):
        if os.path.exists(official_path):
            shutil.copyfile(official_path, working_path)
        else:
            df = pd.DataFrame(columns=["Code élément", "Libellé élément Schémathèque", "Libéllé Retenu"])
            df.to_excel(working_path, index=False)
    return official_path, working_path, backup_path

def valider_modifications(base_dir: str, project: str):
    """
    Sauvegarde l'ancien fichier officiel comme back up, puis remplace avec la version de travail et supprime la version de travail.
    """
    working_path = os.path.join(base_dir, f"data/working_blocs_fonctions_{project}.xlsx")

    official, working, backup = ensure_working_copy(base_dir, project)
    if os.path.exists(official):
        shutil.copyfile(official, backup)
    else:
        st.info("ℹ️ Aucun fichier officiel à sauvegarder. Création d'une première version.")

    if os.path.exists(working):
        shutil.copyfile(working, official)
        os.remove(working_path)
        st.success("✅ Modifications validées et version précédente sauvegardée.")
        rerun()
    else:
        st.warning("⚠️ Aucune version de travail trouvée à valider.")

def revert_working_copy(base_dir: str, project: str):
    """
    Réinitialise la version de travail à partir de la version officielle,
    sans modifier l'officiel ni supprimer définitivement les données.
    """
    official_path = os.path.join(base_dir, f"data/blocs_fonctions_{project}.xlsx")
    working_path = os.path.join(base_dir, f"data/working_blocs_fonctions_{project}.xlsx")

    if os.path.exists(official_path):
        shutil.copy2(official_path, working_path)
        st.info("🔄 Version de travail réinitialisée à partir de la version officielle.")
        rerun()
    else:
        st.warning("❌ Version officielle introuvable, impossible de réinitialiser.")



def get_bloc_status(title: str, official_df: pd.DataFrame, working_df: pd.DataFrame) -> str:
    """
    Détermine si un bloc est :
    - green (identique entre fichiers)
    - orange (présent mais différent dans working)
    - red (absent)
    """
    off = official_df[official_df["Libellé élément Schémathèque"] == title]["Code élément"].astype(str).sort_values().tolist()
    work = working_df[working_df["Libellé élément Schémathèque"] == title]["Code élément"].astype(str).sort_values().tolist()

    if off and work:
        return "green"
    elif off and not work:
        return "orange"
    elif work and not off: 
        return "orange"
    else :
        return "red"


# ============================================================================== 
# 1.2. Fonctions - Recommandations
# ============================================================================== 
def charger_correspondances_fonctions(path="correspondances_fonctions.txt"):
    mapping = {}
    if os.path.exists(path):
        df_map = pd.read_csv(path, header=None, names=["clé", "fonction"])
        for _, r in df_map.iterrows():
            mapping[r["clé"].strip().lower()] = r["fonction"].strip()
    return mapping

def recommander_fonctions(
    bloc_title: str,
    mapping: dict,
    df_elements: pd.DataFrame,
    base_threshold: float = 0.4,
    bonus_per_keyword: float = 1.0,
    malus_no_keyword: float = -0.5
) -> list[str]:
    """
    Pour chaque mot‑clé trouvé dans le titre de bloc :
      - on donne un bonus
    Si aucun mot‑clé, on applique un malus unique.
    On renvoie la liste des ELEMENT dont le score enrichi >= seuil.
    """
    # Pré‑traitement du titre
    titre = (bloc_title.replace("_", " ")
                      .replace("schematic", "")
                      .replace("sheet1", "")
                      .replace("/", " ")
                      .replace("X82", "")
                      .replace("ph2", "")
                      .lower())
    scores = {}
    # 1) Ratio de similarité titre ↔ INTITULE
    for _, row in df_elements.dropna(subset=["INTITULE"]).iterrows():
        elem = row["ELEMENT"]
        intit = str(row["INTITULE"]).lower()
        ratio = SequenceMatcher(None, titre, intit).ratio()
        if ratio >= base_threshold:
            scores[elem] = ratio  # score initial

    # 2) Bonus / malus via mapping mots‑clés → fonction
    found_keyword = False
    for mot_cle, fct in mapping.items():
        if mot_cle in titre:
            found_keyword = True
            # récupérer tous les ELEMENTs associés à cette fonction
            mask = df_elements["INTITULE"].str.contains(fct, case=False, na=False)
            for elem in df_elements.loc[mask, "ELEMENT"]:
                scores[elem] = scores.get(elem, 0) + bonus_per_keyword

    # Si aucun mot‑clé n’a matché, on applique un malus à tous
    if not found_keyword:
        for elem in scores.keys():
            scores[elem] += malus_no_keyword

    # 3) Filtrer et trier par score décroissant
    recommandations = [
        (score, elem)
        for elem, score in scores.items()
        if score >= base_threshold
    ]
    recommandations.sort(reverse=True, key=lambda x: x[0])

    return [elem for _, elem in recommandations]

def recommander_par_intitule(
    bloc_title: str,
    df_elements: pd.DataFrame,
    threshold: float = 0.4,
    bonus_word_match: float = 0.2
) -> list[tuple[float, str, str]]:
    """
    Compare le titre du bloc et chaque INTITULE :
      - score = ratio SequenceMatcher + bonus si des mots clés du titre apparaissent dans l'intitulé
    Renvoie top 5 trié par score.
    """
    title = (bloc_title.replace("_", " ")
                       .replace("schematic", "")
                       .replace("sheet1", "")
                       .replace("/", " ")
                       .replace("X82", "")
                       .replace("ph2", "")
                       .lower())
    words = set(title.split())
    recos = []

    for _, row in df_elements.dropna(subset=["INTITULE"]).iterrows():
        elem = row["ELEMENT"]
        intit = str(row["INTITULE"]).lower()
        ratio = SequenceMatcher(None, title, intit).ratio()
        # bonus pour mots en commun
        common = words & set(intit.split())
        bonus = len(common) * bonus_word_match
        score = ratio + bonus
        if score >= threshold:
            recos.append((score, elem, row["INTITULE"]))

    recos.sort(reverse=True, key=lambda x: x[0])
    return recos[:5]

def propagate_to_similar(
    target: str,
    df_blocs_fonctions: pd.DataFrame,
    base_dir: str,
    project,
    threshold: float = 0.875,
    path_weight: float = 0.6,
    name_weight: float = 0.4,
    reference_titles: set = None,
    existing_functions: set = None
) -> tuple[dict[str, list[str]], float, dict[str, list[str]], dict[str, float]]:
    """
    Compare avec TOUS les blocs historiques et regroupe toutes les fonctions des blocs similaires,
    en excluant celles déjà associées au bloc cible.

    Retourne :
    - prop : dictionnaire avec toutes les fonctions similaires
    - best_score : le meilleur score rencontré
    - similar_sources : dict {bloc similaire: [fonctions associées]}
    - bloc_scores : dict {bloc similaire: score de similarité avec le bloc cible}
    """
    # Charger tous les fichiers blocs_fonctions des autres projets
    all_blocs_files = [f for f in os.listdir(os.path.join(base_dir, "data")) 
                      if f.startswith("blocs_fonctions_") and f.endswith(".xlsx")]
    
    # Concaténer tous les DataFrames
    all_blocs = [df_blocs_fonctions]
    for file in all_blocs_files:
        if file != f"blocs_fonctions_{project}.xlsx":  # Éviter de charger le fichier courant deux fois
            path = os.path.join(base_dir, "data", file)
            df = pd.read_excel(path)
            all_blocs.append(df)
    
    full_df = pd.concat(all_blocs, ignore_index=True)
    
    # Le reste de la fonction reste identique mais utilise full_df au lieu de df_blocs_fonctions
    prop = {}
    similar_sources = {}
    bloc_scores = {}
    all_functions = set()

    if existing_functions is None:
        existing_functions = set()

    target_parts = target.split('/')
    target_path = '/'.join(target_parts[:-1])
    target_name = target_parts[-1]

    best_score = 0.0

    for _, row in full_df.iterrows():
        oth = row["Libellé élément Schémathèque"]
        if oth == target or pd.isna(oth):
            continue

        if reference_titles is not None and oth not in reference_titles:
            continue

        oth_parts = str(oth).split('/')
        oth_path = '/'.join(oth_parts[:-1])
        oth_name = oth_parts[-1]

        path_sim = SequenceMatcher(None, target_path.lower(), oth_path.lower()).ratio() * path_weight
        name_sim = SequenceMatcher(None, target_name.lower(), oth_name.lower()).ratio() * name_weight
        combined_score = path_sim + name_sim

        if combined_score >= threshold:
            f = row["Code élément"]
            if isinstance(f, str):
                f = f.strip()
                if f not in existing_functions:
                    all_functions.add(f)
                    if oth not in similar_sources:
                        similar_sources[oth] = []
                    similar_sources[oth].append(f)

            bloc_scores[oth] = combined_score

            if combined_score > best_score:
                best_score = combined_score

    if all_functions:
        prop["TOUTES LES FONCTIONS SIMILAIRES"] = sorted(all_functions)

    return prop, best_score, similar_sources, bloc_scores


# ==============================================================================
# 2. Config utilisateur & authentification
# ==============================================================================
def compute_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def load_index(index_file: str):
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_index(index: dict, index_file: str):
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
CONFIG_FILE = r"C:\Users\a048168\Documents\element-maj-app"


def auth_user():
    USERS = {"admin":"Admin","acteur":"Acteur"}
    if "role" not in st.session_state:
        st.sidebar.subheader("🔐 Connexion")
        user = st.sidebar.selectbox("Profil", ["admin","acteur"], key="login_user")
        pwd = st.sidebar.text_input("Mot de passe", type="password", key="login_pwd")
        if st.sidebar.button("🔑 Se connecter"):
            if USERS.get(user) == pwd:
                st.session_state.role = user
                st.sidebar.success(f"Connecté en tant que {user}")
                rerun()
            else:
                st.sidebar.error("Identifiants incorrects")
        st.stop()


# ==============================================================================
# 3. Gestion des schémathèques
# ==============================================================================
def manage_schema_history(base_dir: str) -> tuple:
    """
    Gère l'historique des schémathèques avec upload, sélection et gestion des fichiers existants.
    Retourne: (schema_text, found_localisations, index, project)
    """
    # Chargement de la liste des projets
    try:
        with open("Liste_projets.txt", "r", encoding="utf-8") as f:
            liste_projet = [p.strip() for p in f.read().split(",") if p.strip()]
    except FileNotFoundError:
        liste_projet = []
        with open("Liste_projets.txt", "w", encoding="utf-8") as f:
            f.write("")

    # Initialisation des répertoires
    HISTORY_DIR = os.path.join(base_dir, "schema_history")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    INDEX_FILE = os.path.join(HISTORY_DIR, "index.json")
    
    index = load_index(INDEX_FILE)
    project = None
    schema_text = None
    found_localisations = {}
    
    # Utilisation d'onglets
    tab1, tab2 = st.tabs(["📤 Uploader une schémathèque", "🗃️ Gérer les schémathèques"])
    
    with tab1:
        # Section upload de nouvelle schémathèque
        uploaded = st.file_uploader("📁 Télécharger un fichier .txt de schémathèque", type="txt")
        
        if uploaded:
            new_filename = st.text_input("📝 Nom du fichier (sans extension)", key="custom_filename")
            
            # Gestion des projets
            col1, col2 = st.columns(2)
            with col1:
                project = st.radio("Choisir un projet existant:", liste_projet, 
                                 horizontal=True, key="project_filter")
            with col2:
                nv_projet = st.text_input("Ou créer un nouveau projet:", key="custom_project_name")
                
            if nv_projet and nv_projet not in liste_projet:
                liste_projet.append(nv_projet)
                with open("Liste_projets.txt", "w", encoding="utf-8") as f:
                    f.write(",".join(liste_projet))
                project = nv_projet

                # Création du nouveau fichier blocs_fonctions
                blocs_fonctions_path = os.path.join(base_dir, f"data/blocs_fonctions_{nv_projet}.xlsx")
                if not os.path.exists(blocs_fonctions_path):
                    df_nouveau = pd.DataFrame(columns=[
                        "Code élément",
                        "Libellé élément Schémathèque",
                        "Libéllé Retenu"
                    ])
                    df_nouveau.to_excel(blocs_fonctions_path, index=False)
                    st.success(f"Nouveau fichier créé : blocs_fonctions_{nv_projet}.xlsx")

                # AJOUT DE LA NOUVELLE COLONNE UET
                uet_col = f"UET {nv_projet}"
                corres_path = os.path.join(base_dir, "data/localisation_uet.xlsx")
                df_corres = pd.read_excel(corres_path)
                
                if uet_col not in df_corres.columns:
                    df_corres[uet_col] = ""  # Crée la nouvelle colonne vide
                    df_corres.to_excel(corres_path, index=False)
                    st.success(f"Nouvelle colonne '{uet_col}' ajoutée au fichier de correspondance")
            
            # Validation et sauvegarde
            if st.button("💾 Enregistrer la schémathèque", key="save_btn"):
                if not new_filename:
                    st.error("❌ Un nom de fichier est requis")
                    st.stop()
                
                # Formatage du nom de fichier
                if not new_filename.endswith('.txt'):
                    new_filename += '.txt'
                
                full_path = os.path.join(HISTORY_DIR, new_filename)
                
                # Vérification doublon
                if os.path.exists(full_path):
                    st.error(f"❌ Le fichier '{new_filename}' existe déjà!")
                    st.stop()
                
                # Lecture et vérification du contenu
                sch_content = uploaded.getvalue().decode("utf-8")
                if not sch_content.strip():
                    st.error("❌ Le fichier est vide!")
                    st.stop()
                
                # Calcul hash pour éviter les doublons
                h = compute_hash(sch_content)
                if any(entry.get("hash") == h for entry in index.values()):
                    st.warning("⚠️ Une schémathèque identique existe déjà!")
                    st.stop()
                
                # Sauvegarde du fichier
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(sch_content)
                
                # Mise à jour de l'index
                timestamp = datetime.now().isoformat()
                index[new_filename] = {
                    "filename": new_filename,
                    "project": project,
                    "timestamp": timestamp,
                    "hash": h
                }
                save_index(index, INDEX_FILE)
                st.success(f"✅ Schémathèque '{new_filename}' enregistrée pour le projet '{project}'")
                st.rerun()


        if index:
            # Tri par date décroissante
            sorted_schemas = sorted(index.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)

            # # Chargement automatique de la dernière si aucune sélection manuelle
            # if not schema_text and index:
            #     latest_schema = sorted_schemas[0][1]  # Premier élément après le tri
            #     latest_path = os.path.join(HISTORY_DIR, latest_schema['filename'])
            #     with open(latest_path, "r", encoding="utf-8") as f:
            #         schema_text = f.read()
            #     project = latest_schema.get("project")
            #     st.info(f"ℹ️ Chargement automatique de la dernière schémathèque: {latest_schema['filename']}")


            
            # Création des options pour le selectbox
            schema_options = []
            for schema_name, schema_data in sorted_schemas:
                display_text = (
                    f"{schema_data['filename']} "
                    f"({schema_data.get('project', '?')}) - "
                    f"{schema_data.get('timestamp', 'date inconnue')}"
                )
                schema_options.append((schema_name, schema_data['filename'], display_text))
            
            # Sélection manuelle
            selected_option = st.selectbox(
                "Sélectionner dans l'historique:",
                options=schema_options,
                format_func=lambda x: x[0].strip().replace(".txt", ""),
                key="manual_schema_select"
            )
            
            if selected_option and st.button("Charger cette schémathèque"):
                schema_name, filename, _ = selected_option
                selected_path = os.path.join(HISTORY_DIR, filename)
                with open(selected_path, "r", encoding="utf-8") as f:
                    schema_text = f.read()
                project = index[schema_name].get("project")
                st.success(f"Schémathèque chargée: {filename}")
                st.session_state["schema_data"] = schema_text, found_localisations, index, project
                # st.rerun()


    with tab2:
        # Section gestion des schémathèques existantes
        if not index:
            st.info("ℹ️ Aucune schémathèque enregistrée")
        else:
            # Tri par date décroissante
            sorted_items = sorted(index.items(), 
                                key=lambda x: x[1].get("timestamp", ""), 
                                reverse=True)
            
            # Sélection d'une schémathèque
            selected_filename = st.selectbox(
                "📜 Schémathèques disponibles",
                options=[v["filename"] for k, v in sorted_items],
                format_func=lambda x: f"{x} ({index[x].get('project')})",
                key="schema_selector"
            )
            
            if selected_filename:
                selected_path = os.path.join(HISTORY_DIR, selected_filename)
                project_to_delete = index[selected_filename].get("project")
                
                # Boutons d'actions
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("🔍 Afficher", key="show_btn"):
                        with open(selected_path, "r", encoding="utf-8") as f:
                            schema_text = f.read()
                            st.code(schema_text, language="text")
                
                with col2:
                    if st.button("🗑️ Supprimer", key="del_btn"):
                            if os.path.exists(selected_path):
                                # 1. Suppression du fichier
                                os.remove(selected_path)
                                
                                # 2. Suppression de l'index
                                index.pop(selected_filename)
                                save_index(index, INDEX_FILE)
                                
                            
                            st.success("✅ Schémathèque et données associées supprimées")
                            st.rerun()
                
                with col3:
                    if st.button("📥 Télécharger", key="dl_btn"):
                        with open(selected_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Télécharger",
                                data=f,
                                file_name=selected_filename,
                                mime="text/plain"
                            )
 
    

    # Détection des localisations si schémathèque chargée
    if schema_text:
        lines = schema_text.splitlines()
        for line in lines:
            texte = line.strip()
            if not texte or "/" in texte or not re.match(r"^[A-Za-z0-9]", texte):
                continue

            if ";" in texte:
                parts = texte.split(";", maxsplit=1)
                code_brut = parts[0].strip()
                label = parts[1].strip().upper() if len(parts) > 1 else ""
            else:
                parts = texte.split(maxsplit=1)
                code_brut = parts[0]
                label = parts[1].strip().upper() if len(parts) > 1 else ""

            clean_code = extract_clean(code_brut)
            if clean_code and len(clean_code) <= 8 and clean_code not in found_localisations:
                found_localisations[clean_code] = label

    return (schema_text, found_localisations, index, project) if schema_text else None

# ==============================================================================
# 4. Parsing de la schémathèque
# ==============================================================================
def parse_schema(schema_text: str) -> tuple[list[dict], dict]:
    if not schema_text:
        return [], {}
    
    blocks = []
    current = []
    for l in schema_text.splitlines():
        if re.match(r"^-{5,}$", l.strip()):
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(l)
    
    if current:
        blocks.append("\n".join(current))
    block_codes = []
    clean2blocks = {}
    
    for blk in blocks:
        # print(blk.splitlines()) debug
        
        # Trouver la première ligne non vide
        for line in blk.splitlines():
            title = line.strip()
            if title:
                break
        else:
            title = "Titre inconnu"
        
        # print("\ntitle :", title) debug
        
        rows = []
        
        for line in blk.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue

            if ";" in line:
                parts = [p.strip() for p in line.split(";", maxsplit=2)]
                if len(parts) < 2:
                    continue
                orig, lbl = parts[:2]
            else:
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue
                orig, lbl = parts

            if orig != "Pas":
                rows.append({"original": orig, "label": lbl})

        if not rows:
            continue
            
        df_blk = pd.DataFrame(rows)
        df_blk["clean"] = df_blk["original"].map(extract_clean)
        
        bloc_obj = {
            "text": blk,
            "title": title,
            "df": df_blk,
            "clean_set": set(df_blk["clean"])
        }
        
        block_codes.append(bloc_obj)
        
        for c in bloc_obj["clean_set"]:
            clean2blocks.setdefault(c, []).append(bloc_obj)
        
        if block_codes and block_codes[0]["title"].startswith("LIST"):
            block_codes = block_codes[1:]

    # print(block_codes[:2])

    return block_codes, clean2blocks

# ==============================================================================
# 5. Chargement des données
# ==============================================================================
def load_common_data(project, base_dir: str):

    official_blocs, working_blocs, backup_blocs = ensure_working_copy(base_dir, project)



    data_paths = {
        "incident_path": os.path.join(base_dir, "data/incidents.xlsx"),
        "element_path": os.path.join(base_dir, "data/elements.xlsx"),
        "corres_path": os.path.join(base_dir, "data/localisation_uet.xlsx"),
        "official_blocs_path": official_blocs,
        "backup_blocs_path": backup_blocs,
        "blocs_fonctions_path": working_blocs,
        "template_path": os.path.join(base_dir, "data/template.xlsx"),
        "localisation_folder": os.path.join(base_dir, f"data/localisations_{project}")
    }

    data = {}
    for name, path in data_paths.items():
        if "folder" in name:
            os.makedirs(path, exist_ok=True)
            data[name] = path
        else:
            data[name] = reload_dataframe(path)

    for df_name in ["incident_path", "element_path", "corres_path", "blocs_fonctions_path", "official_blocs_path"]:
        if isinstance(data[df_name], pd.DataFrame):
            data[df_name] = clean_dataframe(data[df_name])

    return data

# ==============================================================================
# 6. Fonctions pour la sidebar
# ==============================================================================
def show_sidebar_sections(data, project, found_localisations=None):
    """Affiche toutes les sections de la sidebar"""
    st.sidebar.markdown("---")
    uet_projet = " ".join(("UET", project))

    # Gestion des Éléments
    st.sidebar.subheader("🧩 Gestion des Éléments")
    with st.sidebar.expander("🔍 Voir tous les éléments existants"):
        st.dataframe(data["element_path"], use_container_width=True)

    with st.sidebar.expander("✏️ Modifier un élément existant"):
        elem_to_edit = st.selectbox(
            "Choisir un élément à modifier",
            data["element_path"]["ELEMENT"].astype(str).unique(),
            key="edit_elem_select"
        )
        
        subset = data["element_path"].loc[data["element_path"]["ELEMENT"].astype(str) == str(elem_to_edit)]
        if not subset.empty:
            edit_data = subset.iloc[0]
            current_label = edit_data.get("INTITULE") or edit_data.get("LIBELLE") or ""
            new_code = st.text_input("Code", value=str(edit_data["ELEMENT"]), key="edit_elem_code")
            new_label = st.text_input("Libellé", value=str(current_label), key="edit_elem_label")

            if st.button("💾 Enregistrer les modifications", key="edit_elem_btn"):
                try:
                    data["element_path"].loc[data["element_path"]["ELEMENT"] == elem_to_edit, "ELEMENT"] = new_code.strip()
                    label_col = "INTITULE" if "INTITULE" in data["element_path"].columns else "LIBELLE"
                    data["element_path"].loc[data["element_path"]["ELEMENT"] == new_code, label_col] = new_label.strip()
                    data["element_path"].to_excel(os.path.join(data["base_dir"], "data/elements.xlsx"), index=False)
                    st.success("✅ Élément modifié avec succès !")
                    rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")

    with st.sidebar.expander("➕ Créer un nouvel élément"):
        new_elem_code = st.text_input("Code élément*", help="Doit être unique", key="new_elem_code")
        new_elem_label = st.text_input("Libellé élément*", key="new_elem_label")
        
        if st.button("✅ Créer l'élément", key="create_elem_btn"):
            if new_elem_code and new_elem_label:
                if new_elem_code in data["element_path"]["ELEMENT"].values:
                    st.error("Ce code élément existe déjà !")
                else:
                    new_loca_file = os.path.join(data["localisation_folder"], f"{new_elem_code}_localisations.xlsx")
                    pd.DataFrame(columns=["LOCALISATION", "LABEL"]).to_excel(new_loca_file, index=False)
                    
                    data["element_path"] = pd.concat([
                        data["element_path"],
                        pd.DataFrame([{"ELEMENT": new_elem_code, "INTITULE": new_elem_label}])
                    ], ignore_index=True)
                    
                    try:
                        data["element_path"].to_excel(os.path.join(data["base_dir"], "data/elements.xlsx"), index=False)
                        st.success("Élément créé avec succès !")
                        rerun()
                    except Exception as e:
                        st.error(f"Erreur : {str(e)}")
            else:
                st.warning("Les champs marqués d'une * sont obligatoires")

    with st.sidebar.expander("🗑️ Supprimer un élément"):
        elem_to_delete = st.selectbox(
            "Choisir un élément à supprimer :",
            data["element_path"]["ELEMENT"].unique(),
            key="delete_elem_select"
        )
        
        if st.button("❌ Confirmer la suppression", key="delete_elem_btn"):
            try:
                data["element_path"] = data["element_path"][data["element_path"]["ELEMENT"] != elem_to_delete]
                loca_file = os.path.join(data["localisation_folder"], f"{elem_to_delete}_localisations.xlsx")
                if os.path.exists(loca_file):
                    os.remove(loca_file)
                
                data["element_path"].to_excel(os.path.join(data["base_dir"], "data/elements.xlsx"), index=False)
                st.success("Élément supprimé !")
                rerun()
            except Exception as e:
                st.error(f"Erreur : {str(e)}")

    st.sidebar.markdown("---")
    
    # Gestion des Localisations
    st.sidebar.subheader("🗺️ Gestion des Localisations")

    if found_localisations:
        existing_loca_codes = data["corres_path"]["Code Loca"].astype(str).str.strip().unique()
        new_loca_items = {
            code: label 
            for code, label in found_localisations.items() 
            if code not in existing_loca_codes
        }
        
        if new_loca_items:
            count = len(new_loca_items)
            with st.sidebar.expander(f"### 🆕 {count} nouvelle{'s' if count>1 else ''} localisation{'s' if count>1 else ''} (UET à configurer)", expanded=True):
                st.info("Configurez les UET pour les nouvelles localisations détectées")
                
                # Formulaire pour les nouvelles UET
                uet_mapping = {}
                for code, label in new_loca_items.items():
                    cols = st.columns([3, 2])
                    with cols[0]:
                        st.text_input("Code Localisation", value=code, disabled=True, key=f"new_loc_{code}")
                    with cols[1]:
                        uet = st.text_input(uet_projet, key=f"new_uet_{code}", placeholder="Ex: RET")
                        if uet:
                            uet_mapping[code] = uet
                
                # Boutons de validation
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Enregistrer UET", type="primary"):
                        if uet_mapping:
                            new_entries = [{
                                "Code Loca": code,
                                uet_projet: uet,
                                "Famille": project,
                                "Sous-famille": "",
                                "Libellé Long Loca": new_loca_items[code]
                            } for code, uet in uet_mapping.items()]
                            
                            data["corres_path"] = pd.concat([data["corres_path"], pd.DataFrame(new_entries)])
                            data["corres_path"].to_excel(
                                os.path.join(data["base_dir"], "data/localisation_uet.xlsx"), 
                                index=False
                            )
                            st.success("UET enregistrées !")
                            st.rerun()
                        else:
                            st.warning("Aucune UET renseignée")

    with st.sidebar.expander("🔍 Voir toutes les localisations"):
        st.dataframe(data["corres_path"], use_container_width=True)

    with st.sidebar.expander("✏️ Modifier une localisation"):
        loca_to_edit = st.selectbox(
            "Choisir un code Loca :",
            data["corres_path"]["Code Loca"].unique(),
            key="edit_loca_select"
        )

        edit_data = data["corres_path"].loc[data["corres_path"]["Code Loca"] == loca_to_edit].iloc[0]
        new_code = st.text_input("Code Loca", value=edit_data["Code Loca"], key="edit_loca_code")
        new_label = st.text_input("Libellé Long Loca", value=edit_data["Libellé Long Loca"], key="edit_loca_label")
        new_uet = st.text_input(uet_projet, value=edit_data[uet_projet], key="edit_loca_uet")

        if st.button("💾 Enregistrer les modifications", key="edit_loca_btn"):
            try:
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == loca_to_edit, "Code Loca"] = new_code
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == new_code, "Libellé Long Loca"] = new_label
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == new_code, uet_projet] = new_uet
                data["corres_path"].to_excel(os.path.join(data["base_dir"], "data/localisation_uet.xlsx"), index=False)
                st.success("Localisation modifiée avec succès !")
                rerun()
            except Exception as e:
                st.error(f"Erreur pendant la mise à jour : {e}")

    with st.sidebar.expander("🗑️ Supprimer une localisation"):
        loca_to_delete = st.selectbox(
            "Choisir une localisation à supprimer",
            data["corres_path"]["Code Loca"].unique(),
            key="delete_loca_select"
        )
        
        if st.button("❌ Confirmer la suppression", key="delete_loca_btn"):
            try:
                data["corres_path"] = data["corres_path"][data["corres_path"]["Code Loca"] != loca_to_delete]
                data["corres_path"].to_excel(os.path.join(data["base_dir"], "data/localisation_uet.xlsx"), index=False)
                st.success("Localisation supprimée!")
                rerun()
            except Exception as e:
                st.error(f"Erreur: {str(e)}")

    st.sidebar.markdown("---")
    
    # Gestion des Incidents
    st.sidebar.subheader("🛠️ Gestion des Incidents")
    
    with st.sidebar.expander("✏️ Modifier les incidents existants"):
        selected_incident = st.selectbox(
            "Choisir un incident à modifier :", 
            data["incident_path"]["Code Incident"],
            key="edit_incident_select"
        )
        new_label = st.text_input(
            "Nouveau libellé", 
            value=data["incident_path"][data["incident_path"]["Code Incident"] == selected_incident]["Libellé incident"].values[0],
            key=f"{selected_incident}_incident_label"
        )
        
        if st.button("✅ Modifier l'incident", key="edit_incident_btn"):
            data["incident_path"].loc[data["incident_path"]["Code Incident"] == selected_incident, "Libellé Incident"] = new_label
            data["incident_path"].to_excel(os.path.join(data["base_dir"], "data/incidents.xlsx"), index=False)
            st.success("Incident modifié avec succès.")
            rerun()

    with st.sidebar.expander("➕ Ajouter un nouvel incident"):
        new_code = st.text_input("Code Incident à ajouter", key="new_incident_code")
        new_lib = st.text_input("Libellé Incident", key="new_incident_label")
        
        if st.button("➕ Ajouter l'incident", key="add_incident_btn"):
            if new_code and new_lib:
                data["incident_path"] = pd.concat([
                    data["incident_path"],
                    pd.DataFrame([{"Code Incident": new_code, "Libellé Incident": new_lib}])
                ], ignore_index=True)
                data["incident_path"].to_excel(os.path.join(data["base_dir"], "data/incidents.xlsx"), index=False)
                st.success("Incident ajouté avec succès.")
                rerun()
            else:
                st.warning("Merci de remplir les deux champs.")

    with st.sidebar.expander("❌ Supprimer un incident"):
        incident_to_delete = st.selectbox(
            "Sélectionner un incident à supprimer :", 
            data["incident_path"]["Code Incident"],
            key="delete_incident_select"
        )
        
        if st.button("🗑️ Supprimer l'incident", key="delete_incident_btn"):
            data["incident_path"] = data["incident_path"][data["incident_path"]["Code Incident"] != incident_to_delete]
            data["incident_path"].to_excel(os.path.join(data["base_dir"], "data/incidents.xlsx"), index=False)
            st.success("Incident supprimé.")
            rerun()

    st.sidebar.markdown("---")
    
    # Correspondances Localisation - UET
    if st.sidebar.button("🔍 Voir les correspondances localisation - UET"):
        st.session_state.show_corres_edit = True

# ==============================================================================
# 7. Mode "Explorer Blocs"
# ==============================================================================
def show_block_explorer(block_codes, data, project, reference_titles=None):

    project = project
    st.subheader("🔍 Explorer les blocs de la schémathèque")
    col_val, col_reset = st.columns(2)
    with col_val:
        if st.button("✅ Valider les modifications"):
            valider_modifications(data["base_dir"], project)

    with col_reset:
        if st.button("🔄 Réinitialiser la version de travail"):
            revert_working_copy(data["base_dir"], project)

    mapping = charger_correspondances_fonctions()
    all_titles = [b["title"] for b in block_codes]
    current_titles = set(all_titles)
    blocs_rattaches = set(data["blocs_fonctions_path"]["Libellé élément Schémathèque"].astype(str).unique())

    nb_total = len(block_codes)
    nb_non_rattaches = len(current_titles - blocs_rattaches)

    st.markdown(f"""
        - Blocs chargés : `{nb_total}`
        - Nouveaux blocs : `{nb_non_rattaches}`
    """)

    element_dict = dict(zip(data["element_path"]["ELEMENT"], data["element_path"]["INTITULE"]))
    df_display = data["official_blocs_path"].copy()
    df_display["FONCTIONS"] = df_display.apply(
        lambda row: f"{row['Code élément']} ({element_dict.get(row['Code élément'], '?')}) - {row['Libéllé Retenu']}",
        axis=1
    )

    with st.expander("🔍 Voir les associations Bloc - Fonction(s) existantes et validées"):
        st.dataframe(df_display[["Libellé élément Schémathèque", "FONCTIONS"]].rename(
            columns={"Libellé élément Schémathèque": "BLOC"}),
            height=400
        )

    bloc_status = {title: get_bloc_status(title, data["official_blocs_path"], data["blocs_fonctions_path"]) for title in all_titles}
    
    filter_type = st.radio("Filtrer les blocs :", ["Tous", "Avec fonctions", "Sans fonctions", "Modifiés"], horizontal=True, key="bloc_filter")

    if filter_type == "Avec fonctions":
        filtered_titles = [t for t in all_titles if bloc_status[t] in ["green", "orange"]]
    elif filter_type == "Sans fonctions":
        filtered_titles = [t for t in all_titles if bloc_status[t] == "red"]
    elif filter_type == "Modifiés":
        filtered_titles = [t for t in all_titles if bloc_status[t] == "orange"]
    else:
        filtered_titles = all_titles

    st.caption(f"Blocs {filter_type.lower()} : {len(filtered_titles)}")

    # print(block_codes)

    chosen = st.selectbox(
        "Choisir un bloc à visualiser :", 
        filtered_titles, 
        format_func=lambda x: f"🟢 {x}" if bloc_status[x]=="green" else f"🟡 {x}" if bloc_status[x]=="orange" else f"🔴 {x} (Nouveau)",
        index=0 if filtered_titles else None,
        key="explore_blk_select"
    )

    blk_obj = next((b for b in block_codes if b["title"] == chosen), None)
    if not blk_obj:
        st.warning("Bloc non trouvé")
        return

    st.dataframe(blk_obj["df"])

    exist = data["blocs_fonctions_path"].loc[
        data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen,
        "Code élément"
    ].dropna().str.strip().tolist()

    if exist:
        st.markdown("### ✅ Fonctions rattachées")

        df_exist = pd.DataFrame({
            "Fonction": exist,
            "Intitulé": [element_dict.get(f, "Inconnu") for f in exist],
            "Libellé Retenu": data["blocs_fonctions_path"].loc[
                (data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen) &
                (data["blocs_fonctions_path"]["Code élément"].isin(exist)),
                "Libéllé Retenu"
            ].values,
            "Supprimer": [False] * len(exist)
        })

        edited_df = st.data_editor(
            df_exist,
            column_config={
                "Supprimer": st.column_config.CheckboxColumn("Sélectionner", help="Cocher pour supprimer cette association")
            },
            disabled=["Fonction", "Intitulé", "Libellé Retenu"],
            hide_index=True,
            use_container_width=True
        )

        if st.button("🗑️ Supprimer les associations sélectionnées", type="secondary"):
            to_keep = edited_df[~edited_df["Supprimer"]]["Fonction"].tolist()

            if not to_keep:
                data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
                    data["blocs_fonctions_path"]["Libellé élément Schémathèque"] != chosen
                ]
            else:
                data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
                    ~((data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen) &
                      (~data["blocs_fonctions_path"]["Code élément"].isin(to_keep)))
                ]

            data["blocs_fonctions_path"].to_excel(
                os.path.join(data["base_dir"], f"data/working_blocs_fonctions_{project}.xlsx"),
                index=False
            )

            st.success("Suppression effectuée !")
            st.rerun()

    existing_functions = set(exist)

    st.markdown("## 🔎 Recommandations")

    with st.expander("🔍 Par mots-clés", expanded=True):
        direct = recommander_fonctions(chosen, mapping, data["element_path"])

    with st.expander("🤖 Par similarité sémantique", expanded=True):
        sem = recommander_par_intitule(chosen, data["element_path"], threshold=0.4)

    with st.expander("🔄 Par similarité structurelle", expanded=True):
        prop, best_score, similar_sources, bloc_scores = propagate_to_similar(
            chosen,
            data["blocs_fonctions_path"],
            data["base_dir"],
            project,
            reference_titles=reference_titles,
            existing_functions=existing_functions
        )

        if prop:
            st.info("Suggestions basées sur la similarité structurelle :")
            st.markdown(f"Bloc sélectionné : `{chosen}`")
            st.markdown("### 🔄 Blocs similaires (seuil ≥ 87,5 %)")

            st.metric("Blocs similaires trouvés", len(similar_sources))

            for bloc_sim, fonctions in sorted(
                similar_sources.items(),
                key=lambda item: bloc_scores.get(item[0], 0.0),
                reverse=True
            ):
                score = bloc_scores.get(bloc_sim, 0.0)
                score_pct = round(score * 100, 2)
                st.markdown(f"**{bloc_sim}** — Similarité : {score_pct}%")
                for fct in fonctions:
                    libelle = element_dict.get(fct, "Inconnu")
                    st.markdown(f"- `{fct}` — {libelle}")
                st.markdown("---")

            table_data = []
            for bloc_sim, fonctions in similar_sources.items():
                for fct in fonctions:
                    table_data.append({
                        "Bloc source": bloc_sim,
                        "Fonction": fct,
                        "Intitulé": element_dict.get(fct, "Inconnu"),
                        "Score (%)": round(bloc_scores.get(bloc_sim, 0.0) * 100, 2)
                    })

            st.dataframe(
                pd.DataFrame(table_data),
                hide_index=True,
                use_container_width=True
            )

        else:
            st.warning("Aucune fonction similaire trouvée.")

    st.markdown("## 🔗 Ajouter des associations")

    elements = data["element_path"].dropna(subset=["ELEMENT", "INTITULE"])
    options = [(f"{row['ELEMENT']} - {row['INTITULE']}", row['ELEMENT']) for _, row in elements.iterrows()]
    option_labels = [label for label, _ in options]
    option_values = [val for _, val in options]

    defaults = sum(prop.values(), []) if prop else []
    default_indices = [i for i, val in enumerate(option_values) if val in defaults]

    selected_labels = st.multiselect(
        "Associer à des éléments :", 
        option_labels,
        default=[option_labels[i] for i in default_indices],
        key=f"assoc_{chosen}"
    )

    selected_codes = [val for label, val in options if label in selected_labels]
    selected_codes = list(dict.fromkeys(selected_codes))

    if st.button("✅ Associer les Fonctions", key=f"save_{chosen}"):
        existing_df = data["blocs_fonctions_path"]
        other_blocs_df = existing_df[existing_df["Libellé élément Schémathèque"] != chosen]
        chosen_df = existing_df[existing_df["Libellé élément Schémathèque"] == chosen]

        # Codes déjà présents pour ce bloc
        existing_codes = chosen_df["Code élément"].dropna().astype(str).tolist()

        # Fusion des anciens et nouveaux codes
        all_codes = list(set(existing_codes + selected_codes))

        new_entries = []
        for code in all_codes:
            intitule = element_dict.get(code, "")
            new_entries.append({
                "Code élément": code,
                "Libellé élément Schémathèque": chosen,
                "Libéllé Retenu": f"FONCTION {intitule}" if intitule else ""
            })

        # Concat des anciens + nouveaux (remplacé uniquement pour ce bloc)
        updated_df = pd.concat([other_blocs_df, pd.DataFrame(new_entries)], ignore_index=True)

        data["blocs_fonctions_path"] = updated_df

        # Sauvegarde dans le fichier de travail (et non le officiel !)
        updated_df.to_excel(
            os.path.join(data["base_dir"], f"data/working_blocs_fonctions_{project}.xlsx"),
            index=False
        )

        st.success(f"🔗 Associations mises à jour pour le bloc : {chosen}")
        st.rerun()

# ==============================================================================
# 8. Mode "Gestion Élément"
# ==============================================================================
def show_element_manager(block_codes, clean2blocks, data, project):
    uet_projet = " ".join(["UET", project])
    st.header("Choix de l'élément")
    selected_elem = st.selectbox(
        "Choisir un code élément:", 
        data["element_path"].sort_values(by="ELEMENT")["ELEMENT"].unique(),
        format_func=lambda x: f"{x} - {data['element_path'][data['element_path']['ELEMENT'] == x]['INTITULE'].values[0]}"
    )
    
    if not selected_elem:
        st.warning("Veuillez sélectionner un élément")
        return
    
    # 1. Vérification et affichage des blocs associés
    associated_blocs = data["blocs_fonctions_path"][data["blocs_fonctions_path"]["Code élément"] == selected_elem]
    
    # Afficher les blocs associés avec option de détachement
    with st.expander(f"📌 Blocs associés ({len(associated_blocs)} blocs)"):
        if associated_blocs.empty:
            st.warning("Cet élément n'est associé à aucun bloc")
        else:
            for _, row in associated_blocs.iterrows():
                cols = st.columns([4, 1])
                with cols[0]:
                    st.write(f"- {row['Libellé élément Schémathèque']}")
                with cols[1]:
                    if st.button("❌ Détacher", key=f"detach_{row['Libellé élément Schémathèque']}"):
                        # Supprimer l'association
                        data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
                            ~((data["blocs_fonctions_path"]["Code élément"] == selected_elem) & 
                            (data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == row['Libellé élément Schémathèque']))
                        ]
                        data["blocs_fonctions_path"].to_excel(
                            os.path.join(data["base_dir"], f"data/blocs_fonctions_{project}.xlsx"),
                            index=False
                        )
                        st.success("Bloc détaché !")
                        st.rerun()
        
    # 2. Ajout manuel de blocs
    st.subheader("➕ Ajouter un bloc")
    # Liste des titres de tous les blocs
    all_block_titles = [b["title"] for b in block_codes]
    # Titres déjà associés à cet élément
    associated_titles = associated_blocs["Libellé élément Schémathèque"].tolist()
    # Titres disponibles (non associés)
    available_blocks = [t for t in all_block_titles if t not in associated_titles]
    
    selected_block = st.selectbox(
        "Choisir un bloc à associer",
        available_blocks,
        key="add_block_select"
    )
    
    if st.button("🔗 Associer ce bloc", key="add_block_btn"):
        # Ajouter l'association
        new_row = {
            "Code élément": selected_elem,
            "Libellé élément Schémathèque": selected_block,
            "Libéllé Retenu": f"FONCTION {data['element_path'][data['element_path']['ELEMENT'] == selected_elem]['INTITULE'].values[0]}"
        }
        data["blocs_fonctions_path"] = pd.concat([
            data["blocs_fonctions_path"],
            pd.DataFrame([new_row])
        ], ignore_index=True)
        data["blocs_fonctions_path"].to_excel(
            os.path.join(data["base_dir"], f"data/blocs_fonctions_{project}.xlsx"),
            index=False
        )
        st.success("Bloc associé avec succès !")
        st.rerun()
    
    # 3. Gestion des localisations
    loca_file = os.path.join(data["localisation_folder"], f"{selected_elem}_localisations.xlsx")
    
    # Initialisation si fichier manquant
    if not os.path.exists(loca_file):
        st.warning("⚠️ Fichier de localisations manquant pour cet élément")
        if st.button("⚡ Créer le fichier avec les localisations des blocs", type="primary"):
            locas_schema = set()
            for bloc_title in associated_blocs["Libellé élément Schémathèque"]:
                bloc = next((b for b in block_codes if b["title"] == bloc_title), None)
                if bloc:
                    for _, row in bloc["df"].iterrows():
                        locas_schema.add(extract_clean(row["original"]))
            
            df_new = pd.DataFrame({
                "LOCALISATION": list(locas_schema),
                "LABEL": "",
                "SOURCE": "schémathèque"
            })
            df_new.to_excel(loca_file, index=False)
            st.rerun()
        return
    
    df_loca = reload_dataframe(loca_file)
    if df_loca.empty:
        st.error("Fichier vide - Cliquez pour initialiser")
        if st.button("🔄 Remplir avec les localisations des blocs", type="primary"):
            locas_schema = set()
            for bloc_title in associated_blocs["Libellé élément Schémathèque"]:
                bloc = next((b for b in block_codes if b["title"] == bloc_title), None)
                if bloc:
                    for _, row in bloc["df"].iterrows():
                        locas_schema.add(extract_clean(row["original"]))
            
            df_loca = pd.DataFrame({
                "LOCALISATION": list(locas_schema),
                "LABEL": "",
                "SOURCE": "schémathèque"
            })
            df_loca.to_excel(loca_file, index=False)
            st.rerun()
        return
    
    # 4. Extraction des localisations des blocs
    locas_schema = set()
    schema_labels = {}
    for bloc_title in associated_blocs["Libellé élément Schémathèque"]:
        bloc = next((b for b in block_codes if b["title"] == bloc_title), None)
        if bloc:
            for _, row in bloc["df"].iterrows():
                code = extract_clean(row["original"])
                locas_schema.add(code)
                schema_labels[code] = row["label"]
    


    # 5. Gestion des UET manquantes
    filtered_corres = data["corres_path"][data["corres_path"]["Code Loca"].isin(df_loca["LOCALISATION"].astype(str))]
    missing_uet = [loc for loc in df_loca["LOCALISATION"].astype(str).unique() 
                  if loc not in filtered_corres["Code Loca"].values]
    
    uet_projet = " ".join(["UET", project])  # Ex: "UET X8310"

    # Identifier les localisations sans UET pour ce projet spécifique
    missing_uet = []
    configured_locs = []

    for loc in df_loca["LOCALISATION"].astype(str).unique():
        loc_row = data["corres_path"][data["corres_path"]["Code Loca"].astype(str) == loc]
        
        if not loc_row.empty and uet_projet in loc_row.columns:
            uet_value = loc_row[uet_projet].values[0]
            if pd.notna(uet_value) and str(uet_value).strip() and uet_value != "nan":
                configured_locs.append(loc)
            else:
                missing_uet.append(loc)
        else:
            missing_uet.append(loc)


    # # AFFICHAGE DES LOCALISATIONS (toujours visible)
    # st.markdown("#### 🗺 Localisations des blocs")
    # arbo_df = pd.DataFrame([(loc, schema_labels.get(loc, "")) for loc in sorted(locas_schema)],
    #                     columns=["LOCALISATION", "LABEL"])
    # arbo_df["STATUT"] = arbo_df["LOCALISATION"].apply(
    #     lambda x: "✅ Configuré" if x in configured_locs else "❌ UET manquante")
    # st.dataframe(arbo_df)

    # SECTION CONFIGURATION UET (seulement si des UET manquent)
    if missing_uet:
        with st.expander("⚠️ Configuration requise - UET manquantes", expanded=True):
            st.warning(f"{len(missing_uet)} localisations nécessitent une UET pour le projet {project}")
            
            # Création d'un dictionnaire pour stocker les suggestions sélectionnées
            if 'selected_suggestions' not in st.session_state:
                st.session_state.selected_suggestions = {}
            
            # Première passe pour afficher les suggestions et collecter les choix
            suggestions = {}
            for loc in missing_uet:
                loc_row = data["corres_path"][data["corres_path"]["Code Loca"].astype(str) == loc]
                if not loc_row.empty:
                    uet_cols = [c for c in data["corres_path"].columns if c.startswith("UET ") and c != uet_projet]
                    loc_suggestions = []
                    for col in uet_cols:
                        val = loc_row[col].values[0]
                        if pd.notna(val) and str(val).strip():
                            project_name = col.replace("UET ", "")
                            loc_suggestions.append((project_name, str(val).strip()))
                    if loc_suggestions:
                        suggestions[loc] = loc_suggestions
            

            
            # Formulaire principal pour la saisie
            uet_mapping = {}
            with st.form(key="uet_form"):
                for loc in missing_uet:
                    cols = st.columns([2, 3, 1])
                    with cols[0]:
                        st.text_input("Localisation", value=loc, disabled=True, key=f"disp_{loc}")
                    with cols[1]:
                        # Pré-remplir avec la suggestion si disponible
                        default_value = st.session_state.selected_suggestions.get(loc, "")
                        uet_input = st.text_input(
                            "UET", 
                            value=default_value,
                            key=f"uet_{loc}", 
                            placeholder="Ex: RET"
                        )
                    with cols[2]:
                        current_loc_row = data["corres_path"][data["corres_path"]["Code Loca"].astype(str) == loc]
                        label = current_loc_row["Libellé Long Loca"].values[0] if not current_loc_row.empty else schema_labels.get(loc, "Inconnu")
                        st.caption(f"Label: {label}")            # Afficher les suggestions sous forme de selectbox

                for loc, loc_suggestions in suggestions.items():
                    selected = st.selectbox(
                        f"Suggestions pour {loc}",
                        options=["-- Choisir une suggestion --"] + [f"{val} (depuis {proj})" for proj, val in loc_suggestions],
                        key=f"suggest_select_{loc}"
                    )
                    if selected != "-- Choisir une suggestion --":
                        selected_val = selected.split(" (depuis ")[0]
                        st.session_state.selected_suggestions[loc] = selected_val


                
                if st.form_submit_button("💾 Enregistrer les UET", type="primary"):
                    uet_mapping = {
                        loc: st.session_state[f"uet_{loc}"]
                        for loc in missing_uet
                        if st.session_state.get(f"uet_{loc}")
                    }
                    
                    if uet_mapping:
                        # Mise à jour du dataframe de correspondances
                        for loc, uet in uet_mapping.items():
                            mask = data["corres_path"]["Code Loca"].astype(str) == loc
                            
                            if mask.any():  # Mise à jour
                                data["corres_path"].loc[mask, uet_projet] = uet
                            else:  # Création
                                new_row = {
                                    "Code Loca": loc,
                                    uet_projet: uet,
                                    "Libellé Long Loca": schema_labels.get(loc, "Inconnu"),
                                    "Famille": project,
                                    "Sous-famille": ""
                                }
                                data["corres_path"] = pd.concat([
                                    data["corres_path"],
                                    pd.DataFrame([new_row])
                                ], ignore_index=True)
                        
                        # Sauvegarde
                        data["corres_path"].to_excel(
                            os.path.join(data["base_dir"], "data/localisation_uet.xlsx"),
                            index=False
                        )
                        st.success("UET enregistrées avec succès !")
                        st.rerun()
                    else:
                        st.warning("Aucune UET valide à enregistrer")

    st.markdown("---")


    # 6. Ajout manuel de localisations
    with st.expander("📍 Ajouter une localisation à cet élément"):
        add_mode = st.radio("Mode d'ajout :",
                        ["Sélectionner une localisation existante", "Créer une nouvelle localisation"],
                        horizontal=True,
                        key="add_mode_selector")
        
        if add_mode == "Sélectionner une localisation existante":
            existing_locations = data["corres_path"][~data["corres_path"]["Code Loca"].isin(df_loca["LOCALISATION"])]
            
            if not existing_locations.empty:
                selected_existing = st.selectbox(
                    "Choisir une localisation disponible :",
                    existing_locations["Code Loca"].unique(),
                    format_func=lambda x: f"{x} - {existing_locations[existing_locations['Code Loca'] == x]['Libellé Long Loca'].iloc[0]}",
                    key="existing_loc_select"
                )
                
                loc_info = existing_locations[existing_locations["Code Loca"] == selected_existing].iloc[0]
                
                st.markdown(f"""
                    **Détails de la localisation :**
                    - **Code :** {loc_info['Code Loca']}
                    - **Libellé :** {loc_info['Libellé Long Loca']}
                    - **UET associée :** {loc_info[uet_projet]}
                """)
                
                if st.button("➕ Ajouter cette localisation à l'élément", key="add_existing_loc_btn"):
                    new_row = {
                        "LOCALISATION": loc_info['Code Loca'],
                        "LABEL": loc_info['Libellé Long Loca'],
                        "SOURCE": "ajout manuel"
                    }
                    df_loca = pd.concat([df_loca, pd.DataFrame([new_row])], ignore_index=True)
                    
                    try:
                        df_loca.to_excel(loca_file, index=False)
                        st.success(f"Localisation {selected_existing} ajoutée avec succès !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de l'ajout : {str(e)}")
            else:
                st.warning("Toutes les localisations existantes sont déjà attribuées à cet élément.")
        
        else:  # Mode création nouvelle localisation
            with st.form("new_location_form"):
                st.markdown("### Créer une nouvelle localisation")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_code = st.text_input("Code localisation*", help="Doit être unique", key="new_loc_code")
                with col2:
                    new_uet = st.text_input(f"{uet_projet} associée*", key="new_loc_uet")
                
                new_label = st.text_input("Libellé complet*", key="new_loc_label")
                
                if st.form_submit_button("💾 Créer et ajouter"):
                    if not all([new_code, new_label, new_uet]):
                        st.warning("Veuillez remplir tous les champs obligatoires (*)")
                    elif new_code in data["corres_path"]["Code Loca"].values:
                        st.error("Ce code localisation existe déjà !")
                    else:
                        # Ajout à la table de correspondance générale
                        new_corres_row = {
                            "Code Loca": new_code,
                            "Libellé Long Loca": new_label,
                            uet_projet: new_uet,
                            "Famille": project,
                            "Sous-famille": ""
                        }
                        data["corres_path"] = pd.concat([data["corres_path"], pd.DataFrame([new_corres_row])], ignore_index=True)
                        
                        # Ajout à l'élément spécifique
                        new_loca_row = {
                            "LOCALISATION": new_code,
                            "LABEL": new_label,
                            "SOURCE": "création manuelle"
                        }
                        df_loca = pd.concat([df_loca, pd.DataFrame([new_loca_row])], ignore_index=True)
                        
                        try:
                            # Sauvegarde des deux fichiers
                            data["corres_path"].to_excel(
                                os.path.join(data["base_dir"], "data/localisation_uet.xlsx"),
                                index=False
                            )
                            df_loca.to_excel(loca_file, index=False)
                            st.success("Nouvelle localisation créée et ajoutée avec succès !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur lors de la sauvegarde : {str(e)}")

    st.markdown("---")

    # 7. Suppression de localisations
    with st.expander("🗑️ Supprimer une localisation de cet élément"):

        if not df_loca.empty:
            loc_to_remove = st.selectbox(
                "Sélectionner une localisation à retirer :",
                df_loca["LOCALISATION"].unique(),
                format_func=lambda x: f"{x} - {df_loca[df_loca['LOCALISATION'] == x]['LABEL'].iloc[0]}",
                key="remove_loc_select"
            )

            if st.button("❌ Retirer cette localisation", key="remove_loc_btn"):
                df_loca = df_loca[df_loca["LOCALISATION"] != loc_to_remove]

                try:
                    df_loca.to_excel(loca_file, index=False)
                    st.success(f"✅ Localisation `{loc_to_remove}` retirée avec succès.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erreur lors de la suppression : {str(e)}")
        else:
            st.warning("Aucune localisation à supprimer pour cet élément.")

    # 8. Synchronisation et affichage
    st.markdown("---")
    view_mode = st.radio(
        "Mode d'affichage:",
        ["Version actuelle", "Dernière extraction"],
        horizontal=True,
        key="view_mode"
    )


    # Calculer l'arborescence actuelle
    last_genereted = generate_excel_structure(selected_elem, pd.DataFrame(list(locas_schema), columns=["LOCALISATION"]) , filtered_corres, 
                                      data["incident_path"], data["template_path"], data["base_dir"], project)
    current_arbo = compute_current_arbo(selected_elem, pd.DataFrame(list(locas_schema), columns=["LOCALISATION"]) , filtered_corres, 
                                      data["incident_path"], data["template_path"], project)

    
    if st.button("🔄 Synchroniser avec les blocs associés", 
                help="Mettre à jour les localisations selon la schémathèque",
                type="secondary"):
        
        locas_from_blocks = set()
        for bloc_title in associated_blocs["Libellé élément Schémathèque"]:
            bloc = next((b for b in block_codes if b["title"] == bloc_title), None)
            if bloc:
                for _, row in bloc["df"].iterrows():
                    locas_from_blocks.add(extract_clean(row["original"]))
        
        df_loca_updated = pd.DataFrame({
            "LOCALISATION": list(locas_from_blocks),
            "LABEL": [schema_labels.get(loc, "") for loc in locas_from_blocks],
            "SOURCE": "schémathèque"
        })
        
        df_loca_final = pd.concat([
            df_loca_updated,
            df_loca[~df_loca["LOCALISATION"].isin(locas_from_blocks)]
        ]).drop_duplicates(subset=["LOCALISATION"])
        
        df_loca_final.to_excel(loca_file, index=False)
        st.success(f"Synchronisation effectuée : {len(locas_from_blocks)} localisations mises à jour")
        st.rerun()
    
    
    # 9. Affichage des données
    st.markdown("### 📊 Données actuelles")

    if view_mode == "Version actuelle":
        st.markdown("#### Localisations associées à l'élément - Import Localisation GRET")  

        # Construction du tableau initial
        arbo_df = pd.DataFrame([(loc, schema_labels.get(loc, "")) for loc in sorted(locas_schema)],
                            columns=["LOCALISATION", "LABEL"])

        arbo_df.insert(0, "ELEMENT", selected_elem[:4])  # colonne ELEMENT
        arbo_df["ÉTAT"] = ["Actif"] * len(arbo_df)  # valeur par défaut

        # Ajout de la colonne "UET ?" (indicateur de renseignement)
        def get_uet_status(loc):
            loc_str = str(loc)
            row = data["corres_path"][data["corres_path"]["Code Loca"].astype(str) == loc_str]
            if not row.empty and uet_projet in row.columns:
                uet_val = row[uet_projet].values[0]
                if pd.notna(uet_val) and str(uet_val).strip() and str(uet_val).strip().lower() != "nan":
                    return "Renseigné"
            return "Non renseigné"

        arbo_df["UET ?"] = arbo_df["LOCALISATION"].apply(get_uet_status)

        head_cols = st.columns([1.5, 2, 3, 2, 2])
        with head_cols[0]:
            st.text("ELEMENT")
        with head_cols[1]:
            st.text("LOCALISATION")
        with head_cols[2]:
            st.text("LIBELLE")
        with head_cols[3]:
            st.text("ETAT")
        with head_cols[4]:
            st.text("UET ?")

        # Affichage + sélection de l'état ligne par ligne
        for i in range(len(arbo_df)):
            cols = st.columns([1.5, 2, 3, 2, 2])
            with cols[0]:
                st.markdown(f"**{arbo_df.at[i, 'ELEMENT']}**")
            with cols[1]:
                st.markdown(f"`{arbo_df.at[i, 'LOCALISATION']}`")
            with cols[2]:
                st.markdown(arbo_df.at[i, "LABEL"])
            with cols[3]:
                arbo_df.at[i, "ÉTAT"] = st.selectbox(
                    "",
                    options=["Actif", "Obsolète"],
                    key=f"etat_{i}",
                    index=0
                )
            with cols[4]:
                st.markdown(f"🛈 {arbo_df.at[i, 'UET ?']}")

        # Vérification des UET avant export
        all_uet_ok = arbo_df["UET ?"].eq("Renseigné").all()


        # Export Excel (sans colonne "UET ?")
        export_df = arbo_df[["ELEMENT", "LOCALISATION", "LABEL", "ÉTAT"]]
        output = BytesIO()
        export_df.to_excel(output, index=False)
        output.seek(0)

        # Bouton de téléchargement conditionné aux UET renseignées
        if not all_uet_ok:
            st.download_button(
                label="⬇️ Télécharger le fichier Excel",
                data=output,
                file_name=f"{selected_elem}_Import_Loca.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                disabled=True
            )
            st.info("❌ Vous devez renseigner toutes les UET pour pouvoir télécharger ce fichier.")
        else:
            st.download_button(
                label="⬇️ Télécharger le fichier Excel",
                data=output,
                file_name=f"{selected_elem}_Import_Loca.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                disabled=False
            )


    else:
        # Dernière extraction
        extractions_dir = os.path.join(data["base_dir"], "Extractions")
        output_path = os.path.join(extractions_dir, f"{selected_elem}_Arborescence_GRET.xlsx")

        if os.path.exists(output_path):
            df_last = pd.read_excel(output_path)
            st.info(f"Dernière extraction enregistrée : {os.path.basename(output_path)}")
            st.dataframe(df_last)
        else:
            st.warning("Aucune extraction précédente disponible pour cet élément")


    # 10. Génération Excel
    st.markdown("---")
    st.markdown("### 🧾 Génération de l'arborescence")
    if missing_uet:
        st.warning(f"Attention: {len(missing_uet)} localisations sans UET ne seront pas incluses")

    if view_mode == "Version actuelle":
        current_arbo = current_arbo[pd.notna(current_arbo["UET imputée"]) & (current_arbo["UET imputée"].str.strip() != "nan")]
        st.dataframe(current_arbo)
        Check = 0
    else : 
        try :
            st.dataframe(pd.read_excel(last_genereted[last_genereted["UET imputée"] != "nan" and not pd.isna(last_genereted["UET imputée"])]))
            Check = 0
        except :
            st.info("Aucun fichier trouvé.")
            Check = 1
    
    if Check == 0 :
        # Ajout des boutons de generate_excel_structure ici
        col1, col2 = st.columns(2)
        with col1:
            # Bouton pour valider et enregistrer dans Extractions
            if st.button("💾 Valider les modifications", 
                        help="Enregistre définitivement dans le dossier Extractions",
                        type="primary"):
                current_arbo.to_excel(output_path, index=False)
                st.success(f"✅ Fichier enregistré dans : {output_path}")
                st.rerun()
        
        with col2:
            # Bouton de téléchargement (Seulement si toutes les UET sont renseignées)
            output = BytesIO()
            current_arbo.to_excel(output, index=False)
            output.seek(0)
            if missing_uet: 
                st.download_button(
                    label="⬇️ Télécharger le fichier Excel",
                    data=output,
                    file_name=f"{selected_elem}_Arborescence_GRET.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    disabled=True
                )
                st.info("Vous devez renseigner toutes les UET pour pouvoir télécharger ce fichier")
            else :
                st.download_button(
                    label="⬇️ Télécharger le fichier Excel",
                    data=output,
                    file_name=f"{selected_elem}_Arborescence_GRET.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    disabled=False
                )

    st.markdown("---")



def generate_excel_structure(selected_elem, df_loca, df_corres, df_incidents, template, base_dir, project):
    uet_projet = " ".join(["UET", project])
    template_df = template
    existing_df = template_df.copy()
    
    rows = []
    to_drop = []
    exceptions = ["HK01", "SK01", "RK01", "BK01", "MK01", "CK01", "TK01", "1791", "7935"]
    incident_codes = df_incidents["Code Incident"].dropna().unique()
    
    # Construire les nouvelles lignes
    for inc in incident_codes:
        if inc in exceptions:
            continue
            
        for loca in df_loca["LOCALISATION"].astype(str).unique():
            uets = df_corres[df_corres["Code Loca"].astype(str).str.strip() == loca][uet_projet].unique()
            
            for uet in uets:
                already = (
                    (existing_df["INCIDENT"].astype(str).str.strip() == inc) &
                    (existing_df["LOCALISATION"].astype(str).str.strip() == loca) &
                    (existing_df["UET imputée"] == uet)
                ).any()
                
                sub_no_inc = (
                    (existing_df["INCIDENT"].astype(str).str.strip() == inc) &
                    (existing_df["LOCALISATION"].astype(str).str.strip() == loca) &
                    (existing_df["UET imputée"] != uet)
                )
                
                if not already:
                    rows.append({
                        "ELEMENT": selected_elem,
                        "INCIDENT": inc,
                        "LOCALISATION": loca,
                        "Position I/E": None,
                        "OBJET": None,
                        "CRITERE": None,
                        "ZONE": None,
                        "UET imputée": uet,
                        "SECTEUR": "M",
                        "CHAINE": None,
                        "TECHNIQUE": "S",
                        "CODE RETOUCHE": "RELE",
                        "TPS RETOUCHE": "0",
                        "EFFET CLIENT": "O",
                        "REGROUPEMENT": "ELEC",
                        "METIER": "ELECTRICIT"
                    })
                to_drop.extend(existing_df[sub_no_inc].index.tolist())

    # Ajouter incidents exceptionnels automatiquement
    auto_incidents = [
        {"ELEMENT": selected_elem, "INCIDENT": code, "UET imputée": ("RET" if code != "DENR" else "DIV"), "LOCALISATION": "", 
        "SECTEUR": "M", "CODE RETOUCHE": "RELE", "TPS RETOUCHE": "0", "EFFET CLIENT": "O", "REGROUPEMENT": "ELEC", "METIER": "ELECTRICIT", "TECHNIQUE": "S"}
        for code in exceptions
    ]

    df_auto = pd.DataFrame(auto_incidents)

    # Assemblage final du DataFrame
    existing_df = pd.concat([existing_df, df_auto], ignore_index=True) if 'df_auto' in locals() else existing_df
    existing_df = existing_df.drop(index=list(set(to_drop))).drop_duplicates()
    new_lines = pd.DataFrame(rows).drop_duplicates()
    current_df = pd.concat([new_lines, existing_df], axis=0, ignore_index=True).drop_duplicates()

    # Filtrage final
    valid_inc = list(incident_codes) + exceptions
    current_df = current_df[
        (current_df["INCIDENT"].astype(str).str.strip().isin(valid_inc)) &
        ((current_df["LOCALISATION"].astype(str).str.strip().notna()) | (current_df["INCIDENT"].astype(str).str.strip().isin(exceptions)))
    ]

    # Créer le dossier Extractions s'il n'existe pas
    extractions_dir = os.path.join(base_dir, "Extractions")
    os.makedirs(extractions_dir, exist_ok=True)
    output_path = os.path.join(extractions_dir, f"{selected_elem}_Arborescence_GRET.xlsx")
    
    return output_path


def compute_current_arbo(selected_elem, df_loca, df_corres, df_incidents, template, project):
    uet_projet = " ".join(["UET", project])
    template_df = template
    existing_df = template_df.copy()
    
    rows = []
    to_drop = []
    exceptions = ["HK01", "SK01", "RK01", "BK01", "MK01", "CK01", "TK01", "1791", "7935"]
    incident_codes = df_incidents["Code Incident"].dropna().unique()
    
    # Construire les nouvelles lignes
    for inc in incident_codes:
        if inc in exceptions:
            continue
            
        for loca in df_loca["LOCALISATION"].astype(str).unique():
            uets = df_corres[df_corres["Code Loca"].astype(str).str.strip() == loca][uet_projet].unique()
            
            for uet in uets:
                already = (
                    (existing_df["INCIDENT"].astype(str).str.strip() == inc) &
                    (existing_df["LOCALISATION"].astype(str).str.strip() == loca) &
                    (existing_df["UET imputée"] == uet)
                ).any()
                
                sub_no_inc = (
                    (existing_df["INCIDENT"].astype(str).str.strip() == inc) &
                    (existing_df["LOCALISATION"].astype(str).str.strip() == loca) &
                    (existing_df["UET imputée"] != uet)
                )
                
                if not already:
                    rows.append({
                        "ELEMENT": selected_elem,
                        "INCIDENT": inc,
                        "LOCALISATION": loca,
                        "Position I/E": None,
                        "OBJET": None,
                        "CRITERE": None,
                        "ZONE": None,
                        "UET imputée": uet,
                        "SECTEUR": "M",
                        "CHAINE": None,
                        "TECHNIQUE": "S",
                        "CODE RETOUCHE": "RELE",
                        "TPS RETOUCHE": "0",
                        "EFFET CLIENT": "O",
                        "REGROUPEMENT": "ELEC",
                        "METIER": "ELECTRICIT"
                    })
                to_drop.extend(existing_df[sub_no_inc].index.tolist())

    # Ajouter incidents exceptionnels automatiquement
    auto_incidents = [
        {"ELEMENT": selected_elem, "INCIDENT": code, "UET imputée": ("RET" if code != "DENR" else "DIV"), "LOCALISATION": "", 
        "SECTEUR": "M", "CODE RETOUCHE": "RELE", "TPS RETOUCHE": "0", "EFFET CLIENT": "O", "REGROUPEMENT": "ELEC", "METIER": "ELECTRICIT", "TECHNIQUE":"S"}
        for code in exceptions
    ]

    df_auto = pd.DataFrame(auto_incidents)

    # Assemblage final du DataFrame
    existing_df = pd.concat([existing_df, df_auto], ignore_index=True) if 'df_auto' in locals() else existing_df
    existing_df = existing_df.drop(index=list(set(to_drop))).drop_duplicates()
    new_lines = pd.DataFrame(rows).drop_duplicates()
    current_df = pd.concat([new_lines, existing_df], axis=0, ignore_index=True).drop_duplicates()

    # Filtrage final
    valid_inc = list(incident_codes) + exceptions
    current_df = current_df[
        (current_df["INCIDENT"].astype(str).str.strip().isin(valid_inc)) &
        ((current_df["LOCALISATION"].astype(str).str.strip().notna()) | (current_df["INCIDENT"].astype(str).str.strip().isin(exceptions)))
    ]    
    return current_df

# ==============================================================================
# 9. Mode "Comparaison"
# ==============================================================================
def show_schema_comparison(base_dir, current_blocks):
    st.header("🔍 Comparaison de schémathèques")
    
    HISTORY_DIR = os.path.join(base_dir, "schema_history")
    index = load_index(os.path.join(HISTORY_DIR, "index.json"))
    if not index:
        st.warning("Aucune schémathèque historique disponible pour la comparaison.")
        return
    
    schema_files = [v["filename"] for k, v in index.items()]
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Schémathèque courante")
        st.info(f"Blocs: {len(current_blocks)}")
        current_titles = [b["title"] for b in current_blocks]
        
    with col2:
        st.subheader("Schémathèque de référence")
        selected_file = st.selectbox(
            "Sélectionner une schémathèque historique",
            schema_files,
            key="compare_select"
        )
        
        if selected_file:
            selected_path = os.path.join(HISTORY_DIR, selected_file)
            with open(selected_path, "r", encoding="utf-8") as f:
                schema_text = f.read()
            reference_blocks, _ = parse_schema(schema_text)
            reference_titles = [b["title"] for b in reference_blocks]
            st.info(f"Blocs: {len(reference_blocks)}")
    
    if selected_file:
        # Calcul des différences
        common = set(current_titles) & set(reference_titles)
        only_current = set(current_titles) - set(reference_titles)
        only_reference = set(reference_titles) - set(current_titles)
        
        st.subheader("Résultats de la comparaison")
        cols = st.columns(3)
        cols[0].metric("Blocs communs", len(common))
        cols[1].metric("Uniquement dans courant", len(only_current))
        cols[2].metric("Uniquement dans référence", len(only_reference))
        
        # Détails des différences
        with st.expander("Détails des blocs communs"):
            st.write(list(common))
            
        with st.expander("Détails des blocs uniquement dans la schémathèque courante"):
            st.write(list(only_current))
            
        with st.expander("Détails des blocs uniquement dans la schémathèque de référence"):
            st.write(list(only_reference))
        
        # Comparaison détaillée pour un bloc spécifique
        st.subheader("Comparaison détaillée d'un bloc")
        selected_block = st.selectbox("Choisir un bloc commun", list(common))
        
        current_block = next(b for b in current_blocks if b["title"] == selected_block)
        reference_block = next(b for b in reference_blocks if b["title"] == selected_block)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Version courante**")
            st.dataframe(current_block["df"])
        
        with col2:
            st.markdown("**Version de référence**")
            st.dataframe(reference_block["df"])
        
        # Calcul des différences de contenu
        current_content = "\n".join([f"{row['original']};{row['label']}" for _, row in current_block["df"].iterrows()])
        reference_content = "\n".join([f"{row['original']};{row['label']}" for _, row in reference_block["df"].iterrows()])
        
        d = Differ()
        diff = list(d.compare(
            reference_content.splitlines(),
            current_content.splitlines()
        ))
        
        st.subheader("Différences de contenu")
        for line in diff:
            if line.startswith('+ '):
                st.markdown(f"<div style='color:green;'>{line}</div>", unsafe_allow_html=True)
            elif line.startswith('- '):
                st.markdown(f"<div style='color:red;'>{line}</div>", unsafe_allow_html=True)
            else:
                st.write(line)

# ==============================================================================
# 10. Fonctions d'automatisation
# ==============================================================================
def auto_link_blocks(block_codes, data, project, reference_titles=None):
    """
    Crée automatiquement des liens entre blocs et fonctions
    en utilisant la similarité structurelle.
    """
    project = project
    new_links = []
    
    # Titres déjà présents
    existing_titles = set(data["blocs_fonctions_path"]["Libellé élément Schémathèque"].astype(str))
    
    for bloc in block_codes:
        title = bloc["title"]
        
        # On passe si déjà lié ou hors référence
        if title in existing_titles or (reference_titles and title not in reference_titles):
            continue
        
        # On récupère prop, score global, similar_sources et bloc_scores
        prop, _, similar_sources, bloc_scores = propagate_to_similar(
            title,
            data["blocs_fonctions_path"],
            data["base_dir"],
            project,
            reference_titles=reference_titles,
            existing_functions=set()
        )
        
        # Si on a des recommandations
        if prop and "TOUTES LES FONCTIONS SIMILAIRES" in prop:
            # On prend la première fonction proposée
            main_function = prop["TOUTES LES FONCTIONS SIMILAIRES"][0]
            
            # On récupère son intitulé
            intitule = (
                data["element_path"]
                    .loc[data["element_path"]["ELEMENT"] == main_function, "INTITULE"]
                    .values
            )
            intitule = intitule[0] if len(intitule) else ""
            
            new_links.append({
                "Code élément": main_function,
                "Libellé élément Schémathèque": title,
                "Libéllé Retenu": f"FONCTION {intitule}" if intitule else ""
            })
    
    # Si on a créé des liens, on les ajoute puis on sauvegarde
    if new_links:
        data["blocs_fonctions_path"] = pd.concat([
            data["blocs_fonctions_path"],
            pd.DataFrame(new_links)
        ], ignore_index=True)
        
        data["blocs_fonctions_path"].to_excel(
            os.path.join(data["base_dir"], f"data/blocs_fonctions_{project}.xlsx"),
            index=False
        )
        return len(new_links)
    
    return 0



# ==============================================================================
# 11. Application principale
# ==============================================================================
def main():
    st.set_page_config(page_title="GRET MAJ AUTO", layout="wide")
    st.title("📄 GRET MAJ AUTO")
    
    auth_user()

    base_dir = "."

    schema_expansion = True
    
    with st.sidebar.expander("**📃 Gestion Schémathèques**", expanded=schema_expansion):
        # Gestion des schémathèques
        sdata = manage_schema_history(base_dir)
        if st.session_state.get("schema_data") :
            schema_data = st.session_state.get("schema_data")
        else :
            schema_data = sdata
        reference_titles = None

        # schema_data = st.session_state.get("schema_data")
        schema_text = st.session_state.get("schema_text")
        project = st.session_state.get("project")
        found_localisations = st.session_state.get("found_localisations")
        index = st.session_state.get("index")
        
        if schema_data:  # Vérifie si des données de schéma sont disponibles

            if schema_data and len(schema_data) == 4:
                schema_text, found_localisations, index, project = schema_data

                # Sauvegarde dans session_state
                st.session_state["schema_text"] = schema_text
                st.session_state["project"] = project
                st.session_state["found_localisations"] = found_localisations
                st.session_state["index"] = index
                st.session_state["schema_data"] = schema_data

                uet = " ".join(["UET", project])
                # Sélection de la schémathèque de référence
                st.subheader("📌 Schémathèque de référence")
                if index:
                    sorted_items = sorted(index.items(), key=lambda x: x[1]["timestamp"], reverse=True)
                    options = [v["filename"] for k, v in sorted_items]
                    selected_reference = st.selectbox(
                        "Choisir une schémathèque de référence",
                        ["Aucune"] + options,
                        key="reference_select"
                    )
                    
                    if selected_reference != "Aucune":
                        schema_expansion = False
                        reference_path = os.path.join(base_dir, "schema_history", selected_reference)
                        with open(reference_path, "r", encoding="utf-8") as f:
                            reference_text = f.read()
                        reference_blocks, _ = parse_schema(reference_text)
                        reference_titles = {b["title"] for b in reference_blocks}
                        st.success(f"Référence chargée: {selected_reference}")
                        schema_expansion = False
                else:
                    st.info("Aucune schémathèque historique disponible")
            else:
                # schema_text, found_localisations = None, {}
                st.info("Erreur de chargement dans les données du schéma")
        
            # Parsing de la schémathèque
            block_codes, clean2blocks = parse_schema(schema_text) if schema_text else ([], {})

            # Chargement des données
            data = load_common_data(project, base_dir)
            data["base_dir"] = base_dir  # Ajout du base_dir au dictionnaire data

            # Bouton d'automatisation
            if schema_text and st.button("🤖 Automatiser les liens blocs-fonctions", type="primary"):
                with st.spinner("Création des liens en cours..."):
                    count = auto_link_blocks(block_codes, data, project, reference_titles)
                    st.success(f"{count} nouveaux liens créés !")
                    # Recharger les données après modification
                    data["blocs_fonctions_path"] = reload_dataframe(os.path.join(base_dir, f"data/blocs_fonctions_{project}.xlsx"))
                    st.rerun()


    # Sélection du mode
    st.sidebar.markdown("---")
    mode = st.sidebar.radio(
        "Mode:",
        ["Explorer Blocs", "Gestion Élément", "Comparaison"],
        horizontal=True
    )

    if schema_data:  # Vérifie si des données de schéma sont disponibles
        if len(schema_data) == 4:
    
            # Affichage du mode sélectionné
            if mode == "Explorer Blocs":
                show_block_explorer(block_codes, data, project, reference_titles)
            elif mode == "Gestion Élément":
                show_element_manager(block_codes, clean2blocks, data, project)
            elif mode == "Comparaison":
                show_schema_comparison(base_dir, block_codes)
            
            # Affichage des sections de la sidebar
            show_sidebar_sections(data, project, found_localisations)
    
    st.sidebar.markdown("---")

    st.sidebar.markdown(
    "<p style='color:#888; font-size:12px; font-style:italic; text-align:center;'>@author : Brandon C. Etocha</p>",
    unsafe_allow_html=True
)

if __name__ == "__main__":
    main()
