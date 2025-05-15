import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Générateur de fichier UET", layout="wide")
st.title("📄 Générateur de fichier UET")

# 1. Upload des fichiers nécessaires
st.sidebar.header("1. Charger les fichiers Excel")

uploaded_incidents = st.sidebar.file_uploader("📘 Codes incidents (ex: incidents.xlsx)", type=["xlsx"])
uploaded_elements = st.sidebar.file_uploader("📗 Codes éléments (ex: elements.xlsx)", type=["xlsx"])
uploaded_corres = st.sidebar.file_uploader("📕 Correspondance LOCA ↔ UET (ex: localisation_uet.xlsx)", type=["xlsx"])

template_path = "template.xlsx"
localisation_folder = "data/localisations/"

if all([uploaded_incidents, uploaded_elements, uploaded_corres]):
    # 2. Lecture des fichiers
    df_incidents = pd.read_excel(uploaded_incidents)
    df_elements = pd.read_excel(uploaded_elements)
    df_corres = pd.read_excel(uploaded_corres)

    # 3. Sélection d'un élément
    st.sidebar.header("2. Choisir un code élément")
    code_elem = st.sidebar.selectbox("Code élément", df_elements['Code élément'].unique())

    if code_elem:
        # 4. Chargement du fichier de localisations spécifique à l’élément
        loca_file = os.path.join(localisation_folder, f"{code_elem}_localisations.xlsx")
        if os.path.exists(loca_file):
            df_loca = pd.read_excel(loca_file)
        else:
            st.error(f"Fichier des localisations introuvable pour l’élément : {code_elem}")
            st.stop()

        # 5. Filtrage
        loca_codes = df_loca["Code localisation"].unique()
        filtered_corres = df_corres[df_corres["Code localisation"].isin(loca_codes)]
        uet_codes = filtered_corres["Code UET"].unique()
        filtered_incidents = df_incidents[df_incidents['Code élément'] == code_elem]

        # 6. Affichage des données
        st.subheader(f"✅ Résumé des données pour : {code_elem}")
        st.write("📍 Localisations associées")
        st.dataframe(df_loca)

        st.write("📌 Correspondance LOCA ↔ UET")
        st.dataframe(filtered_corres)

        st.write("⚠️ Incidents associés")
        st.dataframe(filtered_incidents)

        # 7. Génération du fichier
        st.sidebar.header("3. Générer le fichier final")
        if st.sidebar.button("📤 Générer fichier Excel"):
            try:
                template = pd.read_excel(template_path)
                existing_df = template.copy()

                rows = []
                to_drop = []

                exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "DENR"]
                incident_codes = filtered_incidents["Code incident"].dropna().unique()

                for inc in incident_codes:
                    for loca in loca_codes:
                        uets = filtered_corres[
                            filtered_corres["Code localisation"].astype(str) == str(loca)
                        ]["Code UET"].unique()

                        for uet in uets:
                            # Vérifie si la ligne existe déjà
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
                                    "ELEMENT": code_elem,
                                    "INCIDENT": inc,
                                    "LOCALISATION": loca,
                                    "UET imputée": uet
                                })

                            to_drop.extend(existing_df[sub_no_inc].index.tolist())

                existing_df = existing_df.drop(index=list(set(to_drop)))

                # Ajout des nouvelles lignes
                new_lines = pd.DataFrame(rows).drop_duplicates()
                final_df = pd.concat([existing_df, new_lines], axis=0, ignore_index=True)

                # Nettoyage
                valid_inc = list(incident_codes) + exceptions
                final_df = final_df[
                    (final_df["INCIDENT"].isin(valid_inc)) &
                    (
                        final_df["LOCALISATION"].notna() |
                        final_df["INCIDENT"].isin(exceptions)
                    )
                ]

                # Sauvegarde en mémoire
                output = BytesIO()
                final_df.to_excel(output, index=False)
                output.seek(0)

                st.success("✅ Fichier généré avec succès !")
                st.download_button(
                    "⬇️ Télécharger le fichier Excel",
                    data=output,
                    file_name=f"fichier_{code_elem}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Erreur lors de la génération : {e}")
else:
    st.info("Veuillez charger tous les fichiers nécessaires pour commencer.")
