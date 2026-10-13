# Test de l'assistant IA sans appel réel à l'API : un faux client joue les réponses de Claude.
# blender -b --python src/trame/scripts/test_trame_assistant.py
from types import SimpleNamespace as N

import bpy

bpy.ops.preferences.addon_enable(module="bl_ext.user_default.trame")
import trame.tool as tool
from trame.bim.module.model.trame_assistant import OUTILS, MODELE, converser

bpy.ops.bim.create_project()
f = tool.Ifc.get()


def appel(id_, nom, entree):
    return N(type="tool_use", id=id_, name=nom, input=entree)


# Ce que « Claude » répond, tour par tour.
TOURS = [
    N(stop_reason="tool_use", content=[appel("t1", "etat_du_projet", {})]),
    N(stop_reason="tool_use", content=[
        appel("t2", "creer_murs", {"points": [[0, 0], [10, 0], [10, 8], [0, 8], [0, 0]], "epaisseur": 0.3,
                                   "hauteur": 2.7, "materiau": "Maçonnerie"}),
        appel("t3", "creer_dalle", {"points": [[0, 0], [10, 0], [10, 8], [0, 8]], "epaisseur": 0.2, "materiau": "Béton"}),
    ]),
    N(stop_reason="tool_use", content=[
        appel("t4", "creer_porte", {"point": [5, 0], "largeur": 0.9, "hauteur": 2.1, "ouverture": "SINGLE_SWING_LEFT"}),
        appel("t5", "creer_fenetre", {"point": [10, 4], "largeur": 1.2, "hauteur": 1.35, "allege": 0.9,
                                      "vantaux": "SINGLE_PANEL"}),
        appel("t6", "creer_porte", {"point": [50, 50], "largeur": 0.9, "hauteur": 2.1, "ouverture": "SINGLE_SWING_LEFT"}),
        appel("t7", "creer_toit", {"points": [], "forme": "DEUX_PANS", "pente": 35, "epaisseur": 0.25, "debord": 0.4}),
    ]),
    N(stop_reason="end_turn", content=[N(type="text", text="Maison de 10 × 8 m créée avec porte, fenêtre et toit.")]),
]


class FauxClient:
    def __init__(self):
        self.requetes = []
        self.beta = N(messages=N(create=self.create))

    def create(self, **kwargs):
        self.requetes.append({**kwargs, "messages": list(kwargs["messages"])})
        return TOURS[len(self.requetes) - 1]


client = FauxClient()
historique = []
reponse = converser(client, historique, "Une maison de 10 × 8 m avec une porte au sud, une fenêtre à l'est et un toit",
                    executer=lambda fonction: fonction(), journal=lambda t: None)

# Réponse finale et requêtes conformes (modèle, repli serveur, outils stricts, pas de choix d'outil forcé).
assert reponse.startswith("Maison de 10 × 8 m"), reponse
assert len(client.requetes) == 4
r0 = client.requetes[0]
assert r0["model"] == MODELE == "claude-opus-5-5" and r0["fallbacks"] == "default"
assert r0["betas"] == ["server-side-fallback-2026-07-01"] and "tool_choice" not in r0
assert all(o["strict"] and o["input_schema"]["additionalProperties"] is False for o in OUTILS)
assert all(set(o["input_schema"]["required"]) == set(o["input_schema"]["properties"]) for o in OUTILS)

# Historique en ajout seul : user, assistant, user (tous les résultats ensemble), …
roles = [m["role"] for m in historique]
assert roles == ["user", "assistant", "user", "assistant", "user", "assistant", "user", "assistant"], roles
resultats_tour3 = historique[6]["content"]
assert [r["tool_use_id"] for r in resultats_tour3] == ["t4", "t5", "t6", "t7"]
erreur = next(r for r in resultats_tour3 if r["tool_use_id"] == "t6")
assert erreur.get("is_error") and "Aucun mur" in erreur["content"]  # l'erreur est rendue à Claude
assert '"etages"' in historique[2]["content"][0]["content"]  # l'état du projet est bien envoyé

# La maquette contient ce qui a été demandé.
compte = {c: len(f.by_type(c)) for c in ("IfcWall", "IfcSlab", "IfcDoor", "IfcWindow", "IfcRoof")}
assert compte == {"IfcWall": 4, "IfcSlab": 1, "IfcDoor": 1, "IfcWindow": 1, "IfcRoof": 1}, compte
print("TEST ASSISTANT OK")
