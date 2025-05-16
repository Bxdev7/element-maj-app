import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Mise à jour d'élément GRET", layout="wide")
st.title("📄 Mise à jour d'élément GRET")

# Définir les chemins
base_dir = "data"
incident_path = os.path.join(base_dir, "incidents.xlsx")
element_path = os.path.join(base_dir, "elements.xlsx")
corres_path = os.path.join(base_dir, "localisation_uet.xlsx")
template_path = os.path.join(base_dir, "template.xlsx")
localisation_folder = os.path.join(base_dir, "localisations")

# Charger les fichiers
df_incidents = pd.read_excel(incident_path)
df_elements = pd.read_excel(element_path)
df_corres = pd.read_excel(corres_path)

# ========== CHOIX DE L'ÉLÉMENT ==========
st.sidebar.header("Choix de l'élément")
selected_elem = st.sidebar.selectbox("Choisir un code élément :", df_elements["ELEMENT"].unique())

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
        st.sidebar.markdown("### 🆕 Nouvelles localisations détectées")

        added_loca_data = []
        for code, label in new_loca_items.items():
            add = st.sidebar.checkbox(f"{code} - {label}", key=code)
            uet_val = st.sidebar.text_input(f"UET pour {code}", key=f"uet_{code}")
            if add and uet_val:
                added_loca_data.append({
                    "Code Loca": code,
                    "Libellé Long Loca": label,
                    "UET": uet_val.strip().upper()
                })

        if added_loca_data:
            st.sidebar.success(f"{len(added_loca_data)} localisations prêtes à être ajoutées")
            if st.sidebar.button("✅ Valider et ajouter au fichier de correspondance"):
                df_new = pd.DataFrame(added_loca_data)
                df_corres = pd.concat([df_corres, df_new], ignore_index=True)
                st.session_state["df_corres_updated"] = df_corres  # Enregistrer dans session pour usage ailleurs
                st.sidebar.success("Nouvelles localisations ajoutées à la correspondance !")
    else:
        st.sidebar.info("Aucune nouvelle localisation détectée.")


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
    filtered_incidents = df_incidents

    st.subheader(f"📍 Données pour {selected_elem}")
    st.write("Localisations")
    st.dataframe(df_loca)
    st.write("Correspondances LOCA ↔ UET")
    st.dataframe(filtered_corres)
    st.write("Incidents")
    st.dataframe(filtered_incidents)

     # ========== AJOUT LOCALISATION ==========
    st.subheader("🏗️ Ajouter une localisation à cet élément")
    with st.expander("➕ Ajouter une nouvelle localisation"):
        new_loca_code = st.text_input("Code localisation")
        new_loca_label = st.text_input("Libellé localisation")
        new_loca_uet = st.text_input("UET associée")

        if st.button("✅ Ajouter la localisation"):
            if new_loca_code and new_loca_label and new_loca_uet:
                df_loca = df_loca.append({"LOCALISATION": new_loca_code, "LIBELLE": new_loca_label}, ignore_index=True)
                df_loca.to_excel(loca_file, index=False)

                if new_loca_code in df_corres["Code Loca"].values:
                    df_corres.loc[df_corres["Code Loca"] == new_loca_code, "Libellé Long Loca"] = new_loca_label
                    df_corres.loc[df_corres["Code Loca"] == new_loca_code, "UET"] = new_loca_uet
                else:
                    df_corres = df_corres.append({
                        "Code Loca": new_loca_code,
                        "Libellé Long Loca": new_loca_label,
                        "UET": new_loca_uet
                    }, ignore_index=True)
                df_corres.to_excel(corres_path, index=False)
                st.success("Localisation ajoutée avec succès.")
                st.experimental_rerun()
            else:
                st.warning("Tous les champs doivent être remplis.")

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

    existing_df = existing_df.drop(index=list(set(to_drop)))
    new_lines = pd.DataFrame(rows).drop_duplicates()
    current_df = pd.concat([existing_df, new_lines], axis=0, ignore_index=True)

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
