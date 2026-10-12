# Trame - panneau « Trame » : outils d'archi, étages, vues (plan coupé, 3D à part) et fichier.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import math

import bpy
import ifcopenshell.util.element
import ifcopenshell.util.unit
from mathutils import Quaternion

import trame.core.aggregate
import trame.core.geometry
import trame.core.root
import trame.tool as tool

from trame.bim.module.model.trame_plan import HAUTEUR_COUPE_PLAN

OUTILS = (
    ("builtin.select_box", "Sélection", "RESTRICT_SELECT_OFF"),
    ("bim.wall_tool", "Mur", "MOD_BUILD"),
    ("bim.slab_tool", "Dalle", "MESH_PLANE"),
    ("bim.roof_tool", "Toit", "MOD_TRIANGULATE"),
    ("bim.column_tool", "Poteau", "MESH_CUBE"),
    ("bim.door_tool", "Porte", "MESH_GRID"),
    ("bim.window_tool", "Fenêtre", "VIEW_ORTHO"),
    ("bim.stair_flight_tool", "Escalier", "SORTSIZE"),
)


def etages() -> list:
    """Étages du projet, du plus haut au plus bas, avec leur altitude (m)."""
    f = tool.Ifc.get()
    if not f:
        return []
    resultat = [(e, o.location.z) for e in f.by_type("IfcBuildingStorey") if (o := tool.Ifc.get_object(e))]
    return sorted(resultat, key=lambda x: -x[1])


def vues_plan():
    """Vues 3D de la fenêtre principale : ce sont les vues en plan (la 3D vit dans une autre fenêtre)."""
    fenetre = bpy.context.window_manager.windows[0]
    for area in fenetre.screen.areas:
        if area.type == "VIEW_3D":
            yield area


def appliquer_coupe_plan(area, z: float, active: bool = True) -> None:
    """Coupe la vue à 1 m au-dessus de l'étage (et juste sous son sol) : on ne voit que l'étage, en plan."""
    rv3d = area.spaces.active.region_3d
    rv3d.use_clip_planes = active
    # Fond blanc comme une feuille de plan ; la fenêtre 3D, elle, garde le fond de Blender.
    ombrage = area.spaces.active.shading
    ombrage.background_type = "VIEWPORT" if active else "THEME"
    ombrage.background_color = (1, 1, 1)
    if active:
        loin = 1e5
        # Plan (a, b, c, d) : un point reste visible si a·x + b·y + c·z + d ≥ 0.
        rv3d.clip_planes = (
            (1, 0, 0, loin), (-1, 0, 0, loin), (0, 1, 0, loin), (0, -1, 0, loin),
            (0, 0, 1, -(z - 0.02)), (0, 0, -1, z + HAUTEUR_COUPE_PLAN),
        )
    area.tag_redraw()


def ajouter_etage(nom: str, hauteur: float):
    """Nouvel étage posé « hauteur » mètres au-dessus de l'étage le plus haut."""
    (haut, z_haut), *_ = etages()
    batiment = ifcopenshell.util.element.get_aggregate(haut)
    obj = bpy.data.objects.new(nom, None)
    obj.location.z = z_haut + hauteur
    trame.core.root.assign_class(
        tool.Ifc, tool.Collector, tool.Root, obj=obj, ifc_class="IfcBuildingStorey", should_add_representation=False
    )
    trame.core.aggregate.assign_object(
        tool.Ifc, tool.Aggregate, tool.Collector, relating_obj=tool.Ifc.get_object(batiment), related_obj=obj
    )
    trame.core.geometry.edit_object_placement(tool.Ifc, tool.Geometry, tool.Surveyor, obj=obj)
    etage = tool.Ifc.get_entity(obj)
    etage.Elevation = obj.location.z / ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
    return etage


def activer_etage(etage) -> None:
    tool.Spatial.set_default_container(etage)
    z = tool.Ifc.get_object(etage).location.z
    for area in vues_plan():
        if area.spaces.active.region_3d.use_clip_planes:
            appliquer_coupe_plan(area, z)


class TRAME_OT_activer_etage(bpy.types.Operator):
    bl_idname = "bim.trame_activer_etage"
    bl_label = "Activer l'étage"
    bl_description = "Dessiner sur cet étage"
    bl_options = {"REGISTER", "UNDO"}
    etage: bpy.props.IntProperty()

    def execute(self, context):
        activer_etage(tool.Ifc.get().by_id(self.etage))
        return {"FINISHED"}


