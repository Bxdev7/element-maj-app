import streamlit as st
import pandas as pd
import os
from io import BytesIO
import hashlib
import json
from datetime import datetime
import re
from difflib import SequenceMatcher

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

import os
import pandas as pd
from difflib import SequenceMatcher

# ============================================================================== 
# 1. Fonctions de recommandation enrichies
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
    threshold: float = 0.85,
    path_weight: float = 0.6,
    name_weight: float = 0.4
) -> dict[str, list[str]]:
    """
    Compare avec TOUS les blocs historiques et regroupe toutes les fonctions des blocs similaires.
    Adapté pour la nouvelle structure du fichier blocs_fonctions.
    """
    prop = {}
    all_functions = set()
    
    # Extraire les parties du bloc cible
    target_parts = target.split('/')
    target_path = '/'.join(target_parts[:-1])
    target_name = target_parts[-1]
    
    # Parcourir tous les blocs existants
    for _, row in df_blocs_fonctions.iterrows():
        oth = row["Libellé élément Schémathèque"]
        if oth == target or pd.isna(oth):
            continue
            
        oth_parts = str(oth).split('/')
        oth_path = '/'.join(oth_parts[:-1])
        oth_name = oth_parts[-1]
        
        # Calcul des similarités pondérées
        path_sim = SequenceMatcher(None, target_path.lower(), oth_path.lower()).ratio() * path_weight
        name_sim = SequenceMatcher(None, target_name.lower(), oth_name.lower()).ratio() * name_weight
        combined_score = path_sim + name_sim
        
        if combined_score >= threshold:
            # Ajouter la fonction associée à ce bloc similaire
            f = row["Code élément"]
            if isinstance(f, str):
                all_functions.add(f.strip())
    
    # Retourner toutes les fonctions groupées
    if all_functions:
        prop["TOUTES LES FONCTIONS SIMILAIRES"] = sorted(all_functions)
    
    return prop

# ==============================================================================
# 2. Config utilisateur & authentification
# ==============================================================================
CONFIG_FILE = os.path.expanduser("~/.elem_maj_config.json")

def load_user_config():
    if os.path.exists(CONFIG_FILE):
        try: 
            return json.load(open(CONFIG_FILE))
        except: 
            return {}
    return {}

def save_user_config(conf):
    with open(CONFIG_FILE, "w") as f:
        json.dump(conf, f)

def init_config_sidebar():
    conf = load_user_config()
    if "base_dir" not in conf:
        st.sidebar.subheader("⚙️ Configuration initiale")
        path = st.sidebar.text_input(
            "Chemin local du dossier element-maj-app",
            placeholder=r"C:\Users\X\OneDrive – Renault\element‑maj‑app",
            key="init_path"
        )
        if st.sidebar.button("✅ Valider le chemin"):
            if os.path.isdir(path):
                conf["base_dir"] = path
                save_user_config(conf)
                st.sidebar.success("Chemin enregistré !")
                rerun()
            else:
                st.sidebar.error("Le dossier n'existe pas, vérifiez le chemin.")

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

