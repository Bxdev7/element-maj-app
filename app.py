import streamlit as st
import pandas as pd
import os
from io import BytesIO
import hashlib
import json
from datetime import datetime
import re

st.set_page_config(page_title="Mise à jour d'élément GRET", layout="wide")

def rerun():
    try:
        st.rerun()
    except AttributeError as e:
        # hack pour forcer le rerun sur versions plus anciennes
        st.error(f"Erreur lors du rerun : {e}")

def reload_dataframe(file_path):
    try:
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        st.error(f"Erreur lors du rechargement du fichier : {str(e)}")
        return pd.DataFrame()


def generate_empty_localisations(file_path):
    colonnes = ["LOCALISATION", "LABEL"]
    df_vierge = pd.DataFrame(columns=colonnes)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df_vierge.to_excel(file_path, index=False)
    st.success(f"✅ Fichier généré : {file_path}")
    st.rerun()
    return df_vierge

# Fonction pour extraire et mettre en forme les codes dans la schématèque
#    * XXX-YY -> RXXX
#    * 1234XX -> 1234
#    * 123XX -> 123
#    * ...
def extract_clean(o: str) -> str:
    # print("\n\nExtract & Clean\n")
    # print("code :", o)
    o = o.strip().upper()

    # Cas 1 : 123-XYZ (même si XYZ contient des chiffres comme 3A)
    m1 = re.match(r"^(\d+)-[\w]+$", o)
    if m1:
        result = "R" + m1.group(1)
        # print("-> Cas 1 : ", result)
        return result

    # Cas 2 : 123AA ou 1234AA => extraire la partie numérique
    m2 = re.match(r"^(\d{3,4})[A-Z]+$", o)
    if m2:
        result = m2.group(1)
        # print("-> Cas 2 : ", result)
        return result

    # Cas 3 : cas standard (reprendre la logique de base)
    base = o.split("-", 1)[0].strip()
    m3 = re.match(r"^(\d+)", base)
    if m3:
        result = m3.group(1)
        # print("-> Cas 3 : ", result)
        return str(result)

    # print("-> Cas final : ", base)
    return str(base)


# ————————————————————————————————
# 0. Helpers pour config utilisateur
# ————————————————————————————————
CONFIG_FILE = os.path.expanduser("~/.elem_maj_config.json")
def load_user_config():
    if os.path.exists(CONFIG_FILE):
        try: return json.load(open(CONFIG_FILE))
        except: return {}
    return {}
def save_user_config(conf):
    with open(CONFIG_FILE, "w") as f:
        json.dump(conf, f)

# ————————————————————————————————
# 1. Saisie du chemin racine
# ————————————————————————————————
conf = load_user_config()
if "base_dir" not in conf:
    st.sidebar.subheader("⚙️ Configuration initiale")
    path = st.sidebar.text_input(
        "Chemin local du dossier element-maj-app",
        placeholder=r"C:\Users\X\OneDrive – Renault\element‑maj‑app",
        key="init_path"
    )
    if st.sidebar.button("✅ Valider le chemin"):
        st.sidebar.write("Chemin saisi :", repr(path))
        st.sidebar.write("Existe ? ", os.path.isdir(path))
        parent = os.path.dirname(path)
        if os.path.isdir(parent):
            st.sidebar.write("→ Contenu du dossier parent :", os.listdir(parent))
        else:
            st.sidebar.write("Le dossier parent n’existe pas :", repr(parent))
        if os.path.isdir(path):
            conf["base_dir"] = path
            save_user_config(conf)
            st.sidebar.success("Chemin enregistré !")
            rerun()
        else:
            st.sidebar.error("Le dossier n’existe pas, vérifie le chemin.")

# ————————————————————————————————
# 2. Gestion de l’historique des schématèques
# ————————————————————————————————
SCHEMA_LOG = os.path.join(conf.get("base_dir","data"), "schema_history.xlsx")

def compute_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

@st.cache_data
def load_schema_history(path):
    if os.path.exists(path):
        return pd.read_excel(path, dtype=str)
    else:
        return pd.DataFrame(columns=["hash", "timestamp", "content"])

def save_schema_history(df, path):
    df.to_excel(path, index=False)

# charge l’historique
df_schemas = load_schema_history(SCHEMA_LOG)

# upload ou dernière schématèque
uploaded = st.sidebar.file_uploader("📁 Charger un .txt de schématèque", type="txt")
if uploaded is not None:
    new_content = uploaded.read().decode("utf-8")
elif not df_schemas.empty:
    new_content = df_schemas.sort_values("timestamp").iloc[-1]["content"]
else:
    new_content = ""

schema_input = st.sidebar.text_area(
    "📄 Schématèque (coller ou charger)",
    value=new_content,
    height=200,
    key="schema_input"
)

# si nouveau texte différent, on l’ajoute à l’historique
if schema_input:
    h = compute_hash(schema_input)
    if h not in df_schemas["hash"].values:
        df_schemas = pd.concat([
            df_schemas,
            pd.DataFrame([{
                "hash":      h,
                "timestamp": datetime.now().isoformat(),
                "content":   schema_input
            }])
        ], ignore_index=True)
        save_schema_history(df_schemas, SCHEMA_LOG)
        st.sidebar.success("Nouvelle schématèque enregistrée")


# ————————————————————————————————
# 3. Authentification simple
# ————————————————————————————————
USERS = {"admin":"Admin","acteur":"Acteur"}
if "role" not in st.session_state:
    st.sidebar.subheader("🔐 Connexion")
    user = st.sidebar.selectbox("Profil", ["admin","acteur"], key="login_user")
    pwd  = st.sidebar.text_input("Mot de passe", type="password", key="login_pwd")
    if st.sidebar.button("🔑 Se connecter"):
        if USERS.get(user) == pwd:
            st.session_state.role = user
            st.sidebar.success(f"Connecté en tant que {user}")
            rerun()
        else:
            st.sidebar.error("Identifiants incorrects")
    st.stop()

