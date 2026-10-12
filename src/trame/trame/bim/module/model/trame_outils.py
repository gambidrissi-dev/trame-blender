# Trame - outils façon Archicad (mur, dalle, porte, fenêtre) : on clique, puis une fenêtre de réglages.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import math
from typing import get_args

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
from mathutils import Matrix, Vector

import trame.tool as tool
import trame.core.root
from trame.bim.module.model import roof as bonsai_toit
from trame.bim.module.model.slab import DumbSlabGenerator
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


def axe_mur(mur: ifcopenshell.entity_instance, z: float):
    """Extrémités (début, fin) de l'axe d'un mur en coordonnées monde, à la hauteur z ; None si inconnu."""
    obj = tool.Ifc.get_object(mur)
    axe = ifcopenshell.util.representation.get_representation(mur, "Plan", "Axis", "GRAPH_VIEW")
    if not obj or not axe or not axe.Items:
        return None
    courbe = axe.Items[0]
    if courbe.is_a("IfcIndexedPolyCurve"):
        coords = courbe.Points.CoordList
    elif courbe.is_a("IfcPolyline"):
        coords = [p.Coordinates for p in courbe.Points]
    else:
        return None
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
    a, b = (obj.matrix_world @ Vector((c[0] * unit_scale, c[1] * unit_scale, 0)) for c in (coords[0], coords[-1]))
    return Vector((a.x, a.y, z)), Vector((b.x, b.y, z))


def extremites_murs(z: float) -> list:
    """Extrémités de l'axe de chaque mur du projet, ramenées à la hauteur de l'étage courant."""
    return [p for mur in tool.Ifc.get().by_type("IfcWall") if (axe := axe_mur(mur, z)) for p in axe]


def mur_sous_point(point: Vector, z: float):
    """Mur le plus proche du point cliqué (à son épaisseur près) : (mur, distance depuis le début de l'axe)."""
    meilleur = None
    for mur in tool.Ifc.get().by_type("IfcWall"):
        if not (axe := axe_mur(mur, z)):
            continue
        a, b = axe
        d = b - a
        if d.length < 1e-6:
            continue
        t = max(0.0, min(1.0, (point - a).dot(d) / d.length_squared))
        ecart = (a + d * t - point).length
        epaisseur = tool.Model.get_material_layer_parameters(ifcopenshell.util.element.get_type(mur) or mur)["thickness"]
        if ecart <= (epaisseur or 0.3) / 2 + 0.15 and (meilleur is None or ecart < meilleur[2]):
            meilleur = (mur, t * d.length, ecart)
    return meilleur[:2] if meilleur else None


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


def type_de_dalle(epaisseur_m: float, prefixe: str = "Dalle", predefini: str = "FLOOR") -> ifcopenshell.entity_instance:
    """Retrouve ou crée le type « Dalle N cm » (ou « Toit-terrasse N cm ») à couches horizontales."""
    f = tool.Ifc.get()
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    nom = f"{prefixe} {epaisseur_m * 100:g} cm"
    for t in f.by_type("IfcSlabType"):
        if t.Name == nom:
            return t
    slab_type = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSlabType", name=nom, predefined_type=predefini)
    materiau = next((m for m in f.by_type("IfcMaterial") if m.Name == "Béton"), None) or (
        ifcopenshell.api.material.add_material(f, name="Béton", category="concrete")
    )
    jeu = ifcopenshell.api.material.add_material_set(f, name=nom, set_type="IfcMaterialLayerSet")
    couche = ifcopenshell.api.material.add_layer(f, layer_set=jeu, material=materiau)
    couche.LayerThickness = epaisseur_m / unit_scale
    ifcopenshell.api.material.assign_material(f, products=[slab_type], material=jeu)
    return slab_type


OUVERTURES_PORTE = (
    ("SINGLE_SWING_LEFT", "Battante à gauche", ""),
    ("SINGLE_SWING_RIGHT", "Battante à droite", ""),
    ("DOUBLE_DOOR_SINGLE_SWING", "Deux vantaux", ""),
    ("SLIDING_TO_LEFT", "Coulissante", ""),
)
VANTAUX_FENETRE = (("SINGLE_PANEL", "Un vantail", ""), ("DOUBLE_PANEL_VERTICAL", "Deux vantaux", ""))


