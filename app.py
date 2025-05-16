import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Générateur de fichier UET", layout="wide")
st.title("📄 Générateur de fichier UET")

# Chemins
base_dir = "data"
incident_path = os.path.join(base_dir, "incidents.xlsx")
element_path = os.path.join(base_dir, "elements.xlsx")
corres_path = os.path.join(base_dir, "localisation_uet.xlsx")
template_path = os.path.join(base_dir, "template.xlsx")
localisation_folder = os.path.join(base_dir, "localisations")

# Chargement des fichiers
df_incidents = pd.read_excel(incident_path)
df_elements = pd.read_excel(element_path)
df_corres = pd.read_excel(corres_path)

# Modifiables : ajout/suppression d'incidents
st.sidebar.subheader("📌 Gérer les incidents")
incident_input = st.sidebar.text_input("Ajouter un nouveau code incident :")
if st.sidebar.button("Ajouter l'incident"):
    if incident_input and incident_input not in df_incidents["Code Incident"].values:
        df_incidents.loc[len(df_incidents)] = {"Code Incident": incident_input}
        st.sidebar.success(f"Ajouté : {incident_input}")

# Modifiables : ajout d’éléments
st.sidebar.subheader("📦 Gérer les éléments")
element_input = st.sidebar.text_input("Ajouter un nouveau code élément :")
if st.sidebar.button("Ajouter l'élément"):
    if element_input and element_input not in df_elements["ELEMENT"].values:
        df_elements.loc[len(df_elements)] = {"ELEMENT": element_input}
        st.sidebar.success(f"Ajouté : {element_input}")

# Choix de l’élément
st.sidebar.header("🧩 Sélection de l'élément")
selected_elem = st.sidebar.selectbox("Choisir un code élément :", df_elements["ELEMENT"].unique())

if selected_elem:
    loca_file = os.path.join(localisation_folder, f"{selected_elem}_localisations.xlsx")
    if os.path.exists(loca_file):
        df_loca = pd.read_excel(loca_file)
    else:
        st.error(f"Fichier de localisations introuvable : {loca_file}")
        st.stop()

    loca_codes = df_loca["LOCALISATION"].unique()
    filtered_corres = df_corres[df_corres["Code Loca"].isin(loca_codes)]
    filtered_incidents = df_incidents.copy()

    # Affichage des tables actuelles
    st.subheader(f"📍 Données pour {selected_elem}")
    st.write("Localisations")
    st.dataframe(df_loca)
    st.write("Correspondances LOCA ↔ UET")
    st.dataframe(filtered_corres)
    st.write("Incidents (modifiables)")
    st.dataframe(filtered_incidents)

    # Bouton de génération
    if st.sidebar.button("🔁 Générer le fichier Excel"):
        template = pd.read_excel(template_path)
        existing_df = template.copy()
        rows = []
        to_drop = []

        # Exceptions (UET = RET / pas de localisation nécessaire)
        exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "DENR"]
        incident_codes = filtered_incidents["Code Incident"].dropna().unique()

        # Normal incidents avec localisations
        for inc in incident_codes:
            if inc in exceptions:
                continue
            for loca in loca_codes:
                uets = filtered_corres[filtered_corres["Code Loca"].astype(str) == str(loca)]["UET"].unique()

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

        # Exceptions manuelles (UET = RET, pas de LOCALISATION)
        for inc in incident_codes:
            if inc in exceptions:
                already_exists = (
                    (existing_df["INCIDENT"].astype(str).str.strip() == str(inc).strip()) &
                    (existing_df["UET imputée"] == "RET")
                ).any()

                if not already_exists:
                    rows.append({
                        "ELEMENT": selected_elem,
                        "INCIDENT": inc,
                        "LOCALISATION": None,
                        "UET imputée": "RET"
                    })

        # Nettoyage et concaténation
        existing_df = existing_df.drop(index=list(set(to_drop)))
        new_lines = pd.DataFrame(rows).drop_duplicates()
        final_df = pd.concat([existing_df, new_lines], axis=0, ignore_index=True)

        output = BytesIO()
        final_df.to_excel(output, index=False)
        output.seek(0)

        st.success("✅ Fichier généré avec succès !")
        st.download_button(
            label="⬇️ Télécharger le fichier Excel",
            data=output,
            file_name=f"{selected_elem}_UET.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
