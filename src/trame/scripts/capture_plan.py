# Capture d'écran d'un petit plan (contrôle visuel des hachures, cotes et symboles) : blender --python src/trame/scripts/capture_plan.py → /tmp/trame_plan.png
import bpy
def go():
    from trame.bim.module.model.trame_outils import mur_sous_point
    from mathutils import Vector
    fen = bpy.context.window_manager.windows[0]
    area = next(a for a in fen.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=fen, area=area, region=region):
        bpy.ops.bim.trame_reglages_mur(points="0,0;8,0;8,6;0,6;0,0", z=0, epaisseur=0.3, hauteur=2.7)
        bpy.ops.bim.trame_reglages_mur(points="4,0;4,6", z=0, longueur=6, angle=90, epaisseur=0.1, hauteur=2.7)
        m, p = mur_sous_point(Vector((2, 0.1, 0)), 0)
        bpy.ops.bim.trame_reglages_porte(mur=m.id(), position=p, z=0, largeur=0.9, hauteur=2.1)
        m, p = mur_sous_point(Vector((8.1, 3, 0)), 0)
        bpy.ops.bim.trame_reglages_fenetre(mur=m.id(), position=p, z=0, largeur=1.4, hauteur=1.35, allege=0.9)
        bpy.ops.bim.trame_reglages_poteau(x=6, y=3, z=0, largeur=0.3, profondeur=0.3, hauteur=2.7)
        bpy.ops.bim.trame_creer_cote(points="0,0;4,0;8,0", decalage=-1.2, z=0)
        bpy.ops.bim.trame_creer_cote(points="8,0;8,6", decalage=-1.2, z=0)
        bpy.ops.bim.trame_vue_plan()
        area.spaces.active.show_region_ui = False
        bpy.ops.view3d.view_all()
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
    bpy.app.timers.register(capturer, first_interval=2)

def capturer():
    bpy.ops.screen.screenshot(filepath="/tmp/trame_plan.png")
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(go, first_interval=4)
