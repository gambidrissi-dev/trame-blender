# Trame - dessin du plan : cotes et murs coupés hachurés selon leur matériau, comme dans Archicad.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import json
import math

import blf
import bmesh
import bpy
import gpu
import ifcopenshell.api.pset
import ifcopenshell.geom
import ifcopenshell.api.spatial
import ifcopenshell.util.element
import ifcopenshell.util.representation
import ifcopenshell.util.unit
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.geometry import convex_hull_2d, tessellate_polygon

import trame.core.root
import trame.tool as tool

HAUTEUR_COUPE_PLAN = 1.0  # le plan coupe à 1 m au-dessus de l'étage
_vues_plan = set()  # zones 3D affichées en plan (pointeurs Blender)


def est_vue_plan(area) -> bool:
    return area is not None and area.as_pointer() in _vues_plan
CLASSES_COUPEES = ("IfcWall", "IfcColumn")


# ---------------------------------------------------------------- Cotes


def geometrie_cote(points: list, decalage: float) -> tuple:
    """Cote alignée sur le premier et le dernier point : (points de la ligne de cote, normale).

    Les points mesurés sont projetés sur la ligne, triés, puis décalés de « decalage » le long de la normale."""
    p0 = Vector((points[0][0], points[0][1]))
    u = Vector((points[-1][0], points[-1][1])) - p0
    u = u.normalized() if u.length > 1e-9 else Vector((1, 0))
    n = Vector((-u.y, u.x))
    abscisses = sorted({round((Vector((p[0], p[1])) - p0).dot(u), 6) for p in points})
    return [p0 + u * t + n * decalage for t in abscisses], n


def decalage_vers(points: list, souris) -> float:
    """Décalage signé de la ligne de cote pour qu'elle passe par la souris."""
    _, n = geometrie_cote(points, 0)
    return (Vector((souris[0], souris[1])) - Vector((points[0][0], points[0][1]))).dot(n)


def attaches(points: list, decalage: float) -> list:
    """Paires (point mesuré, point correspondant sur la ligne de cote), pour les lignes d'attache."""
    if len(points) < 2:
        return []
    _, n = geometrie_cote(points, decalage)
    p0 = Vector((points[0][0], points[0][1]))
    u = Vector((n.y, -n.x))  # direction de la cote (la normale tournée de -90°)
    paires = []
    for p in points:
        v = Vector((p[0], p[1]))
        t = (v - p0).dot(u)
        paires.append((tuple(v), tuple(p0 + u * t + n * decalage)))
    return paires


def creer_cote(points: list, decalage: float, z: float):
    """Cote enregistrée comme annotation IFC « DIMENSION » de l'étage actif."""
    f = tool.Ifc.get()
    ligne, _ = geometrie_cote(points, decalage)
    maillage = bpy.data.meshes.new("Cote")
    maillage.from_pydata([(p.x, p.y, z) for p in ligne], [(i, i + 1) for i in range(len(ligne) - 1)], [])
    obj = bpy.data.objects.new("Cote", maillage)
    bpy.context.scene.collection.objects.link(obj)
    contexte = ifcopenshell.util.representation.get_context(f, "Plan", "Annotation", "PLAN_VIEW")
    cote = trame.core.root.assign_class(
        tool.Ifc, tool.Collector, tool.Root, obj=obj, ifc_class="IfcAnnotation",
        should_add_representation=True, context=contexte,
    )
    cote.ObjectType = "DIMENSION"
    if etage := tool.Root.get_default_container():
        ifcopenshell.api.spatial.assign_container(f, products=[cote], relating_structure=etage)
    pset = ifcopenshell.api.pset.add_pset(f, product=cote, name="Trame_Cote")
    ifcopenshell.api.pset.edit_pset(
        f, pset=pset, properties={"Decalage": decalage, "Points": json.dumps([list(p[:2]) for p in points])}
    )
    return obj


def texte_longueur(longueur: float) -> str:
    return f"{longueur:.2f}".replace(".", ",")


# ---------------------------------------------------------------- Murs coupés


