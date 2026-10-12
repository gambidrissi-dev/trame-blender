# Trame - outil Mur façon Archicad : clic de départ, clic d'arrivée, puis une fenêtre de réglages.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import math

import bpy
import blf
import gpu
import ifcopenshell
import ifcopenshell.api.material
import ifcopenshell.api.root
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.unit
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

import trame.tool as tool
from trame.bim.module.model.wall import DumbWallGenerator


def niveau_etage() -> float:
    return tool.Root.get_default_container_elevation()


def point_sous_souris(context, event, z: float):
    """Projette la souris sur le plan horizontal de l'étage courant."""
    region, rv3d = context.region, context.region_data
    coord = (event.mouse_region_x, event.mouse_region_y)
    origine = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    if abs(direction.z) < 1e-9:
        return None
    t = (z - origine.z) / direction.z
    return origine + direction * t


def contraindre(depart: Vector, fin: Vector, orthogonal: bool) -> Vector:
    """Maj enfoncée : angle bloqué par pas de 45°, comme dans Archicad."""
    if not orthogonal:
        return fin
    d = fin - depart
    angle = round(math.atan2(d.y, d.x) / (math.pi / 4)) * (math.pi / 4)
    return depart + Vector((math.cos(angle), math.sin(angle), 0)) * d.length


def type_de_mur(epaisseur_m: float) -> ifcopenshell.entity_instance:
    """Retrouve ou crée le type « Mur N cm » avec une couche de l'épaisseur voulue."""
    f = tool.Ifc.get()
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    nom = f"Mur {epaisseur_m * 100:g} cm"
    for t in f.by_type("IfcWallType"):
        if t.Name == nom:
            return t
    wall_type = ifcopenshell.api.root.create_entity(f, ifc_class="IfcWallType", name=nom)
    materiau = next((m for m in f.by_type("IfcMaterial") if m.Name == "Maçonnerie"), None) or (
        ifcopenshell.api.material.add_material(f, name="Maçonnerie", category="concrete")
    )
    jeu = ifcopenshell.api.material.add_material_set(f, name=nom, set_type="IfcMaterialLayerSet")
    couche = ifcopenshell.api.material.add_layer(f, layer_set=jeu, material=materiau)
    couche.LayerThickness = epaisseur_m / unit_scale
    ifcopenshell.api.material.assign_material(f, products=[wall_type], material=jeu)
    return wall_type


def creer_mur(x: float, y: float, z: float, longueur: float, angle_deg: float, epaisseur: float, hauteur: float):
    gen = DumbWallGenerator(type_de_mur(epaisseur))
    gen.file = tool.Ifc.get()
    gen.layers = tool.Model.get_material_layer_parameters(gen.relating_type)
    gen.body_context = ifcopenshell.util.representation.get_context(gen.file, "Model", "Body", "MODEL_VIEW")
    gen.axis_context = ifcopenshell.util.representation.get_context(gen.file, "Plan", "Axis", "GRAPH_VIEW")
    gen.container = tool.Root.get_default_container()
    gen.container_obj = tool.Ifc.get_object(gen.container) if gen.container else None
    gen.width = gen.layers["thickness"]
    gen.height = hauteur
    gen.length = longueur
    gen.rotation = math.radians(angle_deg)
    gen.location = Vector((x, y, z))
    gen.x_angle = 0
    return gen.create_wall()


class TRAME_OT_reglages_mur(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_mur"
    bl_label = "Mur"
    bl_description = "Régler et créer le mur dessiné"
    bl_options = {"REGISTER", "UNDO"}

    # Position du clic de départ : fournie par l'outil, jamais affichée.
    x: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    y: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    longueur: bpy.props.FloatProperty(name="Longueur", unit="LENGTH", min=0.01, options={"SKIP_SAVE"})
    angle: bpy.props.FloatProperty(name="Angle (°)", min=-360, max=360, options={"SKIP_SAVE"})
    # Épaisseur et hauteur sont mémorisées d'un mur à l'autre.
    epaisseur: bpy.props.FloatProperty(name="Épaisseur", unit="LENGTH", default=0.20, min=0.01, max=2)
    hauteur: bpy.props.FloatProperty(name="Hauteur", unit="LENGTH", default=2.50, min=0.1, max=50)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Mur", confirm_text="Créer le mur")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        for prop in ("epaisseur", "hauteur", "longueur", "angle"):
            col.prop(self, prop)

    def _execute(self, context):
        creer_mur(self.x, self.y, self.z, self.longueur, self.angle, self.epaisseur, self.hauteur)
        return {"FINISHED"}


class TRAME_OT_dessiner_mur(bpy.types.Operator):
    bl_idname = "bim.trame_dessiner_mur"
    bl_label = "Dessiner un mur"
    bl_description = "Cliquez le point de départ puis le point d'arrivée du mur (Maj : angle par pas de 45°, Échap : annuler)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None and context.area and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        self.z = niveau_etage()
        self.depart = point_sous_souris(context, event, self.z)
        if self.depart is None:
            return {"CANCELLED"}
        self.fin = self.depart.copy()
        self.poignee = bpy.types.SpaceView3D.draw_handler_add(self.dessiner_ligne, (), "WINDOW", "POST_VIEW")
        self.poignee_texte = bpy.types.SpaceView3D.draw_handler_add(
            self.dessiner_longueur, (context,), "WINDOW", "POST_PIXEL"
        )
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Cliquez le point d'arrivée du mur   •   Maj : angle par 45°   •   Échap : annuler")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"PASS_THROUGH"}  # laisser naviguer dans la vue pendant le tracé
        if event.type == "MOUSEMOVE":
            if p := point_sous_souris(context, event, self.z):
                self.fin = contraindre(self.depart, p, event.shift)
            return {"RUNNING_MODAL"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self.terminer(context)
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            d = self.fin - self.depart
            self.terminer(context)
            if d.length < 0.01:
                return {"CANCELLED"}
            bpy.ops.bim.trame_reglages_mur(
                "INVOKE_DEFAULT",
                x=self.depart.x,
                y=self.depart.y,
                z=self.z,
                longueur=round(d.length, 3),
                angle=round(math.degrees(math.atan2(d.y, d.x)), 2),
            )
            return {"FINISHED"}
        return {"RUNNING_MODAL"}

    def terminer(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self.poignee, "WINDOW")
        bpy.types.SpaceView3D.draw_handler_remove(self.poignee_texte, "WINDOW")
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def dessiner_ligne(self):
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.line_width_set(3)
        batch = batch_for_shader(shader, "LINES", {"pos": [self.depart, self.fin]})
        shader.uniform_float("color", (0.1, 0.6, 1.0, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1)

    def dessiner_longueur(self, context):
        milieu = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, (self.depart + self.fin) / 2)
        if milieu:
            blf.size(0, 16)
            blf.position(0, milieu.x + 10, milieu.y + 10, 0)
            blf.draw(0, f"{(self.fin - self.depart).length:.2f} m")
