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
from trame.bim.module.model.wall import DumbWallGenerator, DumbWallJoiner


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


def extremites_murs(z: float) -> list:
    """Extrémités de l'axe de chaque mur du projet, ramenées à la hauteur de l'étage courant."""
    f = tool.Ifc.get()
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    points = []
    for mur in f.by_type("IfcWall"):
        obj = tool.Ifc.get_object(mur)
        axe = ifcopenshell.util.representation.get_representation(mur, "Plan", "Axis", "GRAPH_VIEW")
        if not obj or not axe or not axe.Items:
            continue
        courbe = axe.Items[0]
        if courbe.is_a("IfcIndexedPolyCurve"):
            coords = courbe.Points.CoordList
        elif courbe.is_a("IfcPolyline"):
            coords = [p.Coordinates for p in courbe.Points]
        else:
            continue
        for c in (coords[0], coords[-1]):
            p = obj.matrix_world @ Vector((c[0] * unit_scale, c[1] * unit_scale, 0))
            points.append(Vector((p.x, p.y, z)))
    return points


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


def creer_murs(points: list, z: float, epaisseur: float, hauteur: float) -> list:
    """Un mur par segment, raccordés en angle ; chaîne fermée si le dernier point rejoint le premier."""
    murs = []
    for a, b in zip(points, points[1:]):
        d = Vector(b) - Vector(a)
        murs.append(creer_mur(a[0], a[1], z, d.length, math.degrees(math.atan2(d.y, d.x)), epaisseur, hauteur))
    ferme = len(points) > 3 and (Vector(points[0]) - Vector(points[-1])).length < 1e-6
    paires = zip(murs, murs[1:] + murs[:1]) if ferme else zip(murs, murs[1:])
    for m1, m2 in paires:
        DumbWallJoiner().connect(m2, m1)
    return murs