def section(obj, z: float) -> list:
    """Contours (listes de points 3D) de la section de l'objet par le plan horizontal z."""
    if obj.type != "MESH" or not obj.data.polygons:
        return []
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    zs = [v.co.z for v in bm.verts]
    if not zs or not (min(zs) < z < max(zs)):
        bm.free()
        return []
    coupe = bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, z), plane_no=(0, 0, 1)
    )["geom_cut"]
    aretes = [e for e in coupe if isinstance(e, bmesh.types.BMEdge)]
    voisins = {}
    for e in aretes:
        a, b = (v.index for v in e.verts)
        voisins.setdefault(a, []).append(b)
        voisins.setdefault(b, []).append(a)
    coords = {v.index: v.co.copy() for v in bm.verts}
    bm.free()
    contours, vus = [], set()
    for depart in voisins:
        if depart in vus:
            continue
        boucle, courant, precedent = [depart], depart, None
        vus.add(depart)
        while True:
            suivants = [v for v in voisins[courant] if v != precedent and v not in vus]
            if not suivants:
                break
            precedent, courant = courant, suivants[0]
            vus.add(courant)
            boucle.append(courant)
        if len(boucle) >= 3:
            contours.append([coords[i] for i in boucle])
    return contours


def hachures(contour: list, angle_deg: float, pas: float) -> list:
    """Segments de hachure (paires de points) parallèles à « angle_deg », espacés de « pas », dans le contour."""
    a = math.radians(angle_deg)
    u, n = Vector((math.cos(a), math.sin(a))), Vector((-math.sin(a), math.cos(a)))
    pts = [Vector((p.x, p.y)) for p in contour]
    z = contour[0].z
    hauteurs = [p.dot(n) for p in pts]
    segments = []
    c = math.floor(min(hauteurs) / pas) * pas + pas / 2
    while c < max(hauteurs):
        coupes = []
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            hp, hq = p.dot(n), q.dot(n)
            if (hp - c) * (hq - c) < 0:
                t = (c - hp) / (hq - hp)
                coupes.append((p + (q - p) * t).dot(u))
        coupes.sort()
        for t0, t1 in zip(coupes[0::2], coupes[1::2]):
            a3, b3 = u * t0 + n * c, u * t1 + n * c
            segments.append((Vector((a3.x, a3.y, z)), Vector((b3.x, b3.y, z))))
        c += pas
    return segments


# Motifs : (couleur de fond RGBA, [(angle, pas en m)], couleur des traits)
MOTIFS = {
    "beton": ((0.80, 0.80, 0.80, 1), [(45, 0.08)], (0.25, 0.25, 0.25, 1)),
    "maconnerie": ((1, 1, 1, 1), [(45, 0.12)], (0.1, 0.1, 0.1, 1)),
    "bois": ((0.96, 0.90, 0.80, 1), [(45, 0.15), (135, 0.15)], (0.45, 0.30, 0.15, 1)),
    "isolant": ((1, 0.97, 0.85, 1), [(135, 0.05)], (0.6, 0.5, 0.2, 1)),
    "platre": ((0.88, 0.88, 0.88, 1), [], (0, 0, 0, 1)),
    "plein": ((0.12, 0.12, 0.12, 1), [], (0, 0, 0, 1)),
}


def motif(element) -> str:
    """Motif de hachure selon le matériau principal de l'élément."""
    materiau = ifcopenshell.util.element.get_material(element, should_skip_usage=True)
    if materiau and materiau.is_a("IfcMaterialLayerSet") and materiau.MaterialLayers:
        materiau = max(materiau.MaterialLayers, key=lambda c: c.LayerThickness or 0).Material
    elif materiau and materiau.is_a("IfcMaterialProfileSet") and materiau.MaterialProfiles:
        materiau = materiau.MaterialProfiles[0].Material
    if not materiau or not materiau.is_a("IfcMaterial"):
        return "plein"
    familles = (
        ("beton", ("béton", "beton", "concrete")),
        ("maconnerie", ("maçon", "macon", "brique", "brick", "parpaing", "block", "masonry", "stone", "pierre")),
        ("bois", ("bois", "wood", "timber")),
        ("isolant", ("isol", "insulation", "laine")),
        ("platre", ("plâtre", "platre", "gypsum", "placo")),
    )
    # Le nom choisi par l'archi prime sur la catégorie technique.
    for texte in ((materiau.Name or "").lower(), (getattr(materiau, "Category", "") or "").lower()):
        for cle, mots in familles:
            if any(m in texte for m in mots):
                return cle
    return "plein"


