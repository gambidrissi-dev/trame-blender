# Test de l'interface Trame dans une vraie fenêtre (s'ouvre quelques secondes) :
# blender --python src/trame/scripts/test_trame_interface.py
import bpy

def verifier():
    import trame.tool as tool
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    erreurs = []
    fenetre = bpy.context.window_manager.windows[0]
    area = next(a for a in fenetre.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        # Boîte à outils : les outils d'archi d'abord, dans l'ordre d'Archicad.
        cls = ToolSelectPanelHelper._tool_class_from_space_type("VIEW_3D")
        ids = []
        for item in cls.tools_from_context(bpy.context, mode="OBJECT"):
            if item is None:
                continue
            premier = item if hasattr(item, "idname") else item[0]  # un outil seul, ou le 1er d'un groupe
            if hasattr(premier, "idname"):
                ids.append(premier.idname)
        archi = [i for i in ids if i in ("bim.wall_tool", "bim.slab_tool", "bim.roof_tool", "bim.column_tool",
                                           "bim.door_tool", "bim.window_tool", "bim.stair_flight_tool", "bim.trame_coupe_tool",
                                           "bim.trame_cote_tool")]
        if archi != ["bim.wall_tool", "bim.slab_tool", "bim.roof_tool", "bim.column_tool",
                     "bim.door_tool", "bim.window_tool", "bim.stair_flight_tool", "bim.trame_coupe_tool",
                     "bim.trame_cote_tool"]:
            erreurs.append(f"boîte à outils : {archi}")
        # Vue en plan coupée à 1 m.
        bpy.ops.bim.trame_vue_plan()
        rv3d = area.spaces.active.region_3d
        from trame.bim.module.model.trame_plan import est_vue_plan
        if not est_vue_plan(area):
            erreurs.append("vue en plan non active")
        if tuple(area.spaces.active.shading.background_color) != (1, 1, 1):
            erreurs.append("fond du plan non blanc")
        # 3D dans une fenêtre à part, non coupée.
        n = len(bpy.context.window_manager.windows)
        bpy.ops.bim.trame_ouvrir_3d()
        fen3d = bpy.context.window_manager.windows[-1]
        a3d = next(a for a in fen3d.screen.areas if a.type == "VIEW_3D")
        if (len(bpy.context.window_manager.windows) != n + 1 or a3d.spaces.active.local_view is not None
                or a3d.spaces.active.shading.background_type != "THEME"):
            erreurs.append("fenêtre 3D")
        # Coupe : fenêtre à part qui regarde par la caméra de coupe.
        bpy.ops.bim.trame_reglages_coupe(points="0,0;8,0", nom="Coupe test", profondeur=10)
        fencoupe = bpy.context.window_manager.windows[-1]
        acoupe = next(a for a in fencoupe.screen.areas if a.type == "VIEW_3D")
        if acoupe.spaces.active.region_3d.view_perspective != "CAMERA" or acoupe.spaces.active.camera.name != "Coupe test":
            erreurs.append("fenêtre de coupe")
    # Plan : un mur, un poteau et une cote, puis on force le dessin de la vue (hachures + cotes).
    from trame.bim.module.model.trame_plan import sections_etage, _poignees
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        bpy.ops.bim.trame_reglages_mur(points="0,0;6,0;6,4", z=0, epaisseur=0.2, hauteur=2.5)
        bpy.ops.bim.trame_reglages_poteau(x=3, y=2, z=0, largeur=0.3, profondeur=0.3, hauteur=2.5)
        bpy.ops.bim.trame_creer_cote(points="0,0;6,0", decalage=-1, z=0)
        bpy.ops.bim.trame_vue_plan()
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    if len(_poignees) != 2:
        erreurs.append("dessin du plan non installé")
    if len([c for c, _ in sections_etage(1.0) if c]) != 3:
        erreurs.append(f"sections : {sections_etage(1.0)}")
    # Plan par étage : un mur du R+1 n'apparaît pas dans le plan du RDC, et inversement.
    from trame.bim.module.model.trame_panneau import ajouter_etage, activer_etage, etages
    with bpy.context.temp_override(window=fenetre, area=area, region=region):
        rdc = tool.Root.get_default_container()
        r1 = ajouter_etage("R+1", 2.8)
        activer_etage(r1)
        bpy.ops.bim.trame_reglages_mur(points="0,10;6,10", z=2.8, longueur=6, angle=0, epaisseur=0.2, hauteur=2.5)
        mur_r1 = tool.Ifc.get_object(max(tool.Ifc.get().by_type("IfcWall"), key=lambda w: w.id()))
        mur_rdc = tool.Ifc.get_object(min(tool.Ifc.get().by_type("IfcWall"), key=lambda w: w.id()))
        espace = area.spaces.active
        if not (mur_r1.local_view_get(espace) and not mur_rdc.local_view_get(espace)):
            erreurs.append("plan du R+1 : visibilité")
        activer_etage(rdc)
        if not (mur_rdc.local_view_get(espace) and not mur_r1.local_view_get(espace)):
            erreurs.append("plan du RDC : visibilité")
    # Panneau Trame enregistré et dessinable.
    if not hasattr(bpy.types, "TRAME_PT_panneau"):
        erreurs.append("panneau absent")
    print("INTERFACE", "OK" if not erreurs else erreurs, flush=True)
    bpy.ops.wm.quit_blender()

bpy.app.timers.register(verifier, first_interval=4)