# ————————————————————————————————
# 4. Initialisation Streamlit et chargement des data
# ————————————————————————————————

st.title("📄 Mise à jour d'élément GRET")

@st.cache_data
def load_data(file_path):
    try:
        df = pd.read_excel(file_path, dtype=str)
        df.columns = df.columns.str.strip()
        return df.applymap(lambda x: x.strip() if isinstance(x,str) else x)
    except Exception as e:
        st.error(f"Erreur chargement {file_path}: {e}")
        return pd.DataFrame()

@st.cache_data
def load_template(file_path):
    try:
        return pd.read_excel(file_path)
    except Exception as e:
        st.error(f"Erreur chargement template: {e}")
        return pd.DataFrame()

base_dir           = conf["base_dir"]
incident_path      = os.path.join(base_dir, "data/incidents.xlsx")
element_path       = os.path.join(base_dir, "data/elements.xlsx")
corres_path        = os.path.join(base_dir, "data/localisation_uet.xlsx")
if "df_corres" not in st.session_state:
    st.session_state.df_corres = pd.read_excel(corres_path, dtype={"Code Loca": str})
template_path      = os.path.join(base_dir, "data/template.xlsx")
localisation_folder= os.path.join(base_dir, "data/localisations")

try :
    df_incidents = load_data(incident_path)
    df_elements  = load_data(element_path)
    df_corres    = load_data(corres_path)
    template     = load_template(template_path)
except Exception as e :
    print("\nPROBLEME : ", e)

def clean_dataframe(df):
    for col in df.columns:
        try: 
            df[col] = df[col].astype(str).str.strip()
        except Exception as e : 
            print("Aïe Aïe Aïe")
            print(f"Problème dans la conversion de {df[col].columns}")
    return df

df_incidents = clean_dataframe(df_incidents)
df_elements  = clean_dataframe(df_elements)
df_corres    = clean_dataframe(df_corres)
# print(df_corres.columns, df_corres.columns.dtype)
filtered_incidents = df_incidents[:-1]


# Chemin du dossier d’historique
HISTORY_DIR = os.path.join(base_dir, "schema_history")
os.makedirs(HISTORY_DIR, exist_ok=True)
INDEX_FILE = os.path.join(HISTORY_DIR, "index.json")

def load_index():
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_index(idx):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def compute_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

# 0) Charger l’index existant
index = load_index()

if uploaded is not None:
    # on lit directement le contenu du upload
    schema_input = uploaded.read().decode("utf-8")
elif index:
    # choisir la dernière entrée
    last_ts, last_meta = max(index.items(), key=lambda x: x[1]["timestamp"])
    schema_file = last_meta["filename"]
    with open(os.path.join(HISTORY_DIR, schema_file), "r", encoding="utf-8") as f:
        schema_input = f.read()
else:
    schema_input = ""
        
# 2) Si nouvauté, on enregistre dans un .txt
if schema_input:
    h = compute_hash(schema_input)
    if h not in index:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{h[:8]}.txt"
        with open(os.path.join(HISTORY_DIR, fname), "w", encoding="utf-8") as f:
            f.write(schema_input)
        index[h] = {"filename": fname, "timestamp": ts}
        save_index(index)
        st.sidebar.success("✅ Nouvelle schématèque enregistrée")

# 3) Pour naviguer dans l’historique, on propose un sélecteur
if index:
    st.sidebar.markdown("#### Historique des schématèques")
    # on trie par timestamp décroissant
    choices = sorted(index.items(), key=lambda x: x[1]["timestamp"], reverse=True)
    display = [f"{meta['timestamp']} — {meta['filename']}" for _, meta in choices]
    sel = st.sidebar.selectbox(
        "Charger une ancienne schématèque",
        display,
        key="hist_schema_select"
    )
    # on recharge la sélection
    sel_fname = sel.split("—")[1].strip()
    with open(os.path.join(HISTORY_DIR, sel_fname), "r", encoding="utf-8") as f:
        schema_input = f.read()

    if schema_input:
        import re

        # Extraction des lignes contenant un code de type "123-3A" ou "XXX-3A"
        lines = schema_input.splitlines()
        pattern = r"([A-Z0-9]+)-\w+\s*;\s*(.+?)(?:;|$)"
        found_localisations = {}

        for line in lines:
            matches = re.findall(pattern, line)
            for code, label in matches:
                if code not in found_localisations:
                    found_localisations[code] = label.strip().upper()

        # Charger localisations existantes dans le fichier de correspondance
        existing_loca_codes = df_corres["Code Loca"].astype(str).str.strip().unique()

        # Localisations absentes (nouvelles)
        new_loca_items = {
            code: label
            for code, label in found_localisations.items()
            if code not in existing_loca_codes
        }

        if new_loca_items:
            count = len(new_loca_items)
            st.sidebar.markdown(f"### 🆕 {count} nouvelle{'s' if count>1 else ''} localisation{'s' if count>1 else ''} détectée{'s' if count>1 else ''}")
            st.sidebar.info("🛠️ Pour chaque localisation, tu peux la renommer, ajuster son code, choisir ses éléments et indiquer l’UET.")
            
            if st.sidebar.button("🔍 Afficher les nouvelles localisations") : 
                all_elements = df_elements["ELEMENT"].tolist()
                for orig_code, orig_label in new_loca_items.items():
                    with st.expander(f"➡️ {orig_code} – {orig_label}"):
                        # 1) Permettre la modification du code et du label
                        new_code = st.sidebar.text_input("✏️ Code localisation :", value=orig_code, key=f"code_mod_{orig_code}")
                        new_label = st.sidebar.text_input("✏️ Libellé localisation :", value=orig_label, key=f"label_mod_{orig_code}")

                        # 2) Choix des éléments
                        choix_elems = st.sidebar.multiselect(
                            "Ajouter cette localisation aux éléments :", 
                            all_elements, 
                            key=f"elems_for_{orig_code}"
                        )

                        # 3) Saisie de l’UET
                        uet = st.sidebar.text_input("🔧 UET associé :", key=f"uet_mod_{orig_code}")

                        # 4) Bouton d’ajout
                        if st.sidebar.button(f"✅ Valider {orig_code}", key=f"valider_{orig_code}"):
                            if not new_code.strip() or not new_label.strip() or not uet.strip():
                                st.sidebar.warning("Code, libellé et UET sont obligatoires.")
                            elif not choix_elems:
                                st.sidebar.warning("Sélectionne au moins un élément.")
                            else:
                                for elem in choix_elems:
                                    loca_file = os.path.join(localisation_folder, f"{elem}_localisations.xlsx")
                                    df_loca_elem = pd.read_excel(loca_file, dtype={"LOCALISATION": str})

                                    # Vérifier doublon
                                    if new_code in df_loca_elem["LOCALISATION"].astype(str).values:
                                        st.sidebar.info(f"{new_code} existe déjà pour {elem}.")
                                    else:
                                        df_loca_elem = pd.concat([
                                            df_loca_elem,
                                            pd.DataFrame([{"LOCALISATION": str(new_code), "LABEL": new_label}])
                                        ], ignore_index=True)
                                        df_loca_elem.to_excel(loca_file, index=False)
                                        st.sidebar.success(f"{new_code} ajouté à {elem}.")

                                # Mettre à jour la correspondance globale
                                if new_code in df_corres["Code Loca"].values:
                                    df_corres.loc[df_corres["Code Loca"] == new_code, ["Libellé Long Loca", "UET"]] = [new_label, uet]
                                else:
                                    df_corres = pd.concat([df_corres, pd.DataFrame([{
                                        "Code Loca": new_code,
                                        "Libellé Long Loca": new_label,
                                        "UET": uet
                                    }])], ignore_index=True)
                                df_corres.to_excel(corres_path, index=False)

            # bouton facultatif pour rafraîchir l’app
            if st.sidebar.button("🔄 Recharger les données après ajout"):
                st.rerun()
        else:
            st.sidebar.sidebar.info("✅ Aucune nouvelle localisation détectée.")



