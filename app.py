import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Mise à jour d'élément GRET", layout="wide")
st.title("📄 Mise à jour d'élément GRET")

# ========== FONCTIONS CACHÉES ==========
@st.cache_data
def load_data(file_path):
    try:
        df = pd.read_excel(file_path)
        if 'Code Loca' in df.columns:
            df['Code Loca'] = df['Code Loca'].astype(str).str.strip()
        return df
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

# ========== CHOIX DE L'ÉLÉMENT ==========
st.sidebar.header("Choix de l'élément")
selected_elem = st.sidebar.selectbox("Choisir un code élément :", df_elements["ELEMENT"].unique())

st.sidebar.markdown("### 📋 Visualiser")

if st.sidebar.button("👁️ Voir les correspondances"):
    st.session_state["show_corres_table"] = True

if st.session_state.get("show_corres_table"):
    st.markdown("### 🔍 Table des correspondances Loca - UET")
    st.dataframe(df_corres, use_container_width=True)

    if st.button("❌ Fermer"):
        st.session_state["show_corres_table"] = False



# ========== Sidebar ==========
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Coller une nouvelle schématèque")

schema_input = st.sidebar.text_area("Colle ici le contenu de la schématèque")

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
        st.markdown("### 🆕 Nouvelles localisations détectées")
        st.info("🛠️ Tu peux associer chaque localisation à une existante, la modifier ou l’ajouter directement.")

        for i, (code, label) in enumerate(new_loca_items.items()):
            with st.expander(f"➡️ {code} - {label}"):
                # Sélection d'une localisation existante
                options = [f"{c} - {l}" for c, l in zip(df_corres['Code Loca'], df_corres['Libellé Long Loca'])]
                selected = st.selectbox("Associer à une localisation existante :", options=options, key=f"select_{i}")
                code_selected, libelle_selected = selected.split(" - ", 1)

                # Champs modifiables
                new_code = st.text_input("✏️ Modifier le Code Loca :", value=code, key=f"code_{i}")
                new_libelle = st.text_input("✏️ Modifier le Libellé :", value=label, key=f"libelle_{i}")
                uet = st.text_input("🔧 UET associé :", key=f"uet_{i}")

                if st.button("✅ Ajouter au fichier de correspondance", key=f"add_{i}"):
                    new_row = {
                        "Code Loca": new_code.strip(),
                        "Libellé Long Loca": new_libelle.strip(),
                        "UET": uet.strip()
                    }
                    df_corres = pd.concat([df_corres, pd.DataFrame([new_row])], ignore_index=True)
                    st.success(f"Ajouté : {new_row['Code Loca']} - {new_row['Libellé Long Loca']}")

        # Optionnel : bouton de sauvegarde globale
        if st.button("💾 Sauvegarder le fichier de correspondance"):
            df_corres.to_excel(corres_path, index=False)
            st.success("📁 Fichier sauvegardé avec succès.")
    else:
        st.sidebar.info("✅ Aucune nouvelle localisation détectée.")

# ========== GESTION DES LOCALISATIONS (SIDEBAR) ==========
st.sidebar.subheader("🗺️ Gestion des Localisations")

with st.sidebar.expander("🔍 Voir toutes les localisations"):
    st.dataframe(df_corres, use_container_width=True)

with st.sidebar.expander("✏️ Modifier une localisation"):
    loca_to_edit = st.selectbox(
        "Choisir une localisation à modifier",
        df_corres["Code Loca"].unique(),
        key="edit_loca_select"
    )
    
    edit_data = df_corres[df_corres["Code Loca"] == loca_to_edit].iloc[0]
    new_code = st.text_input("Code", value=edit_data["Code Loca"], key="edit_loca_code")
    new_label = st.text_input("Libellé", value=edit_data["Libellé Long Loca"], key="edit_loca_label")
    new_uet = st.text_input("UET", value=edit_data["UET"], key="edit_loca_uet")
    
    if st.button("💾 Enregistrer les modifications", key="edit_loca_btn"):
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
        df_corres["Code Loca"].unique(),
        key="delete_loca_select"
    )
    
    if st.button("❌ Confirmer la suppression", key="delete_loca_btn"):
        try:
            df_corres = df_corres[df_corres["Code Loca"] != loca_to_delete]
            df_corres.to_excel(corres_path, index=False)
            st.success("Localisation supprimée!")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur: {str(e)}")