def manage_schema_history(base_dir: str):
    HISTORY_DIR = os.path.join(base_dir, "schema_history")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    INDEX_FILE = os.path.join(HISTORY_DIR, "index.json")
    
    index = load_index(INDEX_FILE)
    
    # Upload de nouvelle schémathèque
    uploaded = st.sidebar.file_uploader("📁 Télécharger un fichier .txt de schémathèque", type="txt")
    new_filename = st.sidebar.text_input("📝 Nom du fichier (sans extension)", key="custom_filename")
    
    if uploaded is not None:
        sch_content = uploaded.read().decode("utf-8")
        h = compute_hash(sch_content)

        if h not in index:
            if not new_filename:
                st.sidebar.error("❌ Merci de donner un nom de fichier avant d'enregistrer.")
                st.stop()

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{new_filename.replace(' ', '_')}_{ts}.txt"
            path_txt = os.path.join(HISTORY_DIR, fname)

            with open(path_txt, "w", encoding="utf-8") as f_txt:
                f_txt.write(sch_content)

            index[h] = {"filename": fname, "timestamp": ts}
            save_index(index, INDEX_FILE)
            st.sidebar.success("✅ schémathèque ajoutée à l'historique !")
            new_filename = ""
            rerun()
        else:
            st.sidebar.info("ℹ️ Cette schémathèque est déjà enregistrée dans l'historique.")

    # Sélection d'une schémathèque existante
    if not index:
        st.sidebar.info("ℹ️ Aucune schémathèque enregistrée pour le moment.")
        return None
    
    sorted_items = sorted(index.items(), key=lambda x: x[1]["timestamp"], reverse=True)
    options = [v["filename"] for k, v in sorted_items]
    
    selected_filename = st.sidebar.selectbox(
        "📜 Choisir une schémathèque existante", 
        options, 
        index=0
    )

    selected_path = os.path.join(HISTORY_DIR, selected_filename)
    with open(selected_path, "r", encoding="utf-8") as f:
        schema_text = f.read()
    
    st.sidebar.success(f"✅ schémathèque chargée : {selected_filename}")
    
    # Détection des nouvelles localisations
    lines = schema_text.splitlines()
    found_localisations = {}

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

    return schema_text, found_localisations

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
        if len(blk.splitlines()[0].strip()) < 2:
            title = blk.splitlines()[1].strip()
        else:
            title = blk.splitlines()[0].strip()
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
        
        if block_codes[0]["title"].startswith("LIST"):
            block_codes = block_codes[1:]

    return block_codes, clean2blocks

# ==============================================================================
# 5. Chargement des données
# ==============================================================================
def load_common_data(base_dir: str):
    data_paths = {
        "incident_path": os.path.join(base_dir, "data/incidents.xlsx"),
        "element_path": os.path.join(base_dir, "data/elements.xlsx"),
        "corres_path": os.path.join(base_dir, "data/localisation_uet.xlsx"),
        "blocs_fonctions_path": os.path.join(base_dir, "data/blocs_fonctions.xlsx"),
        "template_path": os.path.join(base_dir, "data/template.xlsx"),
        "localisation_folder": os.path.join(base_dir, "data/localisations")
    }
    
    data = {}
    for name, path in data_paths.items():
        if "folder" in name:
            os.makedirs(path, exist_ok=True)
            data[name] = path
        else:
            data[name] = reload_dataframe(path)
    
    # Nettoyage des dataframes
    for df_name in ["incident_path", "element_path", "corres_path", "blocs_fonctions_path"]:
        if isinstance(data[df_name], pd.DataFrame):
            data[df_name] = clean_dataframe(data[df_name])
    
    return data