# ========== CHOIX DE L'ÉLÉMENT ==========
st.sidebar.header("Choix de l'élément")
# Rafraîchir les données après modification
df_elements = load_data(element_path)

selected_elem = st.sidebar.selectbox(
    "Choisir un code élément :", 
    df_elements.sort_values(by="ELEMENT")["ELEMENT"].unique(),
    format_func=lambda x: f"{x} - {df_elements[df_elements['ELEMENT'] == x]['INTITULE'].values[0]}"
)
st.sidebar.markdown("### 📋 Visualiser")

# dans la sidebar
if st.sidebar.button("🔍 Voir les correspondances localisation - UET"):
    st.session_state.show_corres_edit = True

if st.session_state.get("show_corres_edit", False):
    st.markdown("### 🔍 Édition des correspondances Loca - UET")
    edited = st.data_editor(
        df_corres,
        num_rows="dynamic",
        use_container_width=True
    )

    # bouton de validation
    if st.button("✅ Enregistrer les modifications"):
        # détection de changement
        if not edited.equals(df_corres):
            # écriture
            edited.to_excel(corres_path, index=False)
            # on invalide le cache pour reload propre
            load_data.clear()
            st.success("📁 Correspondances sauvegardées, rechargement…")
            st.rerun()
        else:
            st.info("📝 Aucune modification à enregistrer.")

    # bouton pour fermer l’éditeur
    if st.button("❌ Fermer l’éditeur"):
        st.session_state.show_corres_edit = False


# ========== Sidebar ==========

# ========== GESTION DES ÉLÉMENTS ==========
st.sidebar.subheader("🧩 Gestion des Éléments")

with st.sidebar.expander("🔍 Voir tous les éléments existants"):
    st.dataframe(df_elements, use_container_width=True)

with st.sidebar.expander("✏️ Modifier un élément existant"):

    # choix du code (brut)
    elem_to_edit = st.selectbox(
        "Choisir un élément à modifier",
        df_elements["ELEMENT"].astype(str).unique(),
        key="edit_elem_select_v2"
    )

    # prends la ligne correspondante, si elle existe
    subset = df_elements.loc[df_elements["ELEMENT"].astype(str) == str(elem_to_edit)]
    if subset.empty:
        st.error(f"Aucun élément trouvé pour le code « {elem_to_edit} »")
    else:
        edit_data = subset.iloc[0]
        # adapte le champ label en fonction du nom exact de ta colonne
        current_label = edit_data.get("INTITULE") or edit_data.get("LIBELLE") or ""
        new_code  = st.text_input("Code",    value=str(edit_data["ELEMENT"]), key="edit_elem_code_v2")
        new_label = st.text_input("Libellé", value=str(current_label),           key="edit_elem_label_v2")

        if st.button("💾 Enregistrer les modifications", key="edit_elem_btn"):
            try:
                # mise à jour
                df_elements.loc[df_elements["ELEMENT"] == elem_to_edit, "ELEMENT"]  = new_code.strip()
                label_col = "INTITULE" if "INTITULE" in df_elements.columns else "LIBELLE"
                df_elements.loc[df_elements["ELEMENT"] == new_code, label_col] = new_label.strip()

                # cast propre
                df_elements["ELEMENT"] = df_elements["ELEMENT"].astype(str).str.strip()
                df_elements[label_col] = df_elements[label_col].astype(str).str.strip()

                # sauv sur le bon fichier !
                try :
                    df_elements.to_excel(element_path, index=False)
                    rerun()
                    st.success("✅ Élément modifié avec succès !")
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")
                

            except Exception as e:
                st.error(f"Erreur lors de la sauvegarde : {e}")



