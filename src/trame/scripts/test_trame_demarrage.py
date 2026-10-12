# Test du démarrage Trame (ouvre une fenêtre Blender quelques secondes) : blender --python src/trame/scripts/test_trame_demarrage.py
import bpy
def verifier():
    import trame.tool as tool
    f = tool.Ifc.get()
    outils = set()
    for area in bpy.context.window.screen.areas:
        if area.type == "VIEW_3D":
            with bpy.context.temp_override(area=area):
                outils.add(bpy.context.workspace.tools.from_space_view3d_mode("OBJECT").idname)
            vue = area.spaces.active.region_3d.view_perspective
    etages = [s.Name for s in f.by_type("IfcBuildingStorey")] if f else None
    print("DEMARRAGE", "projet:", bool(f), "etages:", etages, "outil:", outils, "vue:", vue,
          "langue:", bpy.context.preferences.view.language, flush=True)
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(verifier, first_interval=4)