def type_d_ouverture(classe: str, largeur: float, hauteur: float, modele: str = "") -> ifcopenshell.entity_instance:
    """Retrouve ou crée le type paramétrique « Porte 90 × 210 … » / « Fenêtre 120 × 135 … » de Bonsai."""
    f = tool.Ifc.get()
    porte = classe == "IfcDoorType"
    modeles = OUVERTURES_PORTE if porte else VANTAUX_FENETRE
    modele = modele or modeles[0][0]
    libelle = next(m[1] for m in modeles if m[0] == modele).lower()
    nom = f"{'Porte' if porte else 'Fenêtre'} {largeur * 100:g} × {hauteur * 100:g} {libelle}"
    for t in f.by_type(classe):
        if t.Name == nom:
            return t
    # Les paramètres par défaut de Bonsai servent de gabarit ; affectation directe pour ne pas déclencher ses mises à jour.
    defauts = getattr(tool.Blender.get_addon_preferences().default_parameters, "door" if porte else "window")
    defauts["overall_width"], defauts["overall_height"] = largeur, hauteur
    choix = get_args(tool.Model.DoorType if porte else tool.Model.WindowType)
    defauts["door_type" if porte else "window_type"] = choix.index(modele)
    props = tool.Root.get_root_props()
    props.ifc_product = "IfcElementType"
    props.ifc_class = classe
    props.ifc_predefined_type = "DOOR" if porte else "WINDOW"
    props.representation_template = "DOOR" if porte else "WINDOW"
    avant = set(f.by_type(classe))
    bpy.ops.bim.add_element(skip_dialog=True)
    (nouveau,) = set(f.by_type(classe)) - avant
    nouveau.Name = nom
    return nouveau


def creer_dalle(points: list, z: float, epaisseur: float, type_=None):
    gen = DumbSlabGenerator(type_ or type_de_dalle(epaisseur))
    gen.file = tool.Ifc.get()
    gen.unit_scale = ifcopenshell.util.unit.calculate_unit_scale(gen.file)
    gen.body_context = ifcopenshell.util.representation.get_context(gen.file, "Model", "Body", "MODEL_VIEW")
    gen.footprint_context = ifcopenshell.util.representation.get_context(gen.file, "Plan", "FootPrint", "SKETCH_VIEW")
    gen.container = tool.Root.get_default_container()
    gen.container_obj = tool.Ifc.get_object(gen.container) if gen.container else None
    gen.depth = epaisseur
    gen.x_angle = 0
    gen.location = Vector((points[0][0], points[0][1], z))
    gen.polyline = [(p[0] - points[0][0], p[1] - points[0][1], 0.0) for p in points]
    if gen.polyline[0] != gen.polyline[-1]:
        gen.polyline.append(gen.polyline[0])  # une dalle est toujours fermée
    return gen.create_slab()


def creer_ouverture(
    classe: str, mur, position: float, z: float, largeur: float, hauteur: float, allege: float,
    modele: str = "", retourner: bool = False,
):
    """Pose une porte/fenêtre centrée à « position » mètres du début de l'axe du mur ; Bonsai perce le mur.

    « retourner » la bascule de l'autre côté du mur (ouverture vers l'intérieur ou l'extérieur)."""
    type_ = type_d_ouverture(classe, largeur, hauteur, modele)
    a, b = axe_mur(mur, z)
    direction = (b - a).normalized()
    origine = a + direction * (position - largeur / 2)  # l'origine d'une porte Bonsai est son bord gauche
    origine.z = z + allege
    tool.Model.get_model_props().rl2 = allege  # hauteur d'allège utilisée par Bonsai pour les fenêtres
    bpy.context.scene.cursor.location = origine
    obj_mur = tool.Ifc.get_object(mur)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj_mur.select_set(True)
    bpy.context.view_layer.objects.active = obj_mur
    avant = set(tool.Ifc.get().by_type(classe[:-4]))
    bpy.ops.bim.add_occurrence(relating_type_id=type_.id())
    (nouvelle,) = set(tool.Ifc.get().by_type(classe[:-4])) - avant
    obj = tool.Ifc.get_object(nouvelle)
    if retourner:
        selectionner_seul(obj)
        bpy.ops.bim.flip_fill()
    return obj