# ========== GESTION DES INCIDENTS ==========
st.sidebar.subheader("🛠️ Gestion des Incidents")

with st.sidebar.expander("Modifier les incidents existants"):
    selected_incident = st.selectbox("Choisir un incident à modifier :", df_incidents["Code Incident"])
    new_label = st.text_input("Nouveau libellé", value=df_incidents[df_incidents["Code Incident"] == selected_incident]["Libellé incident"].values[0])
    if st.button("✅ Modifier l’incident"):
        df_incidents.loc[df_incidents["Code Incident"] == selected_incident, "Libellé Incident"] = new_label
        df_incidents.to_excel(incident_path, index=False)
        st.success("Incident modifié avec succès.")
        st.experimental_rerun()

with st.sidebar.expander("Ajouter un nouvel incident"):
    new_code = st.text_input("Code Incident à ajouter")
    new_lib = st.text_input("Libellé Incident")
    if st.button("➕ Ajouter l’incident"):
        if new_code and new_lib:
            df_incidents = df_incidents.append({"Code Incident": new_code, "Libellé Incident": new_lib}, ignore_index=True)
            df_incidents.to_excel(incident_path, index=False)
            st.success("Incident ajouté avec succès.")
            st.experimental_rerun()
        else:
            st.warning("Merci de remplir les deux champs.")

with st.sidebar.expander("Supprimer un incident"):
    incident_to_delete = st.selectbox("Sélectionner un incident à supprimer :", df_incidents["Code Incident"])
    if st.button("🗑️ Supprimer l’incident"):
        df_incidents = df_incidents[df_incidents["Code Incident"] != incident_to_delete]
        df_incidents.to_excel(incident_path, index=False)
        st.success("Incident supprimé.")
        st.experimental_rerun()



if selected_elem:
    loca_file = os.path.join(localisation_folder, f"{selected_elem}_localisations.xlsx")
    current_tab = f""
    if os.path.exists(loca_file):
        df_loca = pd.read_excel(loca_file)
    else:
        st.error(f"Fichier de localisations introuvable : {loca_file}")
        st.stop()

    loca_codes = df_loca["LOCALISATION"].unique()
    filtered_corres = df_corres[df_corres["Code Loca"].isin(loca_codes)]
    filtered_incidents = df_incidents[:-1]
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

    # ========== AJOUT LOCALISATION ==========
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
                    "LIBELLE": loc_info['Libellé Long Loca']
                }
                df_loca = pd.concat([df_loca, pd.DataFrame([new_row])], ignore_index=True)
                
                try:
                    df_loca.to_excel(loca_file, index=False)
                    st.success(f"Localisation {selected_existing} ajoutée avec succès !")
                    st.experimental_rerun()
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
                        "LIBELLE": new_label
                    }
                    df_loca = pd.concat([df_loca, pd.DataFrame([new_loca_row])], ignore_index=True)
                    
                    try:
                        # Sauvegarde des deux fichiers
                        df_corres.to_excel(corres_path, index=False)
                        df_loca.to_excel(loca_file, index=False)
                        st.success("Nouvelle localisation créée et ajoutée avec succès !")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la sauvegarde : {str(e)}")

    # ========== SECTION SUPPRESSION LOCALISATION ==========
    st.markdown("---")
    st.subheader("🗑️ Supprimer une localisation de cet élément")
    
    if not df_loca.empty:
        loc_to_remove = st.selectbox(
            "Sélectionner une localisation à retirer :",
            df_loca["LOCALISATION"].unique(),
            format_func=lambda x: f"{x} - {df_loca[df_loca['LOCALISATION'] == x]['LIBELLE'].iloc[0]}",
            key="remove_loc_select"
        )
        
        if st.button("❌ Retirer cette localisation", key="remove_loc_btn"):
            df_loca = df_loca[df_loca["LOCALISATION"] != loc_to_remove]
            
            try:
                df_loca.to_excel(loca_file, index=False)
                st.success(f"Localisation {loc_to_remove} retirée avec succès !")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Erreur lors de la suppression : {str(e)}")
    else:
        st.warning("Aucune localisation à supprimer pour cet élément.")

    # ========== CONSTRUCTION AUTOMATIQUE ARBORESCENCE ==========
    # [Le reste de votre code existant reste inchangé...]
    template = pd.read_excel(template_path)
    existing_df = template.copy()

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
