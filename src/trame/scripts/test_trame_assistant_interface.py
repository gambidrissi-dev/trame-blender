# Test de l'assistant dans une vraie fenêtre (fil d'arrière-plan + outils sur le fil principal), faux client.
# blender --python src/trame/scripts/test_trame_assistant_interface.py
import time
from types import SimpleNamespace as N

import bpy

TOURS = [
    N(stop_reason="tool_use", content=[N(type="tool_use", id="t1", name="creer_murs", input={
        "points": [[0, 0], [6, 0], [6, 4], [0, 4], [0, 0]], "epaisseur": 0.2, "hauteur": 2.5, "materiau": "Maçonnerie"})]),
    N(stop_reason="end_turn", content=[N(type="text", text="Quatre murs créés.")]),
]


class FauxClient:
    def __init__(self):
        self.n = 0
        self.beta = N(messages=N(create=self.create))

    def create(self, **kwargs):
        time.sleep(0.3)  # comme un vrai appel réseau
        self.n += 1
        return TOURS[self.n - 1]


def lancer():
    import trame.bim.module.model.trame_assistant as a
    a.client_claude = lambda: FauxClient()
    bpy.context.window_manager.trame_demande = "Quatre murs de 6 × 4"
    fen = bpy.context.window_manager.windows[0]
    area = next(x for x in fen.screen.areas if x.type == "VIEW_3D")
    with bpy.context.temp_override(window=fen, area=area):
        bpy.ops.bim.trame_assistant()
    bpy.app.timers.register(verifier, first_interval=3)


def verifier():
    import trame.tool as tool
    from trame.bim.module.model.trame_assistant import _Etat
    murs = len(tool.Ifc.get().by_type("IfcWall"))
    ok = not _Etat.en_cours and murs == 4 and _Etat.lignes[-1] == "Quatre murs créés."
    print("ASSISTANT INTERFACE", "OK" if ok else f"ECHEC murs={murs} en_cours={_Etat.en_cours} lignes={_Etat.lignes}", flush=True)
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(lancer, first_interval=4)
