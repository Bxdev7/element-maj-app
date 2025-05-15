import streamlit as st
import pandas as pd
from io import BytesIO
import os

st.set_page_config(page_title="Générateur de fichier UET", layout="wide")
st.title("📄 Générateur de fichier UET")

# 1. Chargement des fichiers depuis /data/
try:
    df_incidents = pd.read_excel("data/incidents.xlsx")
    df_elements = pd.read_excel("data/elements.xlsx")
    df_corres = pd.read_excel("data/localisation_uet.xlsx")
except Exception as e:
    st.error(f"❌ Erreur de chargement des fichiers dans /data/ : {e}")
    st.stop()

template_path = "template.xlsx"
localisations_dir = "data/localisations"

# 2. Sélection d'un code élément
st.sidebar.header("1. Choisir un code élément")
code_elem = st.sidebar.selectbox("Code élément", df_elements['Code élément'].unique())

# 3. Chargement dynamique des localisations selon l'élément
localisation_file = os.path.join(localisations_dir, f"{code_elem}_localisations.xlsx")

if os.path.exists(localisation_file):
    try:
        df_loca = pd.read_excel(localisation_file)
    except Exception as e:
        st.error(f"❌ Impossible de lire le fichier de localisations : {e}")
        st.stop()
else:
    st.warning(f"⚠️ Aucun fichier de localisation trouvé pour l'élément : {code_elem}")
    st.stop()

# 4. Filtrage des données associées
filtered_loca = df_loca[df_loca['Code élément'] == code_elem] if 'Code élément' in df_loca.columns else df_loca
loca_codes = filtered_loca['Code localisation'].unique()
filtered_corres = df_corres[df_corres['Code localisation'].isin(loca_codes)]
uet_codes = filtered_corres['Code UET'].unique()
filtered_incidents = df_incidents[df_incidents['Code élément'] == code_elem]

# 5. Affichage
st.subheader(f"✅ Résumé des données pour : {code_elem}")
st.write("📍 Localisations associées")
st.dataframe(filtered_loca)

st.write("📌 Correspondance LOCA ↔ UET")
st.dataframe(filtered_corres)

st.write("⚠️ Incidents associés")
st.dataframe(filtered_incidents)

# 6. Génération du fichier Excel
st.sidebar.header("2. Générer le fichier final")
if st.sidebar.button("📤 Générer fichier Excel"):
    try:
        template = pd.read_excel(template_path)
        template_filled = template.copy()

        # Exemple de remplissage
        template_filled['Code élément'] = code_elem
        template_filled['Code incident'] = ", ".join(filtered_incidents['Code incident'].astype(str).unique())
        template_filled['Code localisation'] = ", ".join(loca_codes.astype(str))
        template_filled['Code UET'] = ", ".join(uet_codes.astype(str))

        output = BytesIO()
        template_filled.to_excel(output, index=False)
        output.seek(0)

        st.success("✅ Fichier généré avec succès !")
        st.download_button("⬇️ Télécharger le fichier Excel", data=output,
                           file_name=f"fichier_{code_elem}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.error(f"❌ Erreur lors de la génération : {e}")