_cache = {}


def sections_etage(z_coupe: float, etage=None) -> list:
    """(contours, motif) de chaque mur/poteau de l'étage (actif par défaut), coupé à z_coupe ; mis en cache."""
    etage = etage or tool.Root.get_default_container()
    if not etage:
        return []
    resultat = []
    for element in ifcopenshell.util.element.get_decomposition(etage):
        if not any(element.is_a(c) for c in CLASSES_COUPEES):
            continue
        obj = tool.Ifc.get_object(element)
        if not obj or obj.type != "MESH" or obj.hide_get():
            continue
        cle = (obj.name, obj.data.as_pointer(), len(obj.data.vertices), tuple(round(v, 5) for r in obj.matrix_world for v in r), round(z_coupe, 4))
        if cle not in _cache:
            _cache[cle] = (section(obj, z_coupe), motif(element))
        resultat.append(_cache[cle])
    return resultat


_cache_symboles = {}


def symbole_plan(element) -> list:
    """Traits du symbole en plan (Plan/Body) d'une porte ou fenêtre Bonsai, en coordonnées monde : [(a, b), …]."""
    obj = tool.Ifc.get_object(element)
    rep = ifcopenshell.util.representation.get_representation(element, "Plan", "Body", "PLAN_VIEW")
    if not obj or not rep:
        return []
    cle = (rep.id(), tuple(round(v, 5) for r in obj.matrix_world for v in r))
    if cle not in _cache_symboles:
        reglages = ifcopenshell.geom.settings()
        reglages.set("dimensionality", ifcopenshell.ifcopenshell_wrapper.CURVES_SURFACES_AND_SOLIDS)
        forme = ifcopenshell.geom.create_shape(reglages, rep)  # en mètres, repère de l'élément
        v, e = forme.verts, forme.edges
        points = [obj.matrix_world @ Vector(v[i : i + 3]) for i in range(0, len(v), 3)]
        _cache_symboles[cle] = [(points[e[i]], points[e[i + 1]]) for i in range(0, len(e), 2)]
    return _cache_symboles[cle]


def emprise(obj, z: float, marge_y: float = 0.0) -> list:
    """Rectangle en plan de l'objet (boîte englobante locale, élargie de « marge_y » de part et d'autre), à la hauteur z."""
    xs = [c[0] for c in obj.bound_box]
    ys = [c[1] for c in obj.bound_box] + [min(c[1] for c in obj.bound_box) - marge_y, max(c[1] for c in obj.bound_box) + marge_y]
    coins = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    monde = [obj.matrix_world @ Vector((x, y, 0)) for x, y in coins]
    return [Vector((p.x, p.y, z)) for p in monde]


def dans_un_toit(element) -> bool:
    return any(r.RelatingOpeningElement.VoidsElements and r.RelatingOpeningElement.VoidsElements[0]
               .RelatingBuildingElement.is_a("IfcRoof") for r in getattr(element, "FillsVoids", []) or [])


def ouvertures_etage() -> list:
    """Portes et fenêtres de l'étage posées dans des murs (les Velux sont dessinés avec le toit)."""
    etage = tool.Root.get_default_container()
    if not etage:
        return []
    return [e for e in ifcopenshell.util.element.get_decomposition(etage)
            if (e.is_a("IfcDoor") or e.is_a("IfcWindow")) and not dans_un_toit(e)]


def etage_inferieur():
    """Étage juste sous l'étage actif (None s'il est le plus bas)."""
    actif = tool.Root.get_default_container()
    if not actif or not (obj_actif := tool.Ifc.get_object(actif)):
        return None
    dessous = [
        (o.location.z, e) for e in tool.Ifc.get().by_type("IfcBuildingStorey")
        if (o := tool.Ifc.get_object(e)) and o.location.z < obj_actif.location.z - 1e-3
    ]
    return max(dessous, key=lambda x: x[0])[1] if dessous else None


