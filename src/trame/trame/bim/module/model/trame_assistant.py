# Trame - assistant IA : construit la maquette à partir d'une demande en français, avec l'API Claude.
# Claude appelle des outils qui sont les opérations Trame elles-mêmes (annulables avec ⌘Z).
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import json
import math
import queue
import threading

import bpy
import ifcopenshell.util.element

import trame.tool as tool

MODELE = "claude-opus-5-5"

CONSIGNES = """Tu es l'assistant de Trame, un logiciel de conception architecturale (comme Archicad) où l'on \
dessine une maquette IFC. Tu construis ce que l'architecte demande en appelant les outils, puis tu résumes \
en français ce que tu as fait, en une ou deux phrases.

Conventions de Trame :
- Unités en mètres. Plan : X vers l'est, Y vers le nord. Les éléments sont créés sur l'étage actif.
- Un mur s'épaissit à gauche de son sens de tracé : trace les contours extérieurs dans le sens inverse des \
aiguilles d'une montre, la ligne tracée est alors la face extérieure ; ferme un contour en répétant le premier point.
- Portes et fenêtres : donne un point sur le mur, au milieu de l'ouverture.
- Commence par consulter l'état du projet si tu ne le connais pas encore. Si la demande est ambiguë sur un \
point qui change beaucoup le résultat, pose une question courte au lieu de deviner."""


def _nombre(description: str) -> dict:
    return {"type": "number", "description": description}


def _point(description: str = "Point [x, y] en mètres") -> dict:
    return {"type": "array", "items": {"type": "number"}, "description": description}


def _points(description: str) -> dict:
    return {"type": "array", "items": _point(), "description": description}


def _outil(nom: str, description: str, proprietes: dict) -> dict:
    # strict : les arguments sont garantis conformes au schéma.
    return {
        "name": nom, "description": description, "strict": True,
        "input_schema": {"type": "object", "properties": proprietes, "required": list(proprietes),
                         "additionalProperties": False},
    }


def _materiau(defaut: str) -> dict:
    return {"type": "string", "description": f"Nom d'un matériau du projet (par défaut « {defaut} »)"}


OUTILS = [
    _outil("etat_du_projet", "Résumé du projet : étages, étage actif, matériaux, éléments existants et leurs positions.", {}),
    _outil("creer_murs", "Murs le long d'une polyligne (un mur par segment, angles raccordés).", {
        "points": _points("Sommets de la polyligne ; répéter le premier point pour fermer"),
        "epaisseur": _nombre("Épaisseur en mètres, ex. 0.20 (porteur) ou 0.07 (cloison)"),
        "hauteur": _nombre("Hauteur en mètres, ex. 2.50"),
        "materiau": _materiau("Maçonnerie"),
    }),
    _outil("creer_dalle", "Dalle sur un contour fermé ; son dessus est au niveau de l'étage.", {
        "points": _points("Sommets du contour"), "epaisseur": _nombre("Épaisseur en mètres, ex. 0.20"),
        "materiau": _materiau("Béton"),
    }),
    _outil("creer_porte", "Porte dans le mur le plus proche du point donné.", {
        "point": _point("Point sur le mur, au milieu de la porte"),
        "largeur": _nombre("Largeur en mètres, ex. 0.90"), "hauteur": _nombre("Hauteur en mètres, ex. 2.10"),
        "ouverture": {"type": "string", "enum": ["SINGLE_SWING_LEFT", "SINGLE_SWING_RIGHT",
                                                 "DOUBLE_DOOR_SINGLE_SWING", "SLIDING_TO_LEFT"]},
    }),
    _outil("creer_fenetre", "Fenêtre dans le mur le plus proche du point donné.", {
        "point": _point("Point sur le mur, au milieu de la fenêtre"),
        "largeur": _nombre("Largeur en mètres, ex. 1.20"), "hauteur": _nombre("Hauteur en mètres, ex. 1.35"),
        "allege": _nombre("Hauteur d'allège en mètres, ex. 0.90 (0 pour une baie)"),
        "vantaux": {"type": "string", "enum": ["SINGLE_PANEL", "DOUBLE_PANEL_VERTICAL"]},
    }),
    _outil("creer_poteau", "Poteau rectangulaire centré sur un point.", {
        "point": _point(), "largeur": _nombre("Largeur en mètres"), "profondeur": _nombre("Profondeur en mètres"),
        "hauteur": _nombre("Hauteur en mètres"), "materiau": _materiau("Béton"),
    }),
    _outil("creer_toit", "Toit sur un contour, ou sur le contour extérieur des murs de l'étage actif.", {
        "points": _points("Contour du toit ; liste vide pour prendre le contour des murs de l'étage"),
        "forme": {"type": "string", "enum": ["DEUX_PANS", "QUATRE_PANS", "UN_PAN", "PLAT"]},
        "pente": _nombre("Pente en degrés, ex. 35"), "epaisseur": _nombre("Épaisseur en mètres, ex. 0.25"),
        "debord": _nombre("Débord en mètres, ex. 0.40"),
    }),
    _outil("creer_escalier", "Escalier : la première volée va du départ vers l'arrivée.", {
        "depart": _point(), "arrivee": _point("Fin de la première volée"),
        "largeur": _nombre("Largeur en mètres, ex. 1.0"), "hauteur": _nombre("Hauteur à monter en mètres"),
        "forme": {"type": "string", "enum": ["DROIT", "L_GAUCHE", "L_DROITE", "U_GAUCHE", "U_DROITE"]},
    }),
    _outil("creer_velux", "Fenêtre de toit dans le toit au-dessus du point.", {
        "point": _point(), "largeur": _nombre("Largeur en mètres, ex. 0.78"),
        "hauteur": _nombre("Hauteur dans la pente en mètres, ex. 0.98"),
    }),
    _outil("creer_cote", "Cote alignée sur des points, ligne de cote décalée.", {
        "points": _points("Points à coter"), "decalage": _nombre("Décalage de la ligne de cote en mètres (signé)"),
    }),
    _outil("ajouter_etage", "Nouvel étage au-dessus du plus haut ; il devient l'étage actif.", {
        "nom": {"type": "string"}, "hauteur": _nombre("Hauteur d'étage en mètres, ex. 2.70"),
    }),
    _outil("activer_etage", "Rend actif l'étage de ce nom.", {"nom": {"type": "string"}}),
    _outil("creer_materiau", "Nouveau matériau du projet.", {
        "nom": {"type": "string"},
        "famille": {"type": "string", "enum": ["MACONNERIE", "BETON", "BOIS", "ISOLANT", "PLATRE", "PLEIN"]},
        "couleur": {"type": "array", "items": {"type": "number"}, "description": "Couleur 3D [r, g, b] entre 0 et 1"},
    }),
]


