import streamlit as st
import pandas as pd
import os
from io import BytesIO

# Configuration de la page
st.set_page_config(page_title="Mise à jour d'élément GRET", layout="wide")
st.title("📄 Mise à jour d'élément GRET")

# ========== FONCTIONS CACHÉES ==========
@st.cache_data
def load_data(file_path):
    try:
        return pd.read_excel(file_path)
    except Exception as e:
        st.error(f"Erreur lors du chargement {file_path}: {str(e)}")
        return pd.DataFrame()

@st.cache_data
def load_template(file_path):
    try:
        return pd.read_excel(file_path)
    except Exception as e:
        st.error(f"Erreur lors du chargement du template: {str(e)}")
        return pd.DataFrame()

# ========== CHARGEMENT DES DONNÉES ==========
base_dir = "data"
incident_path = os.path.join(base_dir, "incidents.xlsx")
element_path = os.path.join(base_dir, "elements.xlsx")
corres_path = os.path.join(base_dir, "localisation_uet.xlsx")
template_path = os.path.join(base_dir, "template.xlsx")
localisation_folder = os.path.join(base_dir, "localisations")

# Chargement avec cache
df_incidents = load_data(incident_path)
df_elements = load_data(element_path)
df_corres = load_data(corres_path)
template = load_template(template_path)

# ========== SIDEBAR - GESTION DES LOCALISATIONS ==========
st.sidebar.header("📌 Gestion des Localisations")

with st.sidebar.expander("🔍 Voir toutes les localisations"):
    st.dataframe(df_corres, use_container_width=True)

with st.sidebar.expander("✏️ Modifier une localisation"):
    loca_to_edit = st.selectbox(
        "Choisir une localisation à modifier",
        df_corres["Code Loca"].unique()
    )
    
    edit_data = df_corres[df_corres["Code Loca"] == loca_to_edit].iloc[0]
    new_code = st.text_input("Code", value=edit_data["Code Loca"])
    new_label = st.text_input("Libellé", value=edit_data["Libellé Long Loca"])
    new_uet = st.text_input("UET", value=edit_data["UET"])
    
    if st.button("💾 Enregistrer les modifications"):
        try:
            df_corres.loc[df_corres["Code Loca"] == loca_to_edit, "Code Loca"] = new_code
            df_corres.loc[df_corres["Code Loca"] == new_code, "Libellé Long Loca"] = new_label
            df_corres.loc[df_corres["Code Loca"] == new_code, "UET"] = new_uet
            df_corres.to_excel(corres_path, index=False)
            st.success("Localisation modifiée avec succès!")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur: {str(e)}")

with st.sidebar.expander("🗑️ Supprimer une localisation"):
    loca_to_delete = st.selectbox(
        "Choisir une localisation à supprimer",
        df_corres["Code Loca"].unique()
    )
    
    if st.button("❌ Confirmer la suppression"):
        try:
            df_corres = df_corres[df_corres["Code Loca"] != loca_to_delete]
            df_corres.to_excel(corres_path, index=False)
            st.success("Localisation supprimée!")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur: {str(e)}")

# ========== SECTION PRINCIPALE - AJOUT LOCALISATION ==========
selected_elem = st.sidebar.selectbox("Choisir un code élément :", df_elements["ELEMENT"].unique())

