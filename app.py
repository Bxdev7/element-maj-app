import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="Générateur de fichier UET", layout="wide")
st.title("📄 Générateur de fichier UET")

# Définir les chemins
base_dir = "data"
incident_path = os.path.join(base_dir, "incidents.xlsx")
element_path = os.path.join(base_dir, "elements.xlsx")
corres_path = os.path.join(base_dir, "localisation_uet.xlsx")
template_path = os.path.join(base_dir, "template.xlsx")
localisation_folder = os.path.join(base_dir, "localisations")

# Charger les fichiers de base
df_incidents = pd.read_excel(incident_path)
df_elements = pd.read_excel(element_path)
df_corres = pd.read_excel(corres_path)

# Sélection de l'élément
st.sidebar.header("Choix de l'élément")
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
    filtered_incidents = df_incidents

    st.subheader(f"📍 Données pour {selected_elem}")
    st.write("Localisations")
    st.dataframe(df_loca)
    st.write("Correspondances LOCA ↔ UET")
    st.dataframe(filtered_corres)
    st.write("Incidents")
    st.dataframe(filtered_incidents)

    if st.sidebar.button("🔁 Générer le fichier Excel"):
        template = pd.read_excel(template_path)
        existing_df = template.copy()

        rows = []
        to_drop = []

        exceptions = ["SK01", "RK01", "BK01", "MK01", "CK01", "DENR"]
        incident_codes = filtered_incidents["Code Incident"].dropna().unique()

        for inc in incident_codes:
            for loca in loca_codes:
                uets = filtered_corres[
                    filtered_corres["Code Loca"].astype(str) == str(loca)
                ]["UET imputée"].unique()

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
        final_df = pd.concat([existing_df, new_lines], axis=0, ignore_index=True)

        valid_inc = list(incident_codes) + exceptions
        final_df = final_df[
            (final_df["INCIDENT"].isin(valid_inc)) &
            (
                final_df["LOCALISATION"].notna() |
                final_df["INCIDENT"].isin(exceptions)
            )
        ]

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