# ------------------------------------------------------------------ Exécution des outils (fil principal)


def _texte(pts) -> str:
    return ";".join(f"{float(p[0]):.6f},{float(p[1]):.6f}" for p in pts)


def _niveau() -> float:
    return tool.Root.get_default_container_elevation()


def _apres(op, **kwargs) -> None:
    """Lance une opération Trame et lève une erreur si Blender la refuse."""
    resultat = op(**kwargs)
    if resultat != {"FINISHED"}:
        raise RuntimeError(f"Opération refusée : {resultat}")


def etat_du_projet() -> dict:
    from trame.bim.module.model.trame_outils import axe_mur
    from trame.bim.module.model.trame_panneau import etages

    f = tool.Ifc.get()
    actif = tool.Root.get_default_container()
    resume = {"etage_actif": actif.Name if actif else None,
              "etages": [{"nom": e.Name, "altitude": round(z, 3)} for e, z in etages()],
              "materiaux": sorted(m.Name for m in f.by_type("IfcMaterial")), "elements": {}}
    for etage, z in etages():
        murs = []
        for e in ifcopenshell.util.element.get_decomposition(etage):
            if e.is_a("IfcWall") and (axe := axe_mur(e, z)):
                murs.append([[round(axe[0].x, 2), round(axe[0].y, 2)], [round(axe[1].x, 2), round(axe[1].y, 2)]])
        compte = {}
        for e in ifcopenshell.util.element.get_decomposition(etage):
            compte[e.is_a()] = compte.get(e.is_a(), 0) + 1
        resume["elements"][etage.Name] = {"nombre_par_classe": compte, "axes_des_murs": murs}
    return resume