class TRAME_OT_ajouter_etage(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_ajouter_etage"
    bl_label = "Ajouter un étage"
    bl_description = "Ajouter un étage au-dessus du plus haut et dessiner dessus"
    bl_options = {"REGISTER", "UNDO"}
    nom: bpy.props.StringProperty(name="Nom", default="Étage", options={"SKIP_SAVE"})
    hauteur: bpy.props.FloatProperty(name="Hauteur d'étage", unit="LENGTH", default=2.70, min=1, max=20)

    @classmethod
    def poll(cls, context):
        return bool(etages())

    def invoke(self, context, event):
        self.nom = f"R+{len(etages())}"
        return context.window_manager.invoke_props_dialog(self, title="Nouvel étage", confirm_text="Ajouter")

    def _execute(self, context):
        activer_etage(ajouter_etage(self.nom, self.hauteur))
        return {"FINISHED"}


class TRAME_OT_vue_plan(bpy.types.Operator):
    bl_idname = "bim.trame_vue_plan"
    bl_label = "Vue en plan"
    bl_description = "Vue de dessus coupée à 1 m au-dessus de l'étage actif (comme un plan Archicad)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        z = tool.Root.get_default_container_elevation()
        for area in vues_plan():
            region = next(r for r in area.regions if r.type == "WINDOW")
            with context.temp_override(window=context.window_manager.windows[0], area=area, region=region):
                bpy.ops.view3d.view_axis(type="TOP")
            appliquer_coupe_plan(area, z)
        return {"FINISHED"}


def nouvelle_fenetre_3d(context, camera=None) -> None:
    """Ouvre une fenêtre à part : la maquette en 3D, ou la vue d'une caméra de coupe si « camera » est donnée."""
    avant = set(context.window_manager.windows)
    bpy.ops.wm.window_new()
    (fenetre,) = set(context.window_manager.windows) - avant
    for area in fenetre.screen.areas:
        if area.type != "VIEW_3D":
            continue
        espace = area.spaces.active
        rv3d = espace.region_3d
        rv3d.use_clip_planes = False  # la 3D montre tout le bâtiment
        espace.shading.background_type = "THEME"
        region = next(r for r in area.regions if r.type == "WINDOW")
        with context.temp_override(window=fenetre, area=area, region=region):
            if camera:
                espace.use_local_camera = True
                espace.camera = camera
                rv3d.view_perspective = "CAMERA"
                bpy.ops.view3d.view_center_camera()
            else:
                rv3d.view_perspective = "PERSP"
                # Vue axonométrique depuis le sud-ouest, à 30° au-dessus de l'horizon.
                rv3d.view_rotation = Quaternion((0, 0, 1), math.radians(-45)) @ Quaternion((1, 0, 0), math.radians(60))
                bpy.ops.view3d.view_all()


class TRAME_OT_ouvrir_3d(bpy.types.Operator):
    bl_idname = "bim.trame_ouvrir_3d"
    bl_label = "Ouvrir la 3D"
    bl_description = "Ouvrir la maquette en 3D dans une fenêtre à part"
    bl_options = {"REGISTER"}

    def execute(self, context):
        nouvelle_fenetre_3d(context)
        return {"FINISHED"}


class TRAME_PT_panneau(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"  # l'onglet ouvert par défaut : le panneau Trame est visible sans chercher
    bl_label = "Trame"
    bl_order = -100  # tout en haut de l'onglet

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None

    def draw(self, context):
        layout = self.layout
        outil = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        actif = outil.idname if outil else ""

        layout.label(text="Outils")
        grille = layout.grid_flow(columns=2, even_columns=True, align=True)
        for idname, nom, icone in OUTILS:
            grille.operator("wm.tool_set_by_id", text=nom, icon=icone, depress=idname == actif).name = idname

        layout.separator()
        layout.label(text="Étages")
        courant = tool.Root.get_default_container()
        col = layout.column(align=True)
        for etage, z in etages():
            op = col.operator(
                "bim.trame_activer_etage", text=f"{etage.Name}   {z:+.2f} m", depress=etage == courant,
                icon="RADIOBUT_ON" if etage == courant else "RADIOBUT_OFF",
            )
            op.etage = etage.id()
        layout.operator("bim.trame_ajouter_etage", icon="ADD")

        layout.separator()
        layout.label(text="Vues")
        ligne = layout.row(align=True)
        ligne.operator("bim.trame_vue_plan", icon="VIEW_ORTHO")
        ligne.operator("bim.trame_ouvrir_3d", icon="VIEW_PERSPECTIVE")
        ligne = layout.row(align=True)
        ligne.operator("wm.tool_set_by_id", text="Coupe", icon="MOD_BOOLEAN").name = "bim.trame_coupe_tool"
        ligne.operator("wm.tool_set_by_id", text="Cote", icon="DRIVER_DISTANCE").name = "bim.trame_cote_tool"

        layout.separator()
        layout.label(text="Calques")
        from trame.bim.module.model.trame_calques import CALQUES

        existants = {c.Name: c for c in tool.Ifc.get().by_type("IfcPresentationLayerWithStyle")}
        col = layout.column(align=True)
        for nom in CALQUES:
            if not (calque := existants.get(nom)):
                continue
            ligne = col.row(align=True)
            ligne.label(text=nom)
            op = ligne.operator("bim.trame_basculer_calque", text="", emboss=False,
                                icon="HIDE_OFF" if calque.LayerOn else "HIDE_ON")
            op.nom, op.attribut = nom, "LayerOn"
            op = ligne.operator("bim.trame_basculer_calque", text="", emboss=False,
                                icon="LOCKED" if calque.LayerBlocked else "UNLOCKED")
            op.nom, op.attribut = nom, "LayerBlocked"

        layout.separator()
        layout.label(text="Matériaux")
        from trame.bim.module.model.trame_materiaux import famille_de, FAMILLES

        col = layout.column(align=True)
        for m in sorted(tool.Ifc.get().by_type("IfcMaterial"), key=lambda m: m.Name or ""):
            col.label(text=f"{m.Name}  —  {FAMILLES[famille_de(m)][0]}", icon="MATERIAL")
        layout.operator("bim.trame_creer_materiau", icon="ADD")

        layout.separator()
        layout.label(text="Fichier")
        ligne = layout.row(align=True)
        ligne.operator("bim.save_project", text="Enregistrer", icon="FILE_TICK")
        ligne.operator("bim.save_project", text="Enregistrer sous", icon="FILE_NEW").should_save_as = True
        layout.operator("bim.load_project", text="Ouvrir un fichier IFC", icon="FILE_FOLDER")
