# Démo : Trame sans l'interface générale de Blender.
# blender --python src/trame/scripts/demo_epure.py                 → plan seul, plein écran
# TRAME_DEMO=cote blender --python src/trame/scripts/demo_epure.py → plan + 3D côte à côte
# This file was generated with the assistance of an AI coding tool.
import math
import os

import bpy
from mathutils import Quaternion

COTE = os.environ.get("TRAME_DEMO") == "cote"


def plus_tard(f, *args):
    bpy.app.timers.register(lambda: f(*args), first_interval=0.5)  # Blender doit d'abord réorganiser l'écran


def zone_3d(fenetre):
    return [a for a in fenetre.screen.areas if a.type == "VIEW_3D"]


def fenetre_region(a):
    return next(r for r in a.regions if r.type == "WINDOW")


def epurer():
    fenetre = bpy.context.window_manager.windows[0]
    ecran = fenetre.screen
    area = max(zone_3d(fenetre), key=lambda a: a.width * a.height)
    if COTE:
        # Le plein écran interdit de découper : on ferme plutôt les autres zones (la barre du haut reste).
        for autre in [a for a in ecran.areas if a != area]:
            with bpy.context.temp_override(window=fenetre, screen=ecran, area=autre):
                bpy.ops.screen.area_close()
        ecran.show_statusbar = False
        plus_tard(decouper, fenetre)
    else:
        with bpy.context.temp_override(window=fenetre, area=area, region=fenetre_region(area)):
            bpy.ops.screen.screen_full_area(use_hide_panels=True)  # plus de barre du haut, d'arbre, de propriétés
        plus_tard(amenager, fenetre)


def decouper(fenetre):
    (area,) = zone_3d(fenetre)
    with bpy.context.temp_override(window=fenetre, screen=fenetre.screen, area=area, region=fenetre_region(area)):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
    plus_tard(amenager, fenetre)


def amenager(fenetre):
    zones = sorted(zone_3d(fenetre), key=lambda a: a.x)
    plan = zones[0]
    espace = plan.spaces.active
    espace.show_region_ui = True        # panneau Trame à droite du plan
    espace.show_region_toolbar = False  # les outils sont dans le panneau Trame
    espace.show_region_header = False
    espace.show_gizmo_navigate = False
    espace.overlay.show_text = False
    espace.overlay.show_cursor = False
    if COTE:
        droite = zones[-1]
        from trame.bim.module.model.trame_plan import _vues_plan

        _vues_plan.discard(droite.as_pointer())  # la zone d'origine (vue en plan) a pu se retrouver à droite
        with bpy.context.temp_override(window=fenetre, area=plan, region=fenetre_region(plan)):
            bpy.ops.bim.trame_vue_plan()
        e3d = droite.spaces.active
        e3d.show_region_ui = e3d.show_region_toolbar = e3d.show_region_header = False
        e3d.overlay.show_text = False
        with bpy.context.temp_override(window=fenetre, area=droite, region=fenetre_region(droite)):
            if e3d.local_view:
                bpy.ops.view3d.localview(frame_selected=False)
        e3d.region_3d.view_perspective = "PERSP"
        e3d.region_3d.view_rotation = Quaternion((0, 0, 1), math.radians(-45)) @ Quaternion((1, 0, 0), math.radians(60))
        e3d.shading.background_type, e3d.shading.light, e3d.shading.color_type = "THEME", "STUDIO", "MATERIAL"
        e3d.shading.show_object_outline = False
    if os.environ.get("TRAME_DEMO_MAISON"):  # pour les captures : une petite maison
        with bpy.context.temp_override(window=fenetre, area=plan, region=fenetre_region(plan)):
            bpy.ops.bim.trame_reglages_mur(points="0,0;9,0;9,7;0,7;0,0", z=0, epaisseur=0.3, hauteur=2.7)
            bpy.ops.object.select_all(action="DESELECT")
        for a in zone_3d(fenetre):
            with bpy.context.temp_override(window=fenetre, area=a, region=fenetre_region(a)):
                bpy.ops.view3d.view_all()
    if capture := os.environ.get("TRAME_DEMO_CAPTURE"):
        def prendre():
            with bpy.context.temp_override(window=fenetre):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                bpy.ops.screen.screenshot(filepath=capture)
            bpy.ops.wm.quit_blender()
        bpy.app.timers.register(prendre, first_interval=2)


bpy.app.timers.register(epurer, first_interval=6)  # après le démarrage de Trame (vue en plan, outil Mur)