def executer_outil(nom: str, entree: dict) -> str:
    """Exécute un outil demandé par Claude ; renvoie un texte de résultat (une exception = erreur)."""
    from trame.bim.module.model.trame_outils import contour_des_murs, mur_sous_point
    from trame.bim.module.model.trame_panneau import activer_etage, etages
    from mathutils import Vector

    ops = bpy.ops.bim
    if nom == "etat_du_projet":
        return json.dumps(etat_du_projet(), ensure_ascii=False)
    if nom == "creer_murs":
        pts = entree["points"]
        if len(pts) < 2:
            raise ValueError("Il faut au moins 2 points")
        d = Vector((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]))
        _apres(ops.trame_reglages_mur, points=_texte(pts), z=_niveau(), epaisseur=entree["epaisseur"],
               hauteur=entree["hauteur"], materiau=entree["materiau"],
               longueur=d.length, angle=math.degrees(math.atan2(d.y, d.x)))
        return f"{len(pts) - 1} mur(s) créé(s)"
    if nom == "creer_dalle":
        _apres(ops.trame_reglages_dalle, points=_texte(entree["points"]), z=_niveau(),
               epaisseur=entree["epaisseur"], materiau=entree["materiau"])
        return "Dalle créée"
    if nom in ("creer_porte", "creer_fenetre"):
        z = _niveau()
        trouve = mur_sous_point(Vector((entree["point"][0], entree["point"][1], z)), z)
        if not trouve:
            raise ValueError("Aucun mur à cet endroit : donne un point sur l'axe d'un mur")
        mur, position = trouve
        if nom == "creer_porte":
            _apres(ops.trame_reglages_porte, mur=mur.id(), position=position, z=z, largeur=entree["largeur"],
                   hauteur=entree["hauteur"], modele=entree["ouverture"])
            return "Porte posée"
        _apres(ops.trame_reglages_fenetre, mur=mur.id(), position=position, z=z, largeur=entree["largeur"],
               hauteur=entree["hauteur"], allege=entree["allege"], modele=entree["vantaux"])
        return "Fenêtre posée"
    if nom == "creer_poteau":
        _apres(ops.trame_reglages_poteau, x=entree["point"][0], y=entree["point"][1], z=_niveau(),
               largeur=entree["largeur"], profondeur=entree["profondeur"], hauteur=entree["hauteur"],
               materiau=entree["materiau"])
        return "Poteau posé"
    if nom == "creer_toit":
        z = _niveau()
        pts = entree["points"]
        depart = 2.5
        if not pts:
            pts = contour_des_murs(z)
            if not pts:
                raise ValueError("Aucun mur sur l'étage actif pour poser le toit")
            hauts = [o.dimensions.z for e in ifcopenshell.util.element.get_decomposition(tool.Root.get_default_container())
                     if e.is_a("IfcWall") and (o := tool.Ifc.get_object(e))]
            depart = max(hauts, default=2.5)
        _apres(ops.trame_reglages_toit, points=_texte(pts), z=z, forme=entree["forme"], pente=entree["pente"],
               epaisseur=entree["epaisseur"], depart=depart, debord=entree["debord"])
        return "Toit créé"
    if nom == "creer_escalier":
        hauteur = entree["hauteur"]
        _apres(ops.trame_reglages_escalier, points=_texte([entree["depart"], entree["arrivee"]]), z=_niveau(),
               largeur=entree["largeur"], hauteur=hauteur, marches=max(2, round(hauteur / 0.17)), forme=entree["forme"])
        return "Escalier créé"
    if nom == "creer_velux":
        avant = len(tool.Ifc.get().by_type("IfcWindow"))
        _apres(ops.trame_reglages_velux, x=entree["point"][0], y=entree["point"][1],
               largeur=entree["largeur"], hauteur=entree["hauteur"])
        if len(tool.Ifc.get().by_type("IfcWindow")) == avant:
            raise ValueError("Aucun toit en pente au-dessus de ce point")
        return "Velux posé"
    if nom == "creer_cote":
        _apres(ops.trame_creer_cote, points=_texte(entree["points"]), decalage=entree["decalage"], z=_niveau())
        return "Cote créée"
    if nom == "ajouter_etage":
        _apres(ops.trame_ajouter_etage, nom=entree["nom"], hauteur=entree["hauteur"])
        return f"Étage « {entree['nom']} » ajouté et actif"
    if nom == "activer_etage":
        etage = next((e for e, _ in etages() if e.Name == entree["nom"]), None)
        if not etage:
            raise ValueError(f"Pas d'étage nommé « {entree['nom']} »")
        activer_etage(etage)
        return f"Étage « {entree['nom']} » actif"
    if nom == "creer_materiau":
        _apres(ops.trame_creer_materiau, nom=entree["nom"], famille=entree["famille"], couleur=entree["couleur"][:3])
        return f"Matériau « {entree['nom']} » créé"
    raise ValueError(f"Outil inconnu : {nom}")


# ------------------------------------------------------------------ Conversation avec Claude


