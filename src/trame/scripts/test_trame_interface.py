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
                                           "bim.door_tool", "bim.window_tool", "bim.stair_flight_tool", "bim.trame_coupe_tool")]
        if archi != ["bim.wall_tool", "bim.slab_tool", "bim.roof_tool", "bim.column_tool",
                     "bim.door_tool", "bim.window_tool", "bim.stair_flight_tool", "bim.trame_coupe_tool"]:
            erreurs.append(f"boîte à outils : {archi}")
        # Vue en plan coupée à 1 m.
        bpy.ops.bim.trame_vue_plan()
        rv3d = area.spaces.active.region_3d
        if not rv3d.use_clip_planes or round(rv3d.clip_planes[5][3], 2) != 1.0:
            erreurs.append("plan non coupé à 1 m")
        # 3D dans une fenêtre à part, non coupée.
        n = len(bpy.context.window_manager.windows)
        bpy.ops.bim.trame_ouvrir_3d()
        fen3d = bpy.context.window_manager.windows[-1]
        a3d = next(a for a in fen3d.screen.areas if a.type == "VIEW_3D")
        if len(bpy.context.window_manager.windows) != n + 1 or a3d.spaces.active.region_3d.use_clip_planes:
            erreurs.append("fenêtre 3D")
        # Coupe : fenêtre à part qui regarde par la caméra de coupe.
        bpy.ops.bim.trame_reglages_coupe(points="0,0;8,0", nom="Coupe test", profondeur=10)
        fencoupe = bpy.context.window_manager.windows[-1]
        acoupe = next(a for a in fencoupe.screen.areas if a.type == "VIEW_3D")
        if acoupe.spaces.active.region_3d.view_perspective != "CAMERA" or acoupe.spaces.active.camera.name != "Coupe test":
            erreurs.append("fenêtre de coupe")
    # Panneau Trame enregistré et dessinable.
    if not hasattr(bpy.types, "TRAME_PT_panneau"):
        erreurs.append("panneau absent")
    print("INTERFACE", "OK" if not erreurs else erreurs, flush=True)
    bpy.ops.wm.quit_blender()

bpy.app.timers.register(verifier, first_interval=4)