# ==============================================================================
# 6. Fonctions pour la sidebar
# ==============================================================================
def show_sidebar_sections(data, found_localisations=None):
    """Affiche toutes les sections de la sidebar"""
    st.sidebar.markdown("---")
    
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
                        uet = st.text_input("UET", key=f"new_uet_{code}", placeholder="Ex: RET")
                        if uet:
                            uet_mapping[code] = uet
                
                # Boutons de validation
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Enregistrer UET", type="primary"):
                        if uet_mapping:
                            new_entries = [{
                                "Code Loca": code,
                                "UET": uet,
                                "Famille": "",
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
        new_uet = st.text_input("UET", value=edit_data["UET"], key="edit_loca_uet")

        if st.button("💾 Enregistrer les modifications", key="edit_loca_btn"):
            try:
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == loca_to_edit, "Code Loca"] = new_code
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == new_code, "Libellé Long Loca"] = new_label
                data["corres_path"].loc[data["corres_path"]["Code Loca"] == new_code, "UET"] = new_uet
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
def show_block_explorer(block_codes, data):
    mapping = charger_correspondances_fonctions()
    all_titles = [b["title"] for b in block_codes]
    
    st.subheader("🔍 Explorer les blocs de la schémathèque")
    
    nb_total = len(block_codes)
    current_titles = {b["title"] for b in block_codes}  # Tous les titres actuels
    
    # Modification pour la nouvelle structure du fichier blocs_fonctions
    blocs_rattaches = [b for b in data["blocs_fonctions_path"]["Libellé élément Schémathèque"].astype(str).unique() 
                       if b in current_titles]  # Filtrage
    nb_non_rattaches = nb_total - len(blocs_rattaches)

    st.markdown(f"""
        - Blocs chargés: `{nb_total}`
        - Nouveaux blocs: `{nb_non_rattaches}`
    """)
    
    # Créer une copie du dataframe pour l'affichage
    df_display = data["blocs_fonctions_path"].copy()
    
    # Créer un dictionnaire de correspondance code -> intitulé
    element_dict = dict(zip(
        data["element_path"]["ELEMENT"], 
        data["element_path"]["INTITULE"]
    ))
    
    # Fonction pour formater les fonctions avec leurs intitulés
    def format_functions(row):
        code = row["Code élément"]
        libelle = row["Libéllé Retenu"]
        intitule = element_dict.get(code, "?")
        return f"{code} ({intitule}) - {libelle}"
    
    # Appliquer le formatage
    df_display["FONCTIONS"] = df_display.apply(format_functions, axis=1)
    
    # Afficher le dataframe formaté
    with st.expander("🔍 Voir les associations Bloc - Fonction(s) existantes"):
        st.dataframe(df_display[["Libellé élément Schémathèque", "FONCTIONS"]].rename(
            columns={"Libellé élément Schémathèque": "BLOC"}), 
            height=400)
    
    # Créer un dictionnaire de statut des blocs
    bloc_status = {
        title: title in data["blocs_fonctions_path"]["Libellé élément Schémathèque"].values
        for title in all_titles
    }
    
    # Radio button pour le filtre - style similaire à votre sidebar
    filter_type = st.radio(
        "Filtrer les blocs:",
        options=["Tous", "Avec fonctions", "Sans fonctions"],
        horizontal=True,
        key="bloc_filter"
    )
    
    # Filtrer les titres selon la sélection
    if filter_type == "Avec fonctions":
        filtered_titles = [title for title in all_titles if bloc_status[title]]
    elif filter_type == "Sans fonctions":
        filtered_titles = [title for title in all_titles if not bloc_status[title]]
    else:
        filtered_titles = all_titles
    
    # Afficher le compteur
    st.caption(f"Blocs {filter_type.lower()}: {len(filtered_titles)}")
    
    # Selectbox avec les blocs filtrés
    chosen = st.selectbox(
        "Choisir un bloc à visualiser:", 
        filtered_titles, 
        key="explore_blk_select",
        format_func=lambda x: (
            f"🟢 {x}" if bloc_status[x] else 
            f"🔴 {x} (Nouveau)"
        )
    )
        
    blk_obj = next((b for b in block_codes if b["title"] == chosen), None)
    
    # Rattachements existants - modification pour la nouvelle structure
    exist = data["blocs_fonctions_path"].loc[
        data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen, 
        "Code élément"
    ].tolist()
    
    if not blk_obj:
        st.warning("Bloc non trouvé")
        return
    
    st.dataframe(blk_obj["df"])

    
    if not blk_obj:
        st.warning("Bloc non trouvé")
        return
    
    if exist:
        st.markdown("### ✅ Fonctions rattachées")
        fonctions = exist
        
        # Créer un dataframe pour l'affichage avec case à cocher
        df_exist = pd.DataFrame({
            "Fonction": fonctions,
            "Intitulé": [data["element_path"].loc[data["element_path"]["ELEMENT"] == f, "INTITULE"].values[0] 
                         if f in data["element_path"]["ELEMENT"].values else "Inconnu" 
                         for f in fonctions],
            "Libellé Retenu": data["blocs_fonctions_path"].loc[
                (data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen) & 
                (data["blocs_fonctions_path"]["Code élément"].isin(fonctions)),
                "Libéllé Retenu"
            ].values,
            "Supprimer": [False] * len(fonctions)  # Colonne pour les cases à cocher
        })
        
        # Afficher le tableau avec cases à cocher
        edited_df = st.data_editor(
            df_exist,
            column_config={
                "Supprimer": st.column_config.CheckboxColumn(
                    "Sélectionner",
                    help="Cocher pour supprimer cette association",
                    default=False,
                )
            },
            disabled=["Fonction", "Intitulé", "Libellé Retenu"],
            hide_index=True,
            use_container_width=True
        )
        
        # Bouton de suppression
        if st.button("🗑️ Supprimer les associations sélectionnées", type="secondary"):
            to_keep = edited_df[~edited_df["Supprimer"]]["Fonction"].tolist()
            
            if len(to_keep) == 0:
                # Supprimer tout le bloc si plus aucune fonction
                data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
                    data["blocs_fonctions_path"]["Libellé élément Schémathèque"] != chosen]
            else:
                # Mettre à jour avec les fonctions restantes
                mask = data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen
                data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
                    ~mask | (data["blocs_fonctions_path"]["Code élément"].isin(to_keep))]
            
            data["blocs_fonctions_path"].to_excel(
                os.path.join(data["base_dir"], "data/blocs_fonctions.xlsx"), 
                index=False
            )
            st.success("Suppression effectuée !")
            st.rerun()


    
    # Section Recommandations
    st.markdown("## 🔎 Recommandations")
    
    # 1. Recommandations par mots-clés
    with st.expander("🔍 Par mots-clés", expanded=True):
        direct = recommander_fonctions(chosen, mapping, data["element_path"])
    
    # 2. Recommandations sémantiques
    with st.expander("🤖 Par similarité sémantique", expanded=True):
        sem = recommander_par_intitule(chosen, data["element_path"], threshold=0.4)
    
    # 3. Recommandations par similarité de blocs améliorée
    with st.expander("🔄 Par similarité structurelle", expanded=True):
        prop = propagate_to_similar(chosen, data["blocs_fonctions_path"])
        
        if prop:
            st.info("Suggestions basées sur la similarité structurelle:")
            cols = st.columns(2)
            with cols[0]:
                st.metric("Bloc sélectionné", chosen)
            with cols[1]:
                st.metric("Fonctions similaires trouvées", len(prop.get("TOUTES LES FONCTIONS SIMILAIRES", [])))
            
            # Créer un tableau pour l'affichage
            similar_data = []
            for f in prop.get("TOUTES LES FONCTIONS SIMILAIRES", []):
                intitule = data["element_path"].loc[
                    data["element_path"]["ELEMENT"] == f, "INTITULE"
                ].values[0] if f in data["element_path"]["ELEMENT"].values else "Inconnu"
                
                similar_data.append({
                    "Fonction": f,
                    "Intitulé": intitule
                })
            
            # Afficher sous forme de tableau
            st.dataframe(
                pd.DataFrame(similar_data),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Aucune fonction similaire trouvée. Essayez de réduire le seuil si nécessaire.")
    
    # Gestion des rattachements
    # Créer une liste d'options avec code + intitulé
    elements = data["element_path"].dropna(subset=["ELEMENT", "INTITULE"])
    options = [
        (f"{row['ELEMENT']} - {row['INTITULE']}", row['ELEMENT']) 
        for _, row in elements.iterrows()
    ]
    
    # Extraire les valeurs et labels pour le multiselect
    option_labels = [opt[0] for opt in options]
    option_values = [opt[1] for opt in options]
    
    # Préparer les valeurs par défaut
    defaults = sum(prop.values(), []) if prop else []
    default_indices = [i for i, val in enumerate(option_values) if val in defaults]

    
    selected_labels = st.multiselect(
        "Associer à des éléments:", 
        options=option_labels,
        default=list(dict.fromkeys([option_labels[i] for i in default_indices])),
        key=f"assoc_{chosen}"
    )

    # Élimination des doublons (au cas où)
    selected_labels = list(dict.fromkeys(selected_labels)) 
    
    # Extraire les codes éléments sélectionnés
    selected_codes = [opt[1] for opt in options if opt[0] in selected_labels]
    
    if st.button("✅ Enregistrer les associations", key=f"save_{chosen}"):
        # Récupérer les associations existantes pour ce bloc
        existing_associations = data["blocs_fonctions_path"][
            data["blocs_fonctions_path"]["Libellé élément Schémathèque"] == chosen
        ]
        
        # Fusionner anciennes et nouvelles associations
        if not existing_associations.empty:
            existing_codes = existing_associations["Code élément"].tolist()
            all_codes = list(set(existing_codes + selected_codes))  # Union sans doublons
        else:
            all_codes = selected_codes
        
        # Supprimer l'ancienne entrée si elle existe
        data["blocs_fonctions_path"] = data["blocs_fonctions_path"][
            data["blocs_fonctions_path"]["Libellé élément Schémathèque"] != chosen
        ]
        
        # Ajouter la nouvelle entrée fusionnée
        if all_codes:  # Ne pas ajouter si vide
            for code in all_codes:
                intitule = data["element_path"].loc[
                    data["element_path"]["ELEMENT"] == code, "INTITULE"
                ].values[0] if code in data["element_path"]["ELEMENT"].values else ""
                
                data["blocs_fonctions_path"] = pd.concat([
                    data["blocs_fonctions_path"],
                    pd.DataFrame([{
                        "Code élément": code,
                        "Libellé élément Schémathèque": chosen,
                        "Libéllé Retenu": f"FONCTION {intitule}" if intitule else ""
                    }])
                ], ignore_index=True)
            
            data["blocs_fonctions_path"].to_excel(
                os.path.join(data["base_dir"], "data/blocs_fonctions.xlsx"), 
                index=False
            )
            st.success(f"🔗 Associations mises à jour pour le bloc: {chosen}")
            st.rerun()
        else:
            st.info("Aucune association à enregistrer")


# ==============================================================================
# 8. Mode "Gestion Élément"
# ==============================================================================
def show_element_manager(block_codes, clean2blocks, data):
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
    
    if associated_blocs.empty:
        st.warning("Cet élément n'est associé à aucun bloc")
        return
    
    with st.expander("### 📌 Blocs associés"):
        # Filtrer les blocs associés qui existent dans block_codes
        valid_blocs = [
            bloc_title for bloc_title in associated_blocs["Libellé élément Schémathèque"].unique() 
            if any(b["title"] == bloc_title for b in block_codes)
        ]
        
        if not valid_blocs:
            st.warning("Aucun bloc présent dans la schémathèque chargée à afficher")
            return
        
        selected_bloc = st.selectbox(
            "Choisir un bloc à explorer:",
            valid_blocs,
            format_func=lambda x: f"{x}",
            key="bloc_selector"
        )
        
        # Affichage du contenu du bloc
        bloc_obj = next(b for b in block_codes if b["title"] == selected_bloc)
        st.markdown(f"**Contenu du bloc {selected_bloc}**")
        st.dataframe(bloc_obj["df"])
    
    # 2. Gestion des localisations
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
    
    # 3. Extraction des localisations des blocs
    locas_schema = set()
    schema_labels = {}
    for bloc_title in associated_blocs["Libellé élément Schémathèque"]:
        bloc = next((b for b in block_codes if b["title"] == bloc_title), None)
        if bloc:
            for _, row in bloc["df"].iterrows():
                code = extract_clean(row["original"])
                locas_schema.add(code)
                schema_labels[code] = row["label"]
    
    # 4. Gestion des UET manquantes
    filtered_corres = data["corres_path"][data["corres_path"]["Code Loca"].isin(df_loca["LOCALISATION"].astype(str))]
    missing_uet = [loc for loc in df_loca["LOCALISATION"].astype(str).unique() 
                  if loc not in filtered_corres["Code Loca"].values]
    
    if missing_uet:
        with st.expander("⚠️ Configuration requise - UET manquantes", expanded=True):
            st.warning(f"{len(missing_uet)} localisations nécessitent une UET")
            
            uet_mapping = {}
            with st.form(key="uet_form"):
                for loc in missing_uet:
                    cols = st.columns([2, 3, 1])
                    with cols[0]:
                        st.text_input("Localisation", value=loc, disabled=True, key=f"disp_{loc}")
                    with cols[1]:
                        st.text_input("UET", key=f"uet_{loc}", placeholder="Ex: RET")
                    with cols[2]:
                        st.caption(f"Label: {schema_labels.get(loc, 'Inconnu')}")
                
                cols = st.columns([1, 1, 3])
                with cols[0]:
                    if st.form_submit_button("💾 Enregistrer", type="primary"):
                        uet_mapping = {
                            loc: st.session_state[f"uet_{loc}"]
                            for loc in missing_uet
                            if st.session_state.get(f"uet_{loc}")
                        }
                        
                        if uet_mapping:
                            new_entries = []
                            for loc, uet in uet_mapping.items():
                                new_entries.append({
                                    "Code Loca": loc,
                                    "UET": uet,
                                    "Famille": "",
                                    "Sous-famille": "",
                                    "Libellé Long Loca": schema_labels.get(loc, "Inconnu")
                                })
                            
                            data["corres_path"] = pd.concat([
                                data["corres_path"],
                                pd.DataFrame(new_entries)
                            ]).drop_duplicates(subset=["Code Loca"], keep="last")
                            
                            data["corres_path"].to_excel(
                                os.path.join(data["base_dir"], "data/localisation_uet.xlsx"),
                                index=False
                            )
                            st.success("UET enregistrées avec succès !")
                            st.rerun()
                        else:
                            st.warning("Aucune UET valide à enregistrer")
                
                st.info("Les localisations avec des UET manquantes ne seront pas incluses dans l'export")

    st.markdown("---")

    # =============================================================================== #
    # ======================== AJOUT MANUEL DE LOCALISATION ========================= #
    # =============================================================================== #
    

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
                    - **UET associée :** {loc_info['UET']}
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
                    new_uet = st.text_input("UET associée*", key="new_loc_uet")
                
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
                            "UET": new_uet,
                            "Famille": "",
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

    # ========== SECTION SUPPRESSION LOCALISATION ==========
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

    # 5. Sélection du mode d'affichage
    st.markdown("---")
    view_mode = st.radio(
        "Mode d'affichage:",
        ["Arborescence schémathèque", "Localisations configurées"],
        horizontal=True,
        key="view_mode"
    )
    
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

    # 7. Affichage des données
    st.markdown("### 📊 Données actuelles")
    
    if view_mode == "Arborescence schémathèque":
        st.markdown("#### 🗺 Localisations des blocs")
        arbo_df = pd.DataFrame([(loc, schema_labels.get(loc, "")) for loc in sorted(locas_schema)],
                             columns=["LOCALISATION", "LABEL"])
        arbo_df["STATUT"] = arbo_df["LOCALISATION"].apply(
            lambda x: "✅ Configuré" if str(x) in filtered_corres["Code Loca"].values else "❌ UET manquante")
        st.dataframe(arbo_df)
    else:
        st.markdown("#### 📝 Localisations configurées")
        st.dataframe(df_loca)
    
    # 8. Génération Excel avec avertissement
    st.markdown("---")
    st.markdown("### 🧾 Génération de l'arborescence")
    if missing_uet:
        st.warning(f"Attention: {len(missing_uet)} localisations sans UET ne seront pas incluses")
    
    generate_excel_structure(selected_elem, df_loca, filtered_corres, 
                           data["incident_path"], data["template_path"], data["base_dir"])
    
def generate_excel_structure(selected_elem, df_loca, df_corres, df_incidents, template, base_dir):
    template_df = template
    existing_df = template_df.copy()
    
    rows = []
    to_drop = []
    exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "TK01", "1791", "7935"]
    incident_codes = df_incidents["Code Incident"].dropna().unique()
    
    # Construire les nouvelles lignes
    for inc in incident_codes:
        if inc in exceptions:
            continue
            
        for loca in df_loca["LOCALISATION"].astype(str).unique():
            uets = df_corres[df_corres["Code Loca"].astype(str).str.strip() == loca]["UET"].unique()
            
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
                        "TECHNIQUE": None,
                        "CODE RETOUCHE": "RELE",
                        "TPS RETOUCHE": "0",
                        "EFFET CLIENT": "O",
                        "REGROUPEMENT": "ELEC",
                        "METIER": "ELECTRICIT"
                    })
                to_drop.extend(existing_df[sub_no_inc].index.tolist())

    # 8) Ajouter incidents exceptionnels automatiquement
    auto_incidents = [
        {"ELEMENT": selected_elem, "INCIDENT": code, "UET imputée": ("RET" if code != "DENR" else "DIV"), "LOCALISATION": "", 
        "SECTEUR": "M", "CODE RETOUCHE": "RELE", "TPS RETOUCHE": "0", "EFFET CLIENT": "0", "REGROUPEMENT": "ELEC", "METIER": "ELECTRICIT"}
        for code in exceptions
    ]

    df_auto = pd.DataFrame(auto_incidents)

    # 9) Assemblage final du DataFrame
    existing_df = pd.concat([existing_df, df_auto], ignore_index=True) if 'df_auto' in locals() else existing_df
    existing_df = existing_df.drop(index=list(set(to_drop))).drop_duplicates()
    new_lines = pd.DataFrame(rows).drop_duplicates()
    current_df = pd.concat([new_lines, existing_df], axis=0, ignore_index=True).drop_duplicates()

    # 10) Filtrage final
    valid_inc = list(incident_codes) + exceptions
    current_df = current_df[
        (current_df["INCIDENT"].astype(str).str.strip().isin(valid_inc)) &
        ((current_df["LOCALISATION"].astype(str).str.strip().notna()) | (current_df["INCIDENT"].astype(str).str.strip().isin(exceptions)))
    ]

    # 11) Export et affichage
    output = BytesIO()
    current_df.to_excel(output, index=False)
    output.seek(0)

    st.subheader("🧾 Aperçu du fichier actuel")
    st.success("✅ Arborescence mise à jour automatiquement")
    st.dataframe(current_df)

    st.download_button(
        label="⬇️ Télécharger le fichier Excel généré",
        data=output,
        file_name=f"{selected_elem}_Arborescence_GRET.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")


    