def contours_toits() -> list:
    """Contours en plan des toits de l'étage actif (pour les dessiner en pointillés)."""
    etage = tool.Root.get_default_container()
    if not etage:
        return []
    contours = []
    for element in ifcopenshell.util.element.get_decomposition(etage):
        type_ = ifcopenshell.util.element.get_type(element)
        est_toit = element.is_a("IfcRoof") or (element.is_a("IfcSlab") and "ROOF" in (
            element.PredefinedType, getattr(type_, "PredefinedType", None)))
        obj = tool.Ifc.get_object(element) if est_toit else None
        if not obj or obj.type != "MESH" or obj.hide_get() or not obj.data.vertices:
            continue
        donnees = ifcopenshell.util.element.get_pset(element, "BBIM_Roof") or {}
        if "Data" in donnees:  # toit paramétrique : son contour exact
            unit_scale = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
            sommets = json.loads(donnees["Data"])["path_data"]["verts"]
            contours.append([obj.matrix_world @ (Vector(v) * unit_scale) for v in sommets])
        else:  # toit-terrasse : enveloppe de ses sommets
            pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
            enveloppe = convex_hull_2d([p.to_2d() for p in pts])
            contours.append([pts[i] for i in enveloppe])
    # Velux : leur emprise en plan, en pointillés comme le toit qui les porte.
    for element in ifcopenshell.util.element.get_decomposition(etage):
        if element.is_a("IfcWindow") and dans_un_toit(element) and (obj := tool.Ifc.get_object(element)):
            pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            enveloppe = convex_hull_2d([p.to_2d() for p in pts])
            contours.append([pts[i] for i in enveloppe])
    return contours


_cache_courbes = {}


def courbes_terrain() -> list:
    """Courbes de niveau de tous les terrains du projet (mises en cache par maillage)."""
    from trame.bim.module.model.trame_terrain import courbes_de_niveau

    segments = []
    for element in tool.Ifc.get().by_type("IfcGeographicElement"):
        obj = tool.Ifc.get_object(element)
        if not obj or obj.type != "MESH" or obj.hide_get():
            continue
        cle = (obj.data.as_pointer(), len(obj.data.vertices), tuple(round(v, 5) for r in obj.matrix_world for v in r))
        if cle not in _cache_courbes:
            _cache_courbes[cle] = courbes_de_niveau(obj, 0.5)
        segments += _cache_courbes[cle]
    return segments


_cache_emprise = {}


def hors_batiment(segments: list) -> list:
    """Retire des segments la partie qui passe sous le bâtiment (contour extérieur des murs de l'étage)."""
    from shapely.geometry import LineString, Polygon
    from trame.bim.module.model.trame_outils import contour_des_murs

    etage = tool.Root.get_default_container()
    if not segments or not etage:
        return segments
    murs = tuple(sorted(
        (o.name, round(o.matrix_world.translation.x, 3), round(o.matrix_world.translation.y, 3), len(o.data.vertices))
        for e in ifcopenshell.util.element.get_decomposition(etage)
        if e.is_a("IfcWall") and (o := tool.Ifc.get_object(e)) and o.type == "MESH"
    ))
    if (etage.id(), murs) not in _cache_emprise:
        _cache_emprise.clear()
        contour = contour_des_murs(tool.Ifc.get_object(etage).location.z, etage) if murs else []
        _cache_emprise[(etage.id(), murs)] = Polygon(contour) if len(contour) >= 3 else None
    emprise = _cache_emprise[(etage.id(), murs)]
    if emprise is None:
        return segments
    resultat = []
    for a, b in segments:
        reste = LineString([(a.x, a.y), (b.x, b.y)]).difference(emprise)
        for morceau in getattr(reste, "geoms", [reste]):
            if not morceau.is_empty and morceau.geom_type == "LineString":
                (x0, y0), (x1, y1) = morceau.coords[0], morceau.coords[-1]
                resultat.append((Vector((x0, y0, a.z)), Vector((x1, y1, a.z))))
    return resultat


