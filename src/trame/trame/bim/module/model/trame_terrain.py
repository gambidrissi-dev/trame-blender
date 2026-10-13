# Trame - terrain : maillage triangulé à partir de points cotés (relevé de géomètre) ou d'un contour,
# enregistré comme IfcGeographicElement « TERRAIN » du site ; courbes de niveau dans le plan.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import math

import bpy
import ifcopenshell.api.spatial
import ifcopenshell.util.representation
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

import trame.core.root
import trame.tool as tool


def lire_points(texte: str) -> list:
    """Points « x y z » d'un relevé : séparateurs ; tabulation espace ou virgule, virgule décimale acceptée.

    Les lignes illisibles (en-têtes, commentaires) sont ignorées."""
    points = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ";" in ligne or "\t" in ligne:
            morceaux = [m.replace(",", ".") for m in ligne.replace("\t", ";").split(";")]
        elif ligne.count(",") >= 2 and " " not in ligne:
            morceaux = ligne.split(",")
        else:
            morceaux = [m.replace(",", ".") for m in ligne.split()]
        valeurs = []
        for m in morceaux:
            try:
                valeurs.append(float(m))
            except ValueError:
                pass
        if len(valeurs) >= 3:
            points.append(tuple(valeurs[-3:]))  # un éventuel numéro de point en tête est ignoré
    return points


def trianguler(points: list) -> tuple:
    """Triangulation de Delaunay en plan des points cotés : (sommets 3D, triangles)."""
    plan = [Vector((p[0], p[1])) for p in points]
    sommets, _, faces, origines, _, _ = delaunay_2d_cdt(plan, [], [], 0, 1e-6)
    hauteurs = [points[o[0]][2] if o else 0.0 for o in origines]
    return [(v.x, v.y, z) for v, z in zip(sommets, hauteurs)], [tuple(f) for f in faces]


def creer_terrain(points: list, nom: str = "Terrain"):
    """Terrain triangulé, rangé dans le site du projet."""
    f = tool.Ifc.get()
    sommets, faces = trianguler(points)
    maillage = bpy.data.meshes.new(nom)
    maillage.from_pydata(sommets, [], faces)
    obj = bpy.data.objects.new(nom, maillage)
    bpy.context.scene.collection.objects.link(obj)
    contexte = ifcopenshell.util.representation.get_context(f, "Model", "Body", "MODEL_VIEW")
    terrain = trame.core.root.assign_class(
        tool.Ifc, tool.Collector, tool.Root, obj=obj, ifc_class="IfcGeographicElement",
        predefined_type="TERRAIN", should_add_representation=True, context=contexte,
    )
    if sites := f.by_type("IfcSite"):
        ifcopenshell.api.spatial.assign_container(f, products=[terrain], relating_structure=sites[0])
    if len(obj.users_collection) > 1:
        bpy.context.scene.collection.objects.unlink(obj)
    return obj


def courbes_de_niveau(obj, pas: float = 0.5) -> list:
    """Courbes de niveau du terrain tous les « pas » mètres : liste de segments (a, b) en coordonnées monde."""
    monde = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not monde:
        return []
    zmin, zmax = min(p.z for p in monde), max(p.z for p in monde)
    segments = []
    niveau = math.ceil(zmin / pas) * pas
    while niveau <= zmax + 1e-9:
        for poly in obj.data.polygons:
            pts = [monde[i] for i in poly.vertices]
            coupes = []
            for a, b in zip(pts, pts[1:] + pts[:1]):
                if (a.z - niveau) * (b.z - niveau) < 0:
                    t = (niveau - a.z) / (b.z - a.z)
                    coupes.append(a + (b - a) * t)
            if len(coupes) == 2:
                segments.append((coupes[0], coupes[1]))
        niveau += pas
    return segments


class TRAME_OT_reglages_terrain(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_reglages_terrain"
    bl_label = "Terrain"
    bl_description = "Créer une plateforme de terrain sur le contour tracé"
    bl_options = {"REGISTER", "UNDO"}

    points: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    altitude: bpy.props.FloatProperty(name="Altitude", unit="LENGTH", default=0.0, soft_min=-50, soft_max=50,
                                      description="Altitude du terrain par rapport au zéro du projet")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Terrain", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        col.prop(self, "altitude")

    def _execute(self, context):
        pts = [tuple(map(float, p.split(","))) for p in self.points.split(";") if p]
        creer_terrain([(x, y, self.altitude) for x, y in pts])
        from trame.bim.module.model.trame_outils import apres_creation

        apres_creation()
        return {"FINISHED"}


class TRAME_OT_importer_releve(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.trame_importer_releve"
    bl_label = "Importer un relevé"
    bl_description = "Terrain à partir d'un fichier de points cotés (x y z), par exemple un relevé de géomètre"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.csv;*.txt;*.xyz", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None

    def execute(self, context):
        with open(self.filepath, encoding="utf-8", errors="replace") as fichier:
            points = lire_points(fichier.read())
        if len(points) < 3:
            self.report({"ERROR"}, "Il faut au moins 3 points « x y z » dans le fichier")
            return {"CANCELLED"}
        creer_terrain(points, nom=bpy.path.display_name_from_filepath(self.filepath))
        from trame.bim.module.model.trame_outils import apres_creation

        apres_creation()
        self.report({"INFO"}, f"Terrain créé à partir de {len(points)} points")
        return {"FINISHED"}