def converser(client, historique: list, demande: str, executer, journal=print) -> str:
    """Boucle d'outils : envoie la demande, exécute les outils que Claude appelle, jusqu'à sa réponse finale.

    « executer(fonction) » lance une fonction sur le fil principal de Blender et renvoie son résultat ;
    l'historique est complété en place (on n'y fait qu'ajouter : la conversation peut continuer)."""
    historique.append({"role": "user", "content": demande})
    while True:
        reponse = client.beta.messages.create(
            model=MODELE,
            max_tokens=16000,
            system=CONSIGNES,
            tools=OUTILS,
            messages=historique,
            output_config={"effort": "medium"},
            # Repli automatique côté serveur si le modèle décline la demande.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        historique.append({"role": "assistant", "content": reponse.content})
        if reponse.stop_reason == "refusal":
            return "La demande a été refusée par l'assistant."
        if reponse.stop_reason == "max_tokens":
            return "La réponse a été coupée (trop longue) : reformule ta demande en plus petit."
        appels = [b for b in reponse.content if b.type == "tool_use"]
        if reponse.stop_reason != "tool_use" or not appels:
            return "\n".join(b.text for b in reponse.content if b.type == "text").strip()
        resultats = []
        for appel in appels:
            journal(f"→ {appel.name}")
            try:
                texte = executer(lambda a=appel: executer_outil(a.name, dict(a.input)))
                resultats.append({"type": "tool_result", "tool_use_id": appel.id, "content": texte})
            except Exception as erreur:  # l'erreur est rendue à Claude, qui peut corriger
                resultats.append({"type": "tool_result", "tool_use_id": appel.id,
                                  "content": f"Erreur : {erreur}", "is_error": True})
        historique.append({"role": "user", "content": resultats})  # tous les résultats dans un seul message


# ------------------------------------------------------------------ Lien avec l'interface


class _Etat:
    historique: list = []
    en_cours = False
    lignes: list = []  # journal affiché dans le panneau
    taches: "queue.Queue" = queue.Queue()


def _executer_sur_fil_principal(fonction):
    """Blender ne modifie la maquette que sur son fil principal : on y envoie la fonction et on attend."""
    fini, boite = threading.Event(), {}
    _Etat.taches.put((fonction, fini, boite))
    fini.wait()
    if "erreur" in boite:
        raise boite["erreur"]
    return boite["resultat"]


def _depiler_taches():
    while not _Etat.taches.empty():
        fonction, fini, boite = _Etat.taches.get()
        try:
            boite["resultat"] = fonction()
        except Exception as erreur:
            boite["erreur"] = erreur
        fini.set()
    for fenetre in bpy.context.window_manager.windows:
        for area in fenetre.screen.areas:
            area.tag_redraw()
    return 0.1 if _Etat.en_cours or not _Etat.taches.empty() else None


def client_claude():
    import anthropic

    cle = tool.Blender.get_addon_preferences().trame_cle_api
    # Sans clé saisie, le SDK cherche ANTHROPIC_API_KEY ou un profil « ant auth login ».
    return anthropic.Anthropic(api_key=cle) if cle else anthropic.Anthropic()


def _travailler(demande: str) -> None:
    def journal(texte):
        _Etat.lignes.append(texte)

    try:
        reponse = converser(client_claude(), _Etat.historique, demande, _executer_sur_fil_principal, journal)
        _Etat.lignes.append(reponse or "(fait)")
    except Exception as erreur:
        _Etat.lignes.append(f"Erreur : {erreur}")
    finally:
        _Etat.en_cours = False


class TRAME_OT_assistant(bpy.types.Operator):
    bl_idname = "bim.trame_assistant"
    bl_label = "Demander à l'assistant"
    bl_description = "Construire ou modifier la maquette à partir d'une demande en français (API Claude)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None and not _Etat.en_cours

    def execute(self, context):
        demande = context.window_manager.trame_demande.strip()
        if not demande:
            self.report({"WARNING"}, "Écris d'abord ta demande")
            return {"CANCELLED"}
        _Etat.en_cours = True
        _Etat.lignes.append(f"Toi : {demande}")
        context.window_manager.trame_demande = ""
        threading.Thread(target=_travailler, args=(demande,), daemon=True).start()
        bpy.app.timers.register(_depiler_taches, first_interval=0.1)
        return {"FINISHED"}


class TRAME_OT_nouvelle_conversation(bpy.types.Operator):
    bl_idname = "bim.trame_nouvelle_conversation"
    bl_label = "Nouvelle conversation"
    bl_description = "Oublier la conversation en cours avec l'assistant"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return not _Etat.en_cours

    def execute(self, context):
        _Etat.historique, _Etat.lignes = [], []
        return {"FINISHED"}