def pointilles(contour: list, z: float, tiret: float = 0.25, vide: float = 0.15) -> list:
    """Segments en tirets le long d'un contour fermé (longueurs en mètres)."""
    segments = []
    for a, b in zip(contour, contour[1:] + contour[:1]):
        a, b = Vector((a.x, a.y, z)), Vector((b.x, b.y, z))
        longueur, t = (b - a).length, 0.0
        while t < longueur:
            fin = min(t + tiret, longueur)
            segments.append((a + (b - a) * (t / longueur), a + (b - a) * (fin / longueur)))
            t = fin + vide
    return segments


# ---------------------------------------------------------------- Dessin dans la vue


def _shader():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def dessiner_hachures():
    if not tool.Ifc.get() or not est_vue_plan(bpy.context.area):
        return  # seulement dans la vue en plan
    z = tool.Root.get_default_container_elevation() + HAUTEUR_COUPE_PLAN - 0.001
    shader = _shader()
    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("ALPHA")
    scene = bpy.context.scene
    # Étage inférieur en calque de fond : ses murs coupés, en gris clair, sous le dessin de l'étage.
    if getattr(scene, "trame_calque_fond", True) and (dessous := etage_inferieur()):
        z_dessous = tool.Ifc.get_object(dessous).location.z + HAUTEUR_COUPE_PLAN
        trace = [Vector((p.x, p.y, z)) for contours, _ in sections_etage(z_dessous, dessous)
                for c in contours for a, b in zip(c, c[1:] + c[:1]) for p in (a, b)]
        if trace:
            gpu.state.line_width_set(1)
            shader.uniform_float("color", (0.72, 0.72, 0.72, 1))
            batch_for_shader(shader, "LINES", {"pos": trace}).draw(shader)
    # Terrain : courbes de niveau tous les 50 cm, sur le plan de l'étage le plus bas.
    if etage_inferieur() is None:
        courbes = [Vector((p.x, p.y, z)) for seg in hors_batiment(courbes_terrain()) for p in seg]
        if courbes:
            gpu.state.line_width_set(1)
            shader.uniform_float("color", (0.55, 0.40, 0.25, 1))
            batch_for_shader(shader, "LINES", {"pos": courbes}).draw(shader)
    # Toits de l'étage : contour en pointillés (ils sont au-dessus du plan de coupe).
    tirets = [p for c in contours_toits() for s in pointilles(c, z) for p in s]
    if tirets:
        gpu.state.line_width_set(1.5)
        shader.uniform_float("color", (0.15, 0.15, 0.15, 1))
        batch_for_shader(shader, "LINES", {"pos": tirets}).draw(shader)
    # Portes et fenêtres : l'ouverture est masquée en blanc sur toute l'épaisseur du mur (on ne voit plus
    # l'allège ni le seuil sous le plan de coupe), les murs sont dessinés par-dessus, puis le symbole.
    symboles = []
    for element in ouvertures_etage():
        obj = tool.Ifc.get_object(element)
        if not obj or obj.hide_get() or obj.type != "MESH":
            continue
        if pts := emprise(obj, z, marge_y=0.6):
            shader.uniform_float("color", (1, 1, 1, 1))
            batch_for_shader(shader, "TRIS", {"pos": pts}, indices=((0, 1, 2), (0, 2, 3))).draw(shader)
        symboles += [Vector((p.x, p.y, z)) for segment in symbole_plan(element) for p in segment]
    for contours, nom_motif in sections_etage(z + 0.001):
        fond, traits, couleur = MOTIFS[nom_motif]
        for contour in contours:
            pts = [Vector((p.x, p.y, z)) for p in contour]
            triangles = tessellate_polygon([pts])
            shader.uniform_float("color", fond)
            batch_for_shader(shader, "TRIS", {"pos": pts}, indices=triangles).draw(shader)
            segments = [p for angle, pas in traits for s in hachures(pts, angle, pas) for p in s]
            if segments:
                gpu.state.line_width_set(1)
                shader.uniform_float("color", couleur)
                batch_for_shader(shader, "LINES", {"pos": segments}).draw(shader)
            gpu.state.line_width_set(2.5)  # contour de coupe en trait fort
            shader.uniform_float("color", (0, 0, 0, 1))
            batch_for_shader(shader, "LINE_LOOP", {"pos": pts}).draw(shader)
    if symboles:
        gpu.state.line_width_set(1.5)
        shader.uniform_float("color", (0, 0, 0, 1))
        batch_for_shader(shader, "LINES", {"pos": symboles}).draw(shader)
    gpu.state.line_width_set(1)
    gpu.state.blend_set("NONE")