if selected_elem:
    loca_file = os.path.join(localisation_folder, f"{selected_elem}_localisations.xlsx")
    df_loca = load_data(loca_file) if os.path.exists(loca_file) else pd.DataFrame()

    st.subheader(f"🏗️ Ajout de localisation à {selected_elem}")
    
    add_option = st.radio("Type d'ajout :",
                         ["Ajouter une localisation existante", "Créer une nouvelle localisation"])
    
    if add_option == "Ajouter une localisation existante":
        existing_loca = st.selectbox(
            "Choisir parmi les localisations existantes",
            df_corres["Code Loca"].unique()
        )
        
        loca_info = df_corres[df_corres["Code Loca"] == existing_loca].iloc[0]
        st.info(f"Libellé: {loca_info['Libellé Long Loca']} | UET: {loca_info['UET']}")
        
        if st.button(f"➕ Ajouter {existing_loca} à l'élément"):
            if existing_loca in df_loca["LOCALISATION"].values:
                st.warning("Cette localisation existe déjà pour cet élément")
            else:
                df_loca = pd.concat([
                    df_loca,
                    pd.DataFrame([{
                        "LOCALISATION": existing_loca,
                        "LIBELLE": loca_info["Libellé Long Loca"]
                    }])
                ], ignore_index=True)
                try:
                    df_loca.to_excel(loca_file, index=False)
                    st.success("Localisation ajoutée!")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erreur: {str(e)}")
    
    else:  # Nouvelle localisation
        with st.form("new_loca_form"):
            new_code = st.text_input("Code localisation")
            new_label = st.text_input("Libellé localisation")
            new_uet = st.text_input("UET associée")
            
            if st.form_submit_button("✅ Créer et ajouter"):
                if new_code and new_label and new_uet:
                    # Ajout à la correspondance générale
                    df_corres = pd.concat([
                        df_corres,
                        pd.DataFrame([{
                            "Code Loca": new_code,
                            "Libellé Long Loca": new_label,
                            "UET": new_uet
                        }])
                    ], ignore_index=True)
                    
                    # Ajout à l'élément spécifique
                    df_loca = pd.concat([
                        df_loca,
                        pd.DataFrame([{
                            "LOCALISATION": new_code,
                            "LIBELLE": new_label
                        }])
                    ], ignore_index=True)
                    
                    try:
                        df_corres.to_excel(corres_path, index=False)
                        df_loca.to_excel(loca_file, index=False)
                        st.success("Localisation créée et ajoutée!")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erreur: {str(e)}")
                else:
                    st.warning("Tous les champs doivent être remplis")

# ========== RESTE DU CODE EXISTANT ==========
# [Le reste de votre code actuel peut être conservé ici...]

    # ========== CONSTRUCTION AUTOMATIQUE ARBORESCENCE ==========
    template = pd.read_excel(template_path)
    existing_df = template.copy()

    rows = []
    to_drop = []

    exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "DENR"]
    incident_codes = filtered_incidents["Code Incident"].dropna().unique()

    for inc in incident_codes:
        if inc in exceptions:
            rows.append({
                "ELEMENT": selected_elem,
                "INCIDENT": inc,
                "LOCALISATION": "",
                "UET imputée": "RET"
            })
        else:
            for loca in loca_codes:
                uets = filtered_corres[
                    filtered_corres["Code Loca"].astype(str) == str(loca)
                ]["UET"].unique()

                for uet in uets:
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
                            "UET imputée": uet
                        })

                    to_drop.extend(existing_df[sub_no_inc].index.tolist())

    
    # Incidents à ajouter automatiquement
    auto_incidents = [
        {"ELEMENT":  selected_elem, "INCIDENT": "SK01", "UET imputée": "RET", "LOCALISATION": ""},
        {"ELEMENT":  selected_elem, "INCIDENT": "RK01", "UET imputée": "RET", "LOCALISATION": ""},
        {"ELEMENT":  selected_elem, "INCIDENT": "BK01", "UET imputée": "RET", "LOCALISATION": ""},
        {"ELEMENT":  selected_elem, "INCIDENT": "MK01", "UET imputée": "RET", "LOCALISATION": ""},
        {"ELEMENT":  selected_elem, "INCIDENT": "CK01", "UET imputée": "RET", "LOCALISATION": ""},
        {"ELEMENT":  selected_elem, "INCIDENT": "DENR", "UET imputée": "DIV", "LOCALISATION": ""}
    ]
    
    df_auto = pd.DataFrame(auto_incidents)
    
    # Ajout au dataframe final
    #existing_df = pd.concat([existing_df, df_auto], ignore_index=True)

    existing_df = existing_df.drop(index=list(set(to_drop)))
    new_lines = pd.DataFrame(rows).drop_duplicates()
    current_df = pd.concat([existing_df, new_lines, df_auto], axis=0, ignore_index=True)

    valid_inc = list(incident_codes) + exceptions
    current_df = current_df[
        (current_df["INCIDENT"].isin(valid_inc)) & (
            current_df["LOCALISATION"].notna() | current_df["INCIDENT"].isin(exceptions)
        )
    ]

    output = BytesIO()
    current_df.to_excel(output, index=False)
    output.seek(0)

    
    st.download_button(
        label="⬇️ Télécharger le fichier Excel généré",
        data=output,
        file_name=f"{selected_elem}_UET.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.subheader("🧾 Aperçu du fichier actuel")
    st.success("✅ Arborescence mise à jour automatiquement")
    st.dataframe(current_df)

else:
    st.warning("Veuillez sélectionner un élément pour modifier les localisations ou générer un fichier.")