# ==============================================================================
# 8. Application principale
# ==============================================================================
def main():
    st.set_page_config(page_title="Mise à jour d'élément GRET", layout="wide")
    st.title("📄 Mise à jour d'élément GRET")
    
    # Initialisation config
    init_config_sidebar()
    auth_user()
    
    # Chargement config
    conf = load_user_config()
    if "base_dir" not in conf:
        st.warning("Veuillez configurer le chemin de base dans la sidebar")
        st.stop()
    
    base_dir = conf["base_dir"]
    
    # Gestion des schémathèques
    schema_data = manage_schema_history(base_dir)
    if schema_data:  # Vérifie si des données de schéma sont disponibles
        schema_text, found_localisations = schema_data
    else:
        schema_text, found_localisations = None, {}
    
    # Parsing de la schémathèque
    block_codes, clean2blocks = parse_schema(schema_text)


    # Chargement des données
    data = load_common_data(base_dir)
    data["base_dir"] = base_dir  # Ajout du base_dir au dictionnaire data

    # Sélection du mode
    st.sidebar.markdown("---")
    mode = st.sidebar.radio(
        "Mode:",
        ["Explorer Blocs", "Gestion Élément"],
        horizontal=True
    )
    
    # Affichage du mode sélectionné
    if mode == "Explorer Blocs":
        show_block_explorer(block_codes, data)
    else:
        show_element_manager(block_codes, clean2blocks, data)
    
    # Affichage des sections de la sidebar
    show_sidebar_sections(data, found_localisations)
    


if __name__ == "__main__":
    main()
