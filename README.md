# GRET MAJ AUTO 🚗🔧

**Offline Streamlit App to Semi-Automatically Update Automotive Failure Catalogs**

assets/GMA_visuel_exploration_blocs.png

## 🔍 Overview

GRET MAJ AUTO is an offline-capable data platform built with **Python** and **Streamlit**, developed at Renault Sandouville to modernize the update process of the **GRET failure catalog**.

The tool automates the extraction, association, and validation of failure data directly from **electronic schematics**, enabling accurate and traceable updates of failure datasets across multiple vehicle projects.

---

## ⚙️ Features

- ✅ **Offline deployment** with `.whl`-based dependency management  
- 📁 **Schema version control** per project  
- 🤖 **Auto-recommendation engine** for linking schematics blocks to vehicle functions  
- 👤 **User authentication** system for secured access  
- 📊 **Streamlit interface** with modular navigation (Explorer, Element Management, Comparison)  
- 📝 **Excel-compatible output files** ready for GRET import  
- 🧪 **Proof-of-concept validated** and deployed in production environment  

---

## 🧩 Folder Structure

├── app.py # Main Streamlit app
├── launcher.py # Offline launcher
├── Liste_projets.txt # List of available projects
├── data/ # Working Excel files (project-wise)
├── schema_history/ # Loaded schematics and JSON index
├── Extractions/ # Last generated failure files
├── streamlit_offline/ # .whl packages for offline setup
├── wheels/ # Dependencies for connected setup
└── README.md


---

## 🚀 Getting Started

### 🔧 Local installation (online machine)

```bash
pip install -r requirements.txt
streamlit run app.py


python launcher.py


🏗️ Tech Stack
Python 3.10+

Streamlit

Pandas / NumPy

Openpyxl

Custom Excel + JSON structure

No database required (file-based architecture)

🔐 Authentication
Users are authenticated via hashed credentials (user_credentials.json). Auth logic is easily extendable for LDAP or token-based systems.

📈 Impact
Replaced a fully manual Excel-based process

Improved update reliability and traceability for 75,000+ defect records

Deployed in factory environment with no internet access

Helped prepare defect management processes for FlexEVan launch

🧠 Author
Brandon-Christopher Etocha
Data & Industrial Process Intern – Renault Sandouville
📍 France | LinkedIn | Portfolio
