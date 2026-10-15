# Test de chaque outil avec de vrais clics de souris simulés (ouvre une fenêtre Blender quelques secondes) :
# blender --enable-event-simulate --python src/trame/scripts/test_trame_clics.py
# This file was generated with the assistance of an AI coding tool.
import math

import bpy
from mathutils import Euler, Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

etapes, erreurs = [], []


def zone():
    fenetre = bpy.context.window_manager.windows[-1]  # la dernière fenêtre ouverte (plan, puis 3D)
    area = next(a for a in fenetre.screen.areas if a.type == "VIEW_3D")
    return fenetre, area, next(r for r in area.regions if r.type == "WINDOW")


def cliquer(*points):
    """Clic gauche à l'endroit de l'écran où se trouve chaque point 3D (z = 0 si absent)."""
    fenetre, area, region = zone()
    for point in points:
        p = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector((*point, 0)[:3]))
        assert p and 0 < p.x < region.width and 0 < p.y < region.height, f"{point} hors de l'écran"
        x, y = int(p.x + region.x), int(p.y + region.y)
        fenetre.event_simulate("MOUSEMOVE", "NOTHING", x=x, y=y)
        fenetre.event_simulate("LEFTMOUSE", "PRESS", x=x, y=y)
        fenetre.event_simulate("LEFTMOUSE", "RELEASE", x=x, y=y)


def entree():
    zone()[0].event_simulate("RET", "PRESS")
    zone()[0].event_simulate("RET", "RELEASE")


def outil(idname):
    fenetre, area, region = zone()
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=idname)


def compter(classe):
    import trame.tool as tool

    return len(tool.Ifc.get().by_type(classe))


def attendu(nom, classe, nombre):
    """Étape de vérification : après le geste précédent, il y a « nombre » éléments de cette classe."""
    def verifier():
        if compter(classe) != nombre:
            erreurs.append(f"{nom} : {compter(classe)} {classe} au lieu de {nombre}")
    etapes.append(verifier)


def geste(*actions):
    etapes.extend(actions)


def depart():
    fenetre, area, region = zone()
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        bpy.ops.bim.trame_reglages_mur(points="0,0;6,0;6,4", z=0, epaisseur=0.2, hauteur=2.5)
        bpy.ops.bim.trame_reglages_mur(points="0,-3;6,-3", z=0, longueur=6, angle=0, epaisseur=0.5, hauteur=2.5)
        bpy.ops.bim.trame_vue_plan()
    rv3d = area.spaces.active.region_3d
    rv3d.view_location, rv3d.view_distance = (9, 2, 0), 30  # tout le terrain de jeu à l'écran


geste(depart)
# Porte : un clic sur le mur, puis la fenêtre de réglages.
geste(lambda: outil("bim.door_tool"), lambda: cliquer((3, 0)), entree)
attendu("porte en plan", "IfcDoor", 1)
geste(lambda: cliquer((3, -2.55)), entree)  # près de la face d'un mur épais opposée à son axe
attendu("porte près de la face d'un mur épais", "IfcDoor", 2)
# Murs enchaînés : clics, Entrée pour terminer, Entrée pour valider les réglages.
geste(lambda: outil("bim.wall_tool"), lambda: cliquer((10, 0), (14, 0), (14, 3)), entree, entree)
attendu("murs enchaînés", "IfcWall", 5)
geste(lambda: outil("bim.window_tool"), lambda: cliquer((12, 0)), entree)
attendu("fenêtre", "IfcWindow", 1)
# Dalle : contour fermé en recliquant le premier point.
geste(lambda: outil("bim.slab_tool"), lambda: cliquer((10, 0), (14, 0), (14, 3), (10, 3), (10, 0)), entree)
attendu("dalle", "IfcSlab", 1)
geste(lambda: outil("bim.column_tool"), lambda: cliquer((16, 1)), entree)
attendu("poteau", "IfcColumn", 1)
geste(lambda: outil("bim.stair_flight_tool"), lambda: cliquer((16, 3), (19, 3)), entree)
attendu("escalier", "IfcStairFlight", 1)
# Cote : deux points, Entrée, puis un clic pour placer la ligne de cote.
geste(lambda: outil("bim.trame_cote_tool"), lambda: cliquer((10, 0), (14, 0)), entree, lambda: cliquer((12, -1.5)))
attendu("cote", "IfcAnnotation", 1)
geste(lambda: outil("bim.roof_tool"), lambda: cliquer((10, 0), (14, 0), (14, 3), (10, 3), (10, 0)), entree)
attendu("toit", "IfcRoof", 1)
geste(lambda: outil("bim.trame_velux_tool"), lambda: cliquer((12, 1.5)), entree)
attendu("Velux", "IfcWindow", 2)
geste(lambda: outil("bim.trame_terrain_tool"), lambda: cliquer((-2, -6), (21, -6), (21, 8), (-2, 8), (-2, -6)), entree)
attendu("terrain", "IfcGeographicElement", 1)


def ouvrir_3d():
    fenetre, area, region = zone()
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        bpy.ops.bim.trame_ouvrir_3d()


def orienter_3d():
    rv3d = zone()[1].spaces.active.region_3d
    rv3d.view_perspective = "PERSP"
    rv3d.view_location = (6, 2, 1)
    rv3d.view_rotation = Euler((math.radians(60), 0, math.radians(90))).to_quaternion()  # depuis l'est, en plongée
    rv3d.view_distance = 12
    zone()[1].tag_redraw()


# Porte en 3D : clic sur la face d'un mur, en hauteur (la vue doit être redessinée avant le clic).
geste(lambda: outil("bim.door_tool"), ouvrir_3d, orienter_3d, lambda: cliquer((6, 2, 1.8)), entree)
attendu("porte sur la face d'un mur en 3D", "IfcDoor", 3)


def fin():
    print("TEST CLICS", "OK" if not erreurs else f"ECHEC {erreurs}", flush=True)
    bpy.ops.wm.quit_blender()


def suivant():
    try:
        etapes.pop(0)()
    except Exception as e:
        import traceback

        traceback.print_exc()
        erreurs.append(repr(e))
        etapes[:] = []
    if etapes:
        return 0.8
    fin()


bpy.app.timers.register(suivant, first_interval=4)