def selectionner_seul(obj) -> None:
    for o in bpy.context.selected_objects:
        o.select_set(False)
    if obj:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def type_de_poteau(largeur: float, profondeur: float) -> ifcopenshell.entity_instance:
    """Retrouve ou crée le type « Poteau 30 × 30 » (profil rectangulaire en béton)."""
    f = tool.Ifc.get()
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(f)
    nom = f"Poteau {largeur * 100:g} × {profondeur * 100:g}"
    for t in f.by_type("IfcColumnType"):
        if t.Name == nom:
            return t
    column_type = ifcopenshell.api.root.create_entity(f, ifc_class="IfcColumnType", name=nom, predefined_type="COLUMN")
    materiau = next((m for m in f.by_type("IfcMaterial") if m.Name == "Béton"), None) or (
        ifcopenshell.api.material.add_material(f, name="Béton", category="concrete")
    )
    profil = f.create_entity(
        "IfcRectangleProfileDef", ProfileName=nom, ProfileType="AREA",
        XDim=largeur / unit_scale, YDim=profondeur / unit_scale,
    )
    jeu = ifcopenshell.api.material.add_material_set(f, name=nom, set_type="IfcMaterialProfileSet")
    profil_materiau = ifcopenshell.api.material.add_profile(f, profile_set=jeu, material=materiau)
    ifcopenshell.api.material.assign_profile(f, material_profile=profil_materiau, profile=profil)
    ifcopenshell.api.material.assign_material(f, products=[column_type], material=jeu)
    return column_type


def creer_poteau(x: float, y: float, z: float, largeur: float, profondeur: float, hauteur: float):
    """Poteau centré sur le point cliqué."""
    type_ = type_de_poteau(largeur, profondeur)
    tool.Model.get_model_props().extrusion_depth = hauteur
    bpy.context.scene.cursor.location = (x, y, z)
    selectionner_seul(None)  # sinon Bonsai rattache le poteau à l'objet sélectionné
    avant = set(tool.Ifc.get().by_type("IfcColumn"))
    bpy.ops.bim.add_occurrence(relating_type_id=type_.id())
    (nouveau,) = set(tool.Ifc.get().by_type("IfcColumn")) - avant
    return tool.Ifc.get_object(nouveau)


def objet_ifc(nom: str, classe: str, emplacement, avec_maillage: bool = True):
    """Objet Blender neuf déclaré dans l'IFC, rangé dans l'étage courant."""
    obj = bpy.data.objects.new(nom, bpy.data.meshes.new(nom) if avec_maillage else None)
    obj.matrix_world = emplacement
    bpy.context.scene.collection.objects.link(obj)
    trame.core.root.assign_class(
        tool.Ifc, tool.Collector, tool.Root, obj=obj, ifc_class=classe, should_add_representation=False
    )
    selectionner_seul(obj)
    return obj


FORMES_TOIT = (
    ("DEUX_PANS", "Deux pans", "Pignons sur les deux petits côtés (contour à 4 points)"),
    ("QUATRE_PANS", "Quatre pans", "Une pente sur chaque côté"),
    ("UN_PAN", "Un pan", "La pente part du premier côté dessiné"),
    ("PLAT", "Toit-terrasse", "Toit plat"),
)


def angles_pignons(points: list, forme: str) -> list:
    """Angle de chaque côté pour Bonsai : pi/2 = pignon vertical, 0 = pente normale."""
    n = len(points)
    cotes = [(Vector(points[(i + 1) % n]) - Vector(points[i])).length for i in range(n)]
    if forme == "UN_PAN":
        return [0.0] + [math.pi / 2] * (n - 1)
    if forme == "DEUX_PANS" and n == 4:
        petits = sorted(range(4), key=lambda i: cotes[i])[:2]
        return [math.pi / 2 if i in petits else 0.0 for i in range(4)]
    return [0.0] * n