with st.sidebar.expander("➕ Créer un nouvel élément"):
    new_elem_code = st.text_input("Code élément*", help="Doit être unique")
    new_elem_label = st.text_input("Libellé élément*")
    
    if st.button("✅ Créer l'élément"):
        if new_elem_code and new_elem_label:
            if new_elem_code in df_elements["ELEMENT"].values:
                st.error("Ce code élément existe déjà !")
            else:
                # Création du fichier de localisations
                new_loca_file = os.path.join(localisation_folder, f"{new_elem_code}_localisations.xlsx")
                pd.DataFrame(columns=["LOCALISATION", "LABEL"]).to_excel(new_loca_file, index=False)
                
                # Ajout à la liste des éléments
                df_elements = pd.concat([
                    df_elements,
                    pd.DataFrame([{"ELEMENT": new_elem_code, "LIBELLE": new_elem_label}])
                ], ignore_index=True)
                
                try:
                    df_elements.to_excel(element_path, index=False)
                    st.success("Élément créé avec succès !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {str(e)}")
        else:
            st.warning("Les champs marqués d'une * sont obligatoires")

with st.sidebar.expander("🗑️ Supprimer un élément"):
    elem_to_delete = st.selectbox(
        "Choisir un élément à supprimer :",
        df_elements["ELEMENT"].unique(),
        key="delete_elem_select"
    )
    
    if st.button("❌ Confirmer la suppression", key="delete_elem_btn"):
        try:
            # Suppression de l'élément
            df_elements = df_elements[df_elements["ELEMENT"] != elem_to_delete]
            
            # Suppression du fichier de localisations
            loca_file = os.path.join(localisation_folder, f"{elem_to_delete}_localisations.xlsx")
            if os.path.exists(loca_file):
                os.remove(loca_file)
            
            df_elements.to_excel(element_path, index=False)
            st.success("Élément supprimé !")
            st.rerun()
            
        except Exception as e:
            st.error(f"Erreur : {str(e)}")

st.sidebar.markdown("---")
st.sidebar.subheader("📄 Coller une nouvelle schématèque")

# schema_input = st.sidebar.text_area("Colle ici le contenu de la schématèque")



# ========== GESTION DES LOCALISATIONS (SIDEBAR) ==========
st.sidebar.subheader("🗺️ Gestion des Localisations")

with st.sidebar.expander("🔍 Voir toutes les localisations"):
    st.dataframe(df_corres, use_container_width=True)

with st.sidebar.expander("✏️ Modifier une localisation"):
    loca_to_edit = st.selectbox(
        "Choisir un code Loca :",
        df_corres["Code Loca"].unique(),
        key="edit_loca_select_v2"
    )

    # On est sûr qu'il y a au moins une ligne
    edit_data = df_corres.loc[df_corres["Code Loca"] == loca_to_edit].iloc[0]

    new_code  = st.text_input("Code Loca",           value=edit_data["Code Loca"],           key="edit_loca_code_v2")
    new_label = st.text_input("Libellé Long Loca",   value=edit_data["Libellé Long Loca"],   key="edit_loca_label_v2")
    new_uet   = st.text_input("UET",                 value=edit_data["UET"],                 key="edit_loca_uet_v2")

    if st.button("💾 Enregistrer les modifications", key="edit_loca_btn"):
        try:
            # On met à jour **tout** en str, pas de conversion surprise
            df_corres.loc[df_corres["Code Loca"] == loca_to_edit, "Code Loca"]          = new_code
            df_corres.loc[df_corres["Code Loca"] == new_code,     "Libellé Long Loca"] = new_label
            df_corres.loc[df_corres["Code Loca"] == new_code,     "UET"]               = new_uet

            # Sauvegarde
            df_corres.to_excel(corres_path, index=False)

            st.success("Localisation modifiée avec succès !")
            rerun()
        except Exception as e:
            st.error(f"Erreur pendant la mise à jour : {e}")


with st.sidebar.expander("🗑️ Supprimer une localisation"):
    loca_to_delete = st.selectbox(
        "Choisir une localisation à supprimer",
        df_corres["Code Loca"].unique(),
        key="delete_loca_select"
    )
    
    if st.button("❌ Confirmer la suppression", key="delete_loca_btn"):
        try:
            df_corres = df_corres[df_corres["Code Loca"] != loca_to_delete]
            df_corres.to_excel(corres_path, index=False)
            st.success("Localisation supprimée!")
            try:
                # code suppression
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de la suppression : {str(e)}")
        except Exception as e:
            st.error(f"Erreur: {str(e)}")


# ========== GESTION DES INCIDENTS ==========
st.sidebar.subheader("🛠️ Gestion des Incidents")

with st.sidebar.expander("✏️ Modifier les incidents existants"):
    selected_incident = st.selectbox("Choisir un incident à modifier :", df_incidents["Code Incident"])
    new_label = st.text_input("Nouveau libellé", value=df_incidents[df_incidents["Code Incident"] == selected_incident]["Libellé incident"].values[0])
    if st.button("✅ Modifier l’incident"):
        df_incidents.loc[df_incidents["Code Incident"] == selected_incident, "Libellé Incident"] = new_label
        df_incidents.to_excel(incident_path, index=False)
        st.success("Incident modifié avec succès.")
        try:
            # code suppression
            rerun()
        except Exception as e:
            st.error(f"Erreur lors de la suppression : {str(e)}")

with st.sidebar.expander("➕ Ajouter un nouvel incident"):
    new_code = st.text_input("Code Incident à ajouter")
    new_lib = st.text_input("Libellé Incident")
    if st.button("➕ Ajouter l’incident"):
        if new_code and new_lib:
            df_incidents = df_incidents.append({"Code Incident": new_code, "Libellé Incident": new_lib}, ignore_index=True)
            df_incidents.to_excel(incident_path, index=False)
            st.success("Incident ajouté avec succès.")
            try:
                # code suppression
                rerun()
            except Exception as e:
                st.error(f"Erreur lors de la suppression : {str(e)}")
        else:
            st.warning("Merci de remplir les deux champs.")

