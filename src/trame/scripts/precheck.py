# Vérification avant tout test : importe le code de Trame SANS activer l'extension.
# Si l'activation échouait, Blender effacerait les dépendances installées ; ici une erreur reste sans dégât.
# blender -b --python src/trame/scripts/precheck.py
import importlib, sys, traceback
modules = ["trame", "trame.tool", "trame.bim.module.model", "trame.bim.handler", "trame.bim.ui", "trame.core.project"]
try:
    for nom in modules:
        importlib.import_module(nom)
except Exception:
    traceback.print_exc()
    print("PRECHECK ECHEC")
    sys.exit(1)
print("PRECHECK OK")
