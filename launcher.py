"""
*
* @author : Brandon C. Etocha
* @version : Cette version permet de sélectionner les dépendances et d'utiliser streamlit_off
* @deployment : Cette version a été déployée et testée sur les serveurs locaux de l'usine de Renault Sandouville le 01/08/2025 - Version finale
*
"""

import os
import sys
import subprocess
import importlib.util
import socket
import glob
from typing import List

# Configuration
BASE_DIR = ('.')
OFFLINE_WHL_DIR = os.path.join(BASE_DIR, "streamlit_offline")
REQUIRED_PACKAGES = ["streamlit", "pandas", "openpyxl", "numpy", "requests"]
os.chdir(BASE_DIR)
print("Localisation actuelle :", os.getcwd())

def is_package_installed(package: str) -> bool:
    try:
        spec = importlib.util.find_spec(package)
        return spec is not None
    except ImportError:
        return False

def install_packages_offline() -> bool:
    """Tente d'installer les packages en mode hors ligne"""
    whl_files = glob.glob(os.path.join(OFFLINE_WHL_DIR, "*.whl"))
    if not whl_files:
        print("❌ Aucun fichier .whl trouvé dans le dossier offline")
        return False
    
    try:
        print("🔧 Tentative d'installation hors ligne...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-index", "--find-links", OFFLINE_WHL_DIR] + whl_files,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Échec de l'installation hors ligne:\n{e.stderr}")
        return False

def install_packages_online(packages: List[str]) -> bool:
    """Tente d'installer les packages en ligne"""
    try:
        print("🌐 Tentative d'installation en ligne...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        return True
    except subprocess.CalledProcessError:
        return False

def check_dependencies():
    missing = [pkg for pkg in REQUIRED_PACKAGES if not is_package_installed(pkg)]
    
    if not missing:
        print("✅ Toutes les dépendances sont déjà installées")
        return True
    
    print(f"📦 Dépendances manquantes: {', '.join(missing)}")
    
    # Essayer d'abord en mode hors ligne
    if os.path.exists(OFFLINE_WHL_DIR):
        if install_packages_offline():
            # Vérifier à nouveau après installation
            missing = [pkg for pkg in REQUIRED_PACKAGES if not is_package_installed(pkg)]
            if not missing:
                return True
    
    # Si échec hors ligne ou dossier inexistant, essayer en ligne
    print("⚠️ Tentative d'installation en ligne...")
    if install_packages_online(missing):
        return True
    
    print("❌ Impossible d'installer les dépendances nécessaires")
    return False

def get_local_ip() -> str:
    """Obtenir l'adresse IP locale"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def main():
    if not check_dependencies():
        sys.exit(1)
    
    local_ip = get_local_ip()
    port = "3000"
    
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--server.port", port
    ]
    
    print(f"🚀 Lancement de l'application sur http://{local_ip}:{port}")
    try:
        subprocess.Popen(cmd)
    except Exception as e:
        print(f"❌ Erreur lors du lancement: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