def dessiner_cotes():
    context = bpy.context
    f = tool.Ifc.get()
    if not f or not context.region_data:
        return
    etage = tool.Root.get_default_container()
    region, rv3d = context.region, context.region_data
    shader = _shader()
    couleur = (0.05, 0.05, 0.05, 1)
    gpu.state.blend_set("ALPHA")
    for cote in f.by_type("IfcAnnotation"):
        if cote.ObjectType != "DIMENSION" or (etage and ifcopenshell.util.element.get_container(cote) != etage):
            continue
        obj = tool.Ifc.get_object(cote)
        if not obj or obj.type != "MESH" or obj.hide_get() or len(obj.data.vertices) < 2:
            continue
        monde = [obj.matrix_world @ v.co for v in obj.data.vertices]
        ecran = [view3d_utils.location_3d_to_region_2d(region, rv3d, p) for p in monde]
        if any(p is None for p in ecran):
            continue
        donnees = ifcopenshell.util.element.get_pset(cote, "Trame_Cote") or {}
        mesures = json.loads(donnees.get("Points", "[]"))
        segments = []
        # Ligne de cote et traits obliques à chaque point (comme Archicad).
        for a, b in zip(ecran, ecran[1:]):
            segments += [a.to_3d(), b.to_3d()]
        direction = (ecran[-1] - ecran[0]).normalized() if (ecran[-1] - ecran[0]).length else Vector((1, 0))
        echelle = context.preferences.system.pixel_size
        oblique = (direction + Vector((-direction.y, direction.x))).normalized() * 6 * echelle
        for p in ecran:
            segments += [(p - oblique).to_3d(), (p + oblique).to_3d()]
        # Lignes d'attache : du point mesuré jusqu'un peu au-delà de la ligne de cote.
        for mesure, sur_ligne in attaches(mesures, donnees.get("Decalage", 0.0)):
            pe = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector((*mesure, monde[0].z)))
            qe = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector((*sur_ligne, monde[0].z)))
            if pe and qe and (qe - pe).length > 4:
                d = (qe - pe).normalized()
                segments += [(pe + d * 3).to_3d(), (qe + d * 5).to_3d()]
        gpu.state.line_width_set(context.preferences.system.pixel_size)
        shader.uniform_float("color", couleur)
        batch_for_shader(shader, "LINES", {"pos": segments}).draw(shader)
        # Longueurs au-dessus de chaque segment, dans le sens de la ligne.
        blf.size(0, 12 * context.preferences.system.ui_scale * context.preferences.system.pixel_size)
        blf.color(0, *couleur)
        for (wa, wb), (a, b) in zip(zip(monde, monde[1:]), zip(ecran, ecran[1:])):
            texte = texte_longueur((wb - wa).length)
            angle = math.atan2((b - a).y, (b - a).x)
            if angle > math.pi / 2 or angle <= -math.pi / 2:
                angle += math.pi  # texte toujours lisible
            largeur, _ = blf.dimensions(0, texte)
            axe = Vector((math.cos(angle), math.sin(angle)))
            milieu = (a + b) / 2 - axe * largeur / 2 + Vector((-axe.y, axe.x)) * 4 * context.preferences.system.pixel_size
            blf.enable(0, blf.ROTATION)
            blf.rotation(0, angle)
            blf.position(0, milieu.x, milieu.y, 0)
            blf.draw(0, texte)
            blf.disable(0, blf.ROTATION)
    gpu.state.blend_set("NONE")


_poignees = []


def installer():
    if bpy.app.background or _poignees:
        return
    _poignees.append(bpy.types.SpaceView3D.draw_handler_add(dessiner_hachures, (), "WINDOW", "POST_VIEW"))
    _poignees.append(bpy.types.SpaceView3D.draw_handler_add(dessiner_cotes, (), "WINDOW", "POST_PIXEL"))


def desinstaller():
    while _poignees:
        bpy.types.SpaceView3D.draw_handler_remove(_poignees.pop(), "WINDOW")
    _cache.clear()
    _cache_symboles.clear()