class TRAME_OT_reglages_mur(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_mur"
    bl_label = "Mur"
    bl_description = "Régler et créer le mur dessiné"
    bl_options = {"REGISTER", "UNDO"}

    # Points cliqués « x,y;x,y;… » : fournis par l'outil, jamais affichés.
    points: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    longueur: bpy.props.FloatProperty(name="Longueur", unit="LENGTH", min=0.01, options={"SKIP_SAVE"})
    angle: bpy.props.FloatProperty(name="Angle (°)", min=-360, max=360, options={"SKIP_SAVE"})
    # Épaisseur et hauteur sont mémorisées d'un mur à l'autre.
    epaisseur: bpy.props.FloatProperty(name="Épaisseur", unit="LENGTH", default=0.20, min=0.01, max=2)
    hauteur: bpy.props.FloatProperty(name="Hauteur", unit="LENGTH", default=2.50, min=0.1, max=50)

    def invoke(self, context, event):
        titre = "Mur" if len(self.liste_points()) == 2 else "Murs"
        return context.window_manager.invoke_props_dialog(self, title=titre, confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        pts = self.liste_points()
        # Longueur et angle ne se corrigent que pour un mur seul ; une chaîne garde le tracé.
        props = ("epaisseur", "hauteur", "longueur", "angle") if len(pts) == 2 else ("epaisseur", "hauteur")
        for prop in props:
            col.prop(self, prop)
        if len(pts) > 2:
            col.label(text=f"{len(pts) - 1} murs raccordés")

    def liste_points(self) -> list:
        return [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]

    def _execute(self, context):
        pts = self.liste_points()
        if len(pts) == 2:
            a = math.radians(self.angle)
            pts[1] = (pts[0][0] + self.longueur * math.cos(a), pts[0][1] + self.longueur * math.sin(a))
        creer_murs(pts, self.z, self.epaisseur, self.hauteur)
        return {"FINISHED"}


class TRAME_OT_dessiner_mur(bpy.types.Operator):
    bl_idname = "bim.trame_dessiner_mur"
    bl_label = "Dessiner des murs"
    bl_description = (
        "Cliquez les points des murs à la suite. Double-clic, Entrée ou clic droit : terminer. "
        "Clic sur le premier point : fermer. Maj : angle par 45°. Retour arrière : annuler le dernier point. Échap : tout annuler"
    )
    bl_options = {"REGISTER"}

    AIDE = "Cliquez le point suivant   •   Double-clic / Entrée : terminer   •   Premier point : fermer   •   Maj : 45°   •   ⌫ : dernier point   •   Échap : annuler"
    RAYON_FERMETURE_PX = 12

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None and context.area and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        self.z = niveau_etage()
        self.cibles = extremites_murs(self.z)
        self.points = []
        depart = self.accroche(context, event) or point_sous_souris(context, event, self.z)
        if depart is None:
            return {"CANCELLED"}
        self.points = [depart]
        self.fin = depart.copy()
        self.poignee = bpy.types.SpaceView3D.draw_handler_add(self.dessiner_lignes, (), "WINDOW", "POST_VIEW")
        self.poignee_texte = bpy.types.SpaceView3D.draw_handler_add(
            self.dessiner_longueur, (context,), "WINDOW", "POST_PIXEL"
        )
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(self.AIDE)
        return {"RUNNING_MODAL"}

    def accroche(self, context, event):
        """Point d'accroche (extrémité de mur ou point déjà cliqué) sous la souris, à quelques pixels près."""
        souris = Vector((event.mouse_region_x, event.mouse_region_y))
        meilleur, distance = None, self.RAYON_FERMETURE_PX
        for cible in self.cibles + self.points[:-1]:
            p = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, cible)
            if p is not None and (d := (p - souris).length) < distance:
                meilleur, distance = cible.copy(), d
        self.accroche_active = meilleur is not None
        return meilleur

    def pres_du_premier_point(self, context, event) -> bool:
        if len(self.points) < 3:
            return False
        p = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, self.points[0])
        return p is not None and (p - Vector((event.mouse_region_x, event.mouse_region_y))).length < self.RAYON_FERMETURE_PX

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"PASS_THROUGH"}  # laisser naviguer dans la vue pendant le tracé
        if event.type == "MOUSEMOVE":
            if self.pres_du_premier_point(context, event):
                self.fin = self.points[0].copy()
                self.accroche_active = True
            elif cible := self.accroche(context, event):
                self.fin = cible
            elif p := point_sous_souris(context, event, self.z):
                self.fin = contraindre(self.points[-1], p, event.shift)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            self.terminer(context)
            return {"CANCELLED"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            if len(self.points) > 1:
                self.points.pop()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "DOUBLE_CLICK":
            return self.valider(context)
        if event.type in {"RET", "NUMPAD_ENTER", "RIGHTMOUSE"} and event.value == "PRESS":
            return self.valider(context)
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if (self.fin - self.points[-1]).length < 0.01:
                return {"RUNNING_MODAL"}  # clic au même endroit : ignoré
            self.points.append(self.fin.copy())
            if (self.fin - self.points[0]).length < 1e-6:
                return self.valider(context)  # contour fermé
        return {"RUNNING_MODAL"}

    def valider(self, context):
        self.terminer(context)
        if len(self.points) < 2:
            return {"CANCELLED"}
        pts = self.points[:]
        d = pts[1] - pts[0]
        bpy.ops.bim.trame_reglages_mur(
            "INVOKE_DEFAULT",
            points=";".join(f"{p.x:.6f},{p.y:.6f}" for p in pts),
            z=self.z,
            longueur=round(d.length, 3),
            angle=round(math.degrees(math.atan2(d.y, d.x)), 2),
        )
        return {"FINISHED"}

    def terminer(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self.poignee, "WINDOW")
        bpy.types.SpaceView3D.draw_handler_remove(self.poignee_texte, "WINDOW")
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def dessiner_lignes(self):
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.line_width_set(3)
        sommets = self.points + [self.fin]
        segments = [p for a, b in zip(sommets, sommets[1:]) for p in (a, b)]
        batch = batch_for_shader(shader, "LINES", {"pos": segments})
        shader.uniform_float("color", (0.1, 0.6, 1.0, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1)

    def dessiner_repere(self, context):
        p = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, self.fin)
        if p is None:
            return
        cercle = [(p.x + 8 * math.cos(a * math.pi / 8), p.y + 8 * math.sin(a * math.pi / 8), 0) for a in range(17)]
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.line_width_set(2)
        batch = batch_for_shader(shader, "LINE_STRIP", {"pos": cercle})
        shader.uniform_float("color", (1.0, 0.55, 0.0, 1.0))
        batch.draw(shader)
        gpu.state.line_width_set(1)

    def dessiner_longueur(self, context):
        if getattr(self, "accroche_active", False):
            self.dessiner_repere(context)
        milieu = view3d_utils.location_3d_to_region_2d(
            context.region, context.region_data, (self.points[-1] + self.fin) / 2
        )
        if milieu:
            blf.size(0, 16)
            blf.position(0, milieu.x + 10, milieu.y + 10, 0)
            blf.draw(0, f"{(self.fin - self.points[-1]).length:.2f} m")