def creer_toit(points: list, z: float, forme: str, pente_deg: float, epaisseur: float, depart: float):
    """Toit sur le contour dessiné, posé à « depart » mètres au-dessus de l'étage."""
    if points[0] == points[-1]:
        points = points[:-1]
    if forme == "PLAT":
        return creer_dalle(points, z + depart, epaisseur, type_de_dalle(epaisseur, "Toit-terrasse", "ROOF"))
    origine = Matrix.Translation((points[0][0], points[0][1], z + depart))
    obj = objet_ifc("Toit", "IfcRoof", origine)
    bpy.ops.bim.add_roof()
    obj = bpy.context.active_object
    props = tool.Model.get_roof_props(obj)
    props["generation_method"] = 1  # ANGLE : la pente est donnée par l'angle
    props["angle"] = math.radians(pente_deg)
    props["roof_thickness"] = epaisseur
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
    donnees = props.get_general_kwargs(convert_to_project_units=True)
    donnees["path_data"] = {
        "edges": [[i, (i + 1) % len(points)] for i in range(len(points))],
        "verts": [[(p[0] - points[0][0]) / unit_scale, (p[1] - points[0][1]) / unit_scale, 0.0] for p in points],
        "gable_roof_angles": angles_pignons(points, forme),
    }
    bonsai_toit.update_bbim_roof_pset(tool.Ifc.get_entity(obj), donnees)
    bonsai_toit.refresh()
    bonsai_toit.update_roof_modifier_bmesh(obj)
    bonsai_toit.update_roof_modifier_ifc_data(bpy.context)
    return obj


def creer_escalier(depart, arrivee, z: float, largeur: float, hauteur: float, marches: int):
    """Volée droite qui monte de « depart » vers « arrivee », centrée sur la ligne cliquée."""
    d = Vector((arrivee[0] - depart[0], arrivee[1] - depart[1], 0))
    angle = math.atan2(d.y, d.x)
    cote = Vector((-math.sin(angle), math.cos(angle), 0))
    origine = Vector((depart[0], depart[1], z)) - cote * largeur / 2
    defauts = tool.Blender.get_addon_preferences().default_parameters.stair
    defauts["width"], defauts["height"], defauts["number_of_treads"] = largeur, hauteur, marches
    defauts["tread_run"] = d.length / marches
    # Un maillage et non un vide : Bonsai perd sinon les réglages en recréant l'objet.
    objet_ifc("Escalier", "IfcStairFlight", Matrix.Translation(origine) @ Matrix.Rotation(angle, 4, "Z"))
    bpy.ops.bim.add_stair()
    return bpy.context.active_object


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
    # Murs existants dont une extrémité coïncide avec le début ou la fin du tracé : on les raccordera.
    voisins = {}
    for mur in tool.Ifc.get().by_type("IfcWall"):
        for extremite in axe_mur(mur, z) or ():
            for i in (0, len(points) - 1):
                if (Vector((points[i][0], points[i][1], z)) - extremite).length < 1e-3:
                    voisins[i] = tool.Ifc.get_object(mur)
    murs = []
    for a, b in zip(points, points[1:]):
        d = Vector(b) - Vector(a)
        murs.append(creer_mur(a[0], a[1], z, d.length, math.degrees(math.atan2(d.y, d.x)), epaisseur, hauteur))
    ferme = len(points) > 3 and (Vector(points[0]) - Vector(points[-1])).length < 1e-6
    paires = zip(murs, murs[1:] + murs[:1]) if ferme else zip(murs, murs[1:])
    for m1, m2 in paires:
        DumbWallJoiner().connect(m2, m1)
    if not ferme:
        if 0 in voisins:
            DumbWallJoiner().connect(murs[0], voisins[0])
        if len(points) - 1 in voisins:
            DumbWallJoiner().connect(murs[-1], voisins[len(points) - 1])
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