with st.sidebar.expander("❌ Supprimer un incident"):
    incident_to_delete = st.selectbox("Sélectionner un incident à supprimer :", df_incidents["Code Incident"])
    if st.button("🗑️ Supprimer l’incident"):
        df_incidents = df_incidents[df_incidents["Code Incident"] != incident_to_delete]
        df_incidents.to_excel(incident_path, index=False)
        st.success("Incident supprimé.")
        try:
            # code suppression
            st.sidebar.rerun()
        except Exception as e:
            st.error(f"Erreur lors de la suppression : {str(e)}")

    # =============================================================================== #
    # ------------------------------------------------------------------------------- #
    # ------------------------------- Page Principale ------------------------------- #
    # ------------------------------------------------------------------------------- #
    # =============================================================================== #

if selected_elem:
    loca_file = os.path.join(localisation_folder, f"{selected_elem}_localisations.xlsx")
    st.session_state.df_corres.to_excel(corres_path, index=False)
    df_corres = reload_dataframe(corres_path)
    df_loca = reload_dataframe(loca_file)
    if "df_corres" not in st.session_state:
        st.session_state.df_corres = pd.read_excel(corres_path, dtype={"Code Loca": str})


    current_tab = f""
    if os.path.exists(loca_file):
        df_loca = pd.read_excel(loca_file, dtype={"LOCALISATION": str}) 
        print(df_loca)
    else:
        st.error(f"Fichier de localisations introuvable : {loca_file}")
        if st.button("📄 Générer un nouveau fichier vide"):
            df_corres = generate_empty_localisations(loca_file)
        else:
            st.stop()  # Stoppe l'app tant que le fichier n'est pas généré

    loca_codes = df_loca["LOCALISATION"].astype(str).unique()
    print(loca_codes)
    print(df_corres)
    filtered_corres = df_corres[df_corres["Code Loca"].isin(loca_codes)]
    # print("\n\ndf_corres", df_corres)
    # filtered_incidents = df_incidents[:-1]
    no_loca_incidents_codes  = ["SK01", "RK01", "BK01", "MK01", "CK01", "DENR"]
    no_loca_incidents = pd.DataFrame({
                                        "Code Incident": no_loca_incidents_codes,
                                        "Libellé incident": [""] * len(no_loca_incidents_codes) 
                                    })

    incident_list = pd.concat([filtered_incidents, no_loca_incidents], axis=0, ignore_index= True).drop_duplicates(subset=["Code Incident"])

    st.subheader(f"📍 Données pour {selected_elem}")
    st.write("Localisations")
    st.dataframe(df_loca)
    st.write("Correspondances LOCA ↔ UET")
    st.dataframe(filtered_corres)
    st.write("Incidents")
    st.dataframe(incident_list)
    
    st.markdown("---")    
    import re
    from difflib import SequenceMatcher

    # --- 1) Découper la schématèque en blocs et tabuler chaque bloc ---
    blocks = []
    current = []
    for l in schema_input.splitlines():
        if re.match(r"^-{5,}$", l.strip()):
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(l)
    if current:
        blocks.append("\n".join(current))

    # Construire block_codes : liste de dict {text, title, df, clean_set}
    block_codes = []
    for blk in blocks:
        title = blk.splitlines()[0].strip()
        rows = []
        for line in blk.splitlines()[1:]:
            if ";" not in line: continue
            orig, lbl, *_ = [p.strip() for p in line.split(";", 2)]
            rows.append({"original": orig, "label": lbl})
        df_blk = pd.DataFrame(rows)
        if df_blk.empty: continue


        df_blk["clean"] = df_blk["original"].map(extract_clean)
        block_codes.append({
            "text": blk,
            "title": title,
            "df": df_blk,
            "clean_set": set(df_blk["clean"])
        })

    # index pour niveau 2
    clean2blocks = {}
    for b in block_codes:
        for c in b["clean_set"]:
            clean2blocks.setdefault(c, []).append(b)

    # normaliser assigned
    assigned = {c.upper().strip() for c in df_loca["LOCALISATION"].astype(str)}    

    # ========== AJOUT LOCALISATION AVEC RECO ==========
    if "ajout_avec_reco" not in st.session_state:
        st.session_state["ajout_avec_reco"] = False


    if st.button("🧩 Ajout de Loca par recommandation sémantique 🧩") : 
        st.session_state["ajout_avec_reco"] = True

    
    if st.session_state["ajout_avec_reco"] == True:
        st.subheader("🏗️ Ajouter une localisation à cet élément")



        # === Niveau 1 : similarité des libellés dans la schématique ===
        st.markdown("**Recommandations Niveau 1 (labels similaires)**")
        elem_label = df_elements.loc[df_elements["ELEMENT"] == selected_elem, "INTITULE"].iloc[0].lower()

        # construire mapping clean_code → premier libellé rencontré
        schema_labels = {}
        for b in block_codes:
            for _, row in b["df"].iterrows():
                c = row["clean"]; lbl = row["label"]
                schema_labels.setdefault(c, lbl)

        # calcul des scores
        lvl1 = [
            {"code": c, "label": lbl, "score": SequenceMatcher(None, elem_label, lbl.lower()).ratio()}
            for c, lbl in schema_labels.items()
            if SequenceMatcher(None, elem_label, lbl.lower()).ratio() > 0.3
        ]
        lvl1 = sorted(lvl1, key=lambda x: x["score"], reverse=True)[:5]

        if not lvl1:
            st.info("✅ Pas de recommandations de niveau 1.")
        else:
            opts1 = [f"{r['code']} — {r['label']} ({r['score']:.2f})" for r in lvl1]
            sel1 = st.selectbox("🔎 Choisis une reco Niveau 1 :", opts1, key="dropdown_lvl1")
            reco1 = next(r for r in lvl1 if f"{r['code']} — {r['label']} ({r['score']:.2f})" == sel1)

            # on affiche les blocs où ce clean code apparaît
            blocs1 = [
                b for b in block_codes
                if reco1["code"] in b["clean_set"]
            ]
            if not blocs1:
                st.warning("Aucun bloc trouvé pour ce code.")
            else:
                st.markdown(f"### Reco N1 : **{reco1['code']} — {reco1['label']}** (score {reco1['score']:.2f})")
                titles1 = [b["title"] for b in blocs1]
                idx1 = st.selectbox("🧩 Choisir un bloc N1 :", list(range(len(titles1))),
                                    format_func=lambda i: titles1[i], key="dropdown_blocks_lvl1")
                b1 = blocs1[idx1]

                # afficher tableau et boutons
                df1 = b1["df"]
                def hl1(row):
                    # row est une Series, len(row) == nombre de colonnes de df1
                    if extract_clean(row["original"]) == reco1["code"]:
                        return ['background-color: lightgreen'] * len(row)
                    else:
                        return [''] * len(row)

                st.dataframe(df1.style.apply(hl1, axis=1), use_container_width=True)

                c1, c2 = st.columns(2)
                if c1.button("➕ Ajouter (N1)", key=f"add1_{reco1['code']}"):
                    # si pas dans df_corres → demander UET
                    if reco1["code"] not in df_corres["Code Loca"].values:
                        st.warning(f"`{reco1['code']}` absent de la correspondance globale.")
                        uet = st.text_input("UET pour ce code :", key=f"uet1_{reco1['code']}")
                        if st.button("Valider correspondance N1", key=f"save1_{reco1['code']}"):
                            df_corres.loc[len(df_corres)] = [reco1["code"], reco1["label"], uet]
                            df_corres.to_excel(corres_path, index=False)
                            st.success("Correspondance globale ajoutée.")
                    else:
                        df_loca.loc[len(df_loca)] = [reco1["code"], reco1["label"]]
                        df_loca.to_excel(loca_file, index=False)
                        st.success(f"{reco1['code']} ajouté à l’élément !")
                        st.rerun()
                if c2.button("❌ Ignorer (N1)", key=f"ign1_{reco1['code']}"):
                    st.info("Ignoré.")

        # === Niveau 2 : voisinage de bloc ===
        st.markdown("**Recommandations Niveau 2 (voisins de bloc)**")
        lvl2 = []
        seen = set()
        for a in assigned:
            for b in clean2blocks.get(a, []):
                for c in b["clean_set"] - assigned:
                    if c in seen: continue
                    # score = #blocs où c coexiste avec un assigned
                    score = sum(1 for b2 in clean2blocks.get(c, [])
                                if set(b2["clean_set"]) & assigned)
                    if score:
                        row = b["df"].loc[b["df"]["clean"] == c].iloc[0]
                        lvl2.append({
                            "code":  row["original"],
                            "label": row["label"],
                            "score": score,
                            "blocks": [b]
                        })
                        seen.add(c)

        if not lvl2:
            st.info("✅ Pas de recommandations de niveau 2.")
        else:
            lvl2 = sorted(lvl2, key=lambda x: x["score"], reverse=True)
            opts2 = [f"{r['code']} — {r['label']} (score {r['score']})" for r in lvl2]
            sel2 = st.selectbox("🔎 Choisis une reco Niveau 2 :", opts2, key="dropdown_lvl2")
            reco2 = next(r for r in lvl2 if f"{r['code']} — {r['label']} (score {r['score']})" == sel2)

            # navigation blocs
            st.markdown(f"### Reco N2 : **{reco2['code']} — {reco2['label']}** (score {reco2['score']})")
            titles2 = [b["title"] for b in reco2["blocks"]]
            idx2 = st.selectbox("🧩 Choisir un bloc N2 :", list(range(len(titles2))),
                                format_func=lambda i: titles2[i], key="dropdown_blocks_lvl2")
            b2 = reco2["blocks"][idx2]

            df2 = b2["df"]
            def hl2(row):
                # row est une Series, len(row) == nombre de colonnes de df1
                if (row["original"]) == reco1["code"]:
                    return ['background-color: lightgreen'] * len(row)
                else:
                    return [''] * len(row)

            st.dataframe(df2.style.apply(hl2, axis=1), use_container_width=True)

            c1, c2 = st.columns(2)
            if c1.button("➕ Ajouter (N2)", key=f"add2_{reco2['code']}"):
                if extract_clean(reco2["code"]) not in df_corres["Code Loca"].values:
                    st.warning(f"`{extract_clean(reco2['code'])}` absent de la correspondance globale.")
                    uet = st.text_input("UET pour ce code :", key=f"uet2_{reco2['code']}")
                    if st.button("Valider correspondance N2", key=f"save2_{reco2['code']}"):
                        df_corres.loc[len(df_corres)] = [extract_clean(reco2["code"]), reco2["label"], uet]
                        df_corres.to_excel(corres_path, index=False)
                        st.success("Correspondance globale ajoutée.")
                else:
                    df_loca.loc[len(df_loca)] = [extract_clean(reco2["code"]), reco2["label"]]
                    df_loca.to_excel(loca_file, index=False)
                    st.success(f"{extract_clean(reco2['code'])} ajouté à l’élément !")
                    rerun()
            if c2.button("❌ Ignorer (N2)", key=f"ign2_{reco2['code']}"):
                st.info("Ignoré.")


        if st.button("Fermer"):
            st.session_state["ajout_avec_reco"] = False
            st.rerun()

    st.markdown("---")

    # =============================================================================== #
    # ======= Option : explorer tous les blocs et ajouter directement un code ======= #
    # =============================================================================== #
    st.subheader("🔍 Explorer les blocs de la schématèque")

    # 1. Filtrage des blocs
    loca_codes = df_loca["LOCALISATION"].astype(str).unique()
    blocs_avec_loca = [b for b in block_codes if any(extract_clean(code) in loca_codes for code in b["df"]["original"])]
    blocs_sans_loca = [b for b in block_codes if b not in blocs_avec_loca]
    ordered_blocks = blocs_avec_loca + blocs_sans_loca
    all_titles = [b["title"] for b in ordered_blocks]

    # 2. Sélection d'un bloc
    chosen_blk_title = st.selectbox("Choisir un bloc à visualiser :", all_titles, key="explore_blk_select")
    blk_obj = next(b for b in ordered_blocks if b["title"] == chosen_blk_title)
    df_explore = blk_obj["df"]

    # 3. Sélection d'une ligne de ce bloc
    display_options = [f"{row['original']} | {row['label']}" for _, row in df_explore.iterrows()]
    selected_row = st.selectbox("Choisir une ligne à ajouter :", display_options, key="line_selector")

    # 4. Extraction du code et label
    selected_idx = display_options.index(selected_row)
    selected_code = extract_clean(df_explore.iloc[selected_idx]["original"])
    selected_label = df_explore.iloc[selected_idx]["label"]

    # 5. Vérification présence
    already_in_loca = selected_code in df_loca["LOCALISATION"].astype(str).values
    already_in_corres = selected_code in df_corres["Code Loca"].astype(str).values

    if already_in_loca:
        st.info(f"`{selected_code}` est déjà présent dans l’élément.")
    else:
        # Si pas dans les correspondances, on demande un UET
        if not already_in_corres:
            st.warning(f"`{selected_code}` n’existe pas encore dans les correspondances globales.")
            uet_key = f"uet_input_{selected_code}"
            uet_val = st.text_input(f"Veuillez entrer un UET pour `{selected_code}` :", key=uet_key)

            if st.button("✅ Valider la correspondance", key=f"save_corres_{selected_code}"):
                uet_val = st.session_state[uet_key].strip()
                if uet_val:
                    df_corres = pd.read_excel(corres_path, dtype={"Code Loca": str})
                    if selected_code not in df_corres["Code Loca"].values:
                        new_row = {"Code Loca": selected_code, "Libellé Long Loca": selected_label, "UET": uet_val, "Famille" : "X82"}
                        st.session_state.df_corres = pd.concat(
                            [st.session_state.df_corres, pd.DataFrame([new_row])],
                            ignore_index=True
                        )
                        st.session_state.df_corres.to_excel(corres_path, index=False)
                        if selected_code not in pd.read_excel(corres_path)["Code Loca"]:
                            st.success(f"✅ Correspondance globale pour `{selected_code}` enregistrée.")
                            print(pd.read_excel(corres_path)["Code Loca"])
                        del st.session_state[uet_key]
                    else:
                        st.warning("Ce code existe déjà dans les correspondances.")
                        print(pd.read_excel(corres_path))
                else:
                    st.warning("Veuillez saisir un UET valide.")

        # Ajout dans df_loca
        if st.button("➕ Ajouter ce code à l’élément", key=f"add_loca_{selected_code}"):
            df_loca.loc[len(df_loca)] = [selected_code, selected_label]
            df_loca.to_excel(loca_file, index=False)
            st.success(f"✅ `{selected_code}` ajouté à l’élément.")
            st.rerun()


    st.markdown("---")



    # ========== AJOUT MANUEL DE LOCALISATION ==============
    
    if "ajout_manuel" not in st.session_state:
        st.session_state["ajout_manuel"] = False

    if st.button("Ajout manuel de localisation"):
        st.session_state["ajout_manuel"] = True

    if st.session_state["ajout_manuel"] == True:
        st.subheader("🏗️ Ajouter une localisation à cet élément")
        
        # Nouveau système avec deux options
        add_mode = st.radio("Mode d'ajout :",
                        ["Sélectionner une localisation existante", "Créer une nouvelle localisation"],
                        horizontal=True,
                        key="add_mode_selector")
        
        if add_mode == "Sélectionner une localisation existante":
            # Filtrer pour ne montrer que les localisations non déjà attribuées
            existing_locations = df_corres[~df_corres["Code Loca"].isin(df_loca["LOCALISATION"])]
            
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
                        "LABEL": loc_info['Libellé Long Loca']
                    }
                    df_loca = pd.concat([df_loca, pd.DataFrame([new_row])], ignore_index=True)
                    
                    try:
                        df_loca.to_excel(loca_file, index=False)
                        st.success(f"Localisation {selected_existing} ajoutée avec succès !")
                        try:
                            # code suppression
                            rerun()
                        except Exception as e:
                            st.error(f"Erreur lors de la suppression : {str(e)}")
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
                    elif new_code in df_corres["Code Loca"].values:
                        st.error("Ce code localisation existe déjà !")
                    else:
                        # Ajout à la table de correspondance générale
                        new_corres_row = {
                            "Code Loca": new_code,
                            "Libellé Long Loca": new_label,
                            "UET": new_uet
                        }
                        df_corres = pd.concat([df_corres, pd.DataFrame([new_corres_row])], ignore_index=True)
                        
                        # Ajout à l'élément spécifique
                        new_loca_row = {
                            "LOCALISATION": new_code,
                            "LABEL": new_label
                        }
                        df_loca = pd.concat([df_loca, pd.DataFrame([new_loca_row])], ignore_index=True)
                        
                        try:
                            # Sauvegarde des deux fichiers
                            df_corres.to_excel(corres_path, index=False)
                            df_loca.to_excel(loca_file, index=False)
                            st.success("Nouvelle localisation créée et ajoutée avec succès !")
                            try:
                                # code suppression
                                rerun()
                            except Exception as e:
                                st.error(f"Erreur lors de la suppression : {str(e)}")
                        except Exception as e:
                            st.error(f"Erreur lors de la sauvegarde : {str(e)}")

        if st.button("Fermer l'ajout manuel"):
            st.session_state["ajout_manuel"] == False
            st.rerun()
        

    st.markdown("---")

    # ========== SECTION SUPPRESSION LOCALISATION ==========

    st.subheader("🗑️ Supprimer une localisation de cet élément")
    
    if not df_loca.empty:
        loc_to_remove = st.selectbox(
            "Sélectionner une localisation à retirer :",
            df_loca["LOCALISATION"].unique(),
            format_func=lambda x: f"{x} - {df_loca[df_loca['LOCALISATION'] == x]['LABEL'].iloc[0]}",
            key="remove_loc_select"
        )
        
    if "df_loca" not in st.session_state:
        st.session_state.df_loca = pd.read_excel(loca_file, dtype={"LOCALISATION": str})



        if st.button("❌ Retirer cette localisation", key="remove_loc_btn"):
            st.session_state.df_loca = st.session_state.df_loca[
                st.session_state.df_loca["LOCALISATION"] != loc_to_remove
            ]
            try:
                st.session_state.df_loca.to_excel(loca_file, index=False)
                st.success(f"✅ Localisation `{loc_to_remove}` retirée avec succès.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur lors de la suppression : {str(e)}")

        else:
            st.warning("Aucune localisation à supprimer pour cet élément.")


    # ========== CONSTRUCTION AUTOMATIQUE ARBORESCENCE ==========
    corres_path        = os.path.join(base_dir, "data/localisation_uet.xlsx")
    if "df_corres" not in st.session_state:
        st.session_state.df_corres = pd.read_excel(corres_path, dtype={"Code Loca": str})

    df_corres    = load_data(corres_path)
    template = pd.read_excel(template_path)
    existing_df = template.copy()

    # ========== CONSTRUCTION AUTOMATIQUE ARBORESCENCE ==========
    template = pd.read_excel(template_path)
    existing_df = template.copy()

    rows = []
    to_drop = []

    exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "TK01", "1791", "7935"]
    incident_codes = filtered_incidents["Code Incident"].dropna().unique()
    # print("loca codes : ", loca_codes)

    for inc in incident_codes:
        if inc in exceptions:
            # rows.append({
            #     "ELEMENT": selected_elem,
            #     "INCIDENT": inc,
            #     "LOCALISATION": "",
            #     "UET imputée": "RET"
            # })
            # print("don't! (add these incidents)")
            continue
        else:
            for loca in loca_codes:
                # print(loca)
                uets = filtered_corres[
                    filtered_corres["Code Loca"].astype(str).str.strip() == str(loca)
                ]["UET"].unique()
                
                # # print("\nfiltered_corres : ", filtered_corres)
                # # print("\nuets : ", uets)

                for uet in uets:
                    # print(uet)
                    already_exists = (
                        (existing_df["INCIDENT"].astype(str).str.strip() == str(inc).strip()) &
                        (existing_df["LOCALISATION"].astype(str).str.strip() == str(loca).strip()) &
                        (existing_df["UET imputée"] == uet)
                    ).any()

                    sub_no_inc = (
                        (existing_df["INCIDENT"].astype(str).str.strip() == str(inc).strip()) &
                        (existing_df["LOCALISATION"].astype(str).str.strip() == str(loca).strip()) &
                        (existing_df["UET imputée"] != uet)
                    )

                    if not already_exists:
                        rows.append({
                            "ELEMENT": selected_elem,
                            "INCIDENT": inc,
                            "LOCALISATION": loca,
                            "UET imputée": uet,
                            "Secteur": "M", 
                            "CODE RETOUCHE" : "RELE", 
                            "TPS RETOUCHE" : "0", 
                            "EFFET CLIENT" : "0", 
                            "REGROUPEMENT" : "ELEC", 
                            "METIER": "ELECTRICIT"
                        })

                    to_drop.extend(existing_df[sub_no_inc].index.tolist())

    # # print("rows : ", rows)
    # Incidents à ajouter automatiquement
    auto_incidents = [
        {"ELEMENT":  selected_elem, "INCIDENT": "SK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "RK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "BK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "MK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "CK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "TK01", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "1791", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "7935", "UET imputée": "RET", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"},
        {"ELEMENT":  selected_elem, "INCIDENT": "DENR", "UET imputée": "DIV", "LOCALISATION": "", "Secteur": "M", "CODE RETOUCHE" : "RELE", "TPS RETOUCHE" : "0", "EFFET CLIENT" : "0", "REGROUPEMENT" : "ELEC", "METIER": "ELECTRICIT"}
    ]
    
    df_auto = pd.DataFrame(auto_incidents)
    
    # Ajout au dataframe final
    existing_df = pd.concat([existing_df, df_auto], ignore_index=True)

    existing_df = existing_df.drop(index=list(set(to_drop))).drop_duplicates()
    new_lines = pd.DataFrame(rows).drop_duplicates()
    # print("new_lines : ", new_lines)
    current_df = pd.concat([new_lines, existing_df, df_auto], axis=0, ignore_index=True)
    # print("current_df", current_df)

    valid_inc = list(incident_codes) + exceptions
    current_df = current_df.drop_duplicates()
    current_df = current_df[
        (current_df["INCIDENT"].astype(str).str.strip().isin(valid_inc)) & (
            current_df["LOCALISATION"].astype(str).str.strip().notna() | current_df["INCIDENT"].astype(str).str.strip().isin(exceptions)
        )
    ]

    output = BytesIO()
    current_df.to_excel(output, index=False)
    output.seek(0)

    


    st.markdown("---")
    st.subheader("🧾 Aperçu du fichier actuel")
    st.success("✅ Arborescence mise à jour automatiquement")
    st.dataframe(current_df)

    st.download_button(
        label="⬇️ Télécharger le fichier Excel généré",
        data=output,
        file_name=f"{selected_elem}_UET.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    
else:
    st.warning("Veuillez sélectionner un élément pour modifier les localisations ou générer un fichier.")

