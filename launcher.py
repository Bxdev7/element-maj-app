# launcher.py
import os
import sys
from streamlit.web import bootstrap

# On se place toujours dans le dossier de l’appli
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# On passe à Streamlit l’argument "run app.py"
sys.argv = ["streamlit", "run", "app.py", "--server.headless", "true"]
bootstrap.run()