class TRAME_OT_reglages_dalle(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_dalle"
    bl_label = "Dalle"
    bl_description = "Régler et créer la dalle dessinée"
    bl_options = {"REGISTER", "UNDO"}

    points: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    epaisseur: bpy.props.FloatProperty(name="Épaisseur", unit="LENGTH", default=0.20, min=0.01, max=2)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Dalle", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        col.prop(self, "epaisseur")

    def _execute(self, context):
        pts = [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]
        creer_dalle(pts, self.z, self.epaisseur)
        return {"FINISHED"}


class _ReglagesOuverture:
    bl_options = {"REGISTER", "UNDO"}
    classe = ""
    avec_allege = False

    mur: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    position: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title=self.bl_label, confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        for prop in ("modele", "largeur", "hauteur") + (("allege",) if self.avec_allege else ()) + ("retourner",):
            col.prop(self, prop)

    def _execute(self, context):
        allege = self.allege if self.avec_allege else 0.0
        creer_ouverture(
            self.classe, tool.Ifc.get().by_id(self.mur), self.position, self.z,
            self.largeur, self.hauteur, allege, self.modele, self.retourner,
        )
        return {"FINISHED"}


class TRAME_OT_reglages_porte(_ReglagesOuverture, bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_porte"
    bl_label = "Porte"
    bl_description = "Régler et poser la porte"
    classe = "IfcDoorType"
    modele: bpy.props.EnumProperty(name="Ouverture", items=OUVERTURES_PORTE)
    retourner: bpy.props.BoolProperty(name="Ouvrir de l'autre côté", default=False)
    largeur: bpy.props.FloatProperty(name="Largeur", unit="LENGTH", default=0.90, min=0.3, max=5)
    hauteur: bpy.props.FloatProperty(name="Hauteur", unit="LENGTH", default=2.10, min=0.5, max=5)


class TRAME_OT_reglages_fenetre(_ReglagesOuverture, bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_fenetre"
    bl_label = "Fenêtre"
    bl_description = "Régler et poser la fenêtre"
    classe = "IfcWindowType"
    avec_allege = True
    modele: bpy.props.EnumProperty(name="Vantaux", items=VANTAUX_FENETRE)
    retourner: bpy.props.BoolProperty(name="Ouvrir de l'autre côté", default=False)
    largeur: bpy.props.FloatProperty(name="Largeur", unit="LENGTH", default=1.20, min=0.2, max=10)
    hauteur: bpy.props.FloatProperty(name="Hauteur", unit="LENGTH", default=1.35, min=0.2, max=5)
    allege: bpy.props.FloatProperty(name="Allège", unit="LENGTH", default=0.90, min=0, max=5)


class TRAME_OT_poser_ouverture(bpy.types.Operator):
    bl_idname = "bim.trame_poser_ouverture"
    bl_label = "Poser une porte ou une fenêtre"
    bl_description = "Cliquez sur un mur à l'endroit où centrer la porte ou la fenêtre"
    bl_options = {"REGISTER"}

    element: bpy.props.EnumProperty(items=(("PORTE", "Porte", ""), ("FENETRE", "Fenêtre", "")))

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None and context.area and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        z = niveau_etage()
        point = point_sous_souris(context, event, z)
        trouve = point and mur_sous_point(point, z)
        if not trouve:
            self.report({"WARNING"}, "Cliquez sur un mur pour y poser l'ouverture")
            return {"CANCELLED"}
        mur, position = trouve
        dialogue = bpy.ops.bim.trame_reglages_porte if self.element == "PORTE" else bpy.ops.bim.trame_reglages_fenetre
        dialogue("INVOKE_DEFAULT", mur=mur.id(), position=position, z=z)
        return {"FINISHED"}


class TRAME_OT_reglages_poteau(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_poteau"
    bl_label = "Poteau"
    bl_description = "Régler et poser le poteau"
    bl_options = {"REGISTER", "UNDO"}

    x: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    y: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    largeur: bpy.props.FloatProperty(name="Largeur", unit="LENGTH", default=0.30, min=0.05, max=3)
    profondeur: bpy.props.FloatProperty(name="Profondeur", unit="LENGTH", default=0.30, min=0.05, max=3)
    hauteur: bpy.props.FloatProperty(name="Hauteur", unit="LENGTH", default=2.50, min=0.1, max=50)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Poteau", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        for prop in ("largeur", "profondeur", "hauteur"):
            col.prop(self, prop)

    def _execute(self, context):
        creer_poteau(self.x, self.y, self.z, self.largeur, self.profondeur, self.hauteur)
        return {"FINISHED"}


class TRAME_OT_poser_poteau(bpy.types.Operator):
    bl_idname = "bim.trame_poser_poteau"
    bl_label = "Poser un poteau"
    bl_description = "Cliquez à l'endroit du centre du poteau"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None and context.area and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        z = niveau_etage()
        point = point_sous_souris(context, event, z)
        if point is None:
            return {"CANCELLED"}
        bpy.ops.bim.trame_reglages_poteau("INVOKE_DEFAULT", x=point.x, y=point.y, z=z)
        return {"FINISHED"}


class TRAME_OT_reglages_toit(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_toit"
    bl_label = "Toit"
    bl_description = "Régler et créer le toit dessiné"
    bl_options = {"REGISTER", "UNDO"}

    points: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    forme: bpy.props.EnumProperty(name="Forme", items=FORMES_TOIT, default="DEUX_PANS")
    pente: bpy.props.FloatProperty(name="Pente (°)", default=35, min=1, max=75)
    epaisseur: bpy.props.FloatProperty(name="Épaisseur", unit="LENGTH", default=0.25, min=0.02, max=2)
    depart: bpy.props.FloatProperty(
        name="Hauteur de départ", unit="LENGTH", default=2.50, min=0, max=50,
        description="Hauteur du bas du toit au-dessus de l'étage (en général, la hauteur des murs)",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Toit", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        col.prop(self, "forme")
        if self.forme != "PLAT":
            col.prop(self, "pente")
        col.prop(self, "epaisseur")
        col.prop(self, "depart")

    def _execute(self, context):
        pts = [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]
        creer_toit(pts, self.z, self.forme, self.pente, self.epaisseur, self.depart)
        return {"FINISHED"}


class TRAME_OT_reglages_escalier(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_escalier"
    bl_label = "Escalier"
    bl_description = "Régler et créer l'escalier dessiné"
    bl_options = {"REGISTER", "UNDO"}

    points: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    z: bpy.props.FloatProperty(options={"HIDDEN", "SKIP_SAVE"})
    largeur: bpy.props.FloatProperty(name="Largeur", unit="LENGTH", default=1.0, min=0.5, max=5)
    hauteur: bpy.props.FloatProperty(name="Hauteur à monter", unit="LENGTH", default=2.70, min=0.2, max=10)
    marches: bpy.props.IntProperty(name="Nombre de marches", default=16, min=2, max=60)

    def invoke(self, context, event):
        self.marches = max(2, round(self.hauteur / 0.17))  # hauteur de marche confortable, ~17 cm
        return context.window_manager.invoke_props_dialog(self, title="Escalier", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        for prop in ("largeur", "hauteur", "marches"):
            col.prop(self, prop)
        pts = [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]
        longueur = (Vector(pts[1]) - Vector(pts[0])).length
        col.label(text=f"Marche : {self.hauteur / self.marches * 100:.1f} cm de haut, {longueur / self.marches * 100:.1f} cm de giron")

    def _execute(self, context):
        pts = [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]
        creer_escalier(pts[0], pts[1], self.z, self.largeur, self.hauteur, self.marches)
        return {"FINISHED"}


class TRAME_OT_dessiner(bpy.types.Operator):
    bl_idname = "bim.trame_dessiner"
    bl_label = "Dessiner des murs ou une dalle"
    bl_description = (
        "Cliquez les points des murs à la suite. Double-clic, Entrée ou clic droit : terminer. "
        "Clic sur le premier point : fermer. Maj : angle par 45°. Retour arrière : annuler le dernier point. Échap : tout annuler"
    )
    bl_options = {"REGISTER"}

    AIDE = "Cliquez le point suivant   •   Double-clic / Entrée : terminer   •   Premier point : fermer   •   Maj : 45°   •   ⌫ : dernier point   •   Échap : annuler"
    RAYON_FERMETURE_PX = 12

    element: bpy.props.EnumProperty(
        items=(("MUR", "Mur", ""), ("DALLE", "Dalle", ""), ("TOIT", "Toit", ""), ("ESCALIER", "Escalier", ""))
    )

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
            if self.element == "ESCALIER":
                return self.valider(context)  # départ + direction : c'est tout
            if (self.fin - self.points[0]).length < 1e-6:
                return self.valider(context)  # contour fermé
        return {"RUNNING_MODAL"}

    def valider(self, context):
        self.terminer(context)
        pts = self.points[:]
        texte = ";".join(f"{p.x:.6f},{p.y:.6f}" for p in pts)
        if self.element in {"DALLE", "TOIT"}:
            if len(pts) < 3:
                self.report({"WARNING"}, "Il faut au moins 3 points pour un contour")
                return {"CANCELLED"}
            dialogue = bpy.ops.bim.trame_reglages_dalle if self.element == "DALLE" else bpy.ops.bim.trame_reglages_toit
            dialogue("INVOKE_DEFAULT", points=texte, z=self.z)
            return {"FINISHED"}
        if self.element == "ESCALIER":
            if len(pts) < 2:
                return {"CANCELLED"}
            bpy.ops.bim.trame_reglages_escalier("INVOKE_DEFAULT", points=texte, z=self.z)
            return {"FINISHED"}
        if len(pts) < 2:
            return {"CANCELLED"}
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
