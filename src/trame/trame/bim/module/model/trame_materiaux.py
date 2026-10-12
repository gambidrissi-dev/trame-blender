# Trame - matériaux : une famille de hachure pour le plan et une couleur pour la 3D, comme dans Archicad.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import bpy
import ifcopenshell.api.material
import ifcopenshell.api.style
import ifcopenshell.util.representation

import trame.core.style
import trame.tool as tool

# Famille : (libellé, catégorie IFC). La catégorie décide de la hachure en plan (voir trame_plan.motif).
FAMILLES = {
    "MACONNERIE": ("Maçonnerie (hachures à 45°)", "block"),
    "BETON": ("Béton (gris, hachures serrées)", "concrete"),
    "BOIS": ("Bois (hachures croisées)", "wood"),
    "ISOLANT": ("Isolant (hachures fines)", "insulation"),
    "PLATRE": ("Plâtre (gris clair)", "gypsum"),
    "PLEIN": ("Autre (noir plein)", ""),
}

PAR_DEFAUT = (
    ("Maçonnerie", "MACONNERIE", (0.85, 0.74, 0.62)),
    ("Béton", "BETON", (0.75, 0.75, 0.72)),
    ("Bois", "BOIS", (0.72, 0.53, 0.32)),
    ("Isolant", "ISOLANT", (0.96, 0.88, 0.55)),
    ("Plâtre", "PLATRE", (0.95, 0.95, 0.93)),
)


def creer_materiau(nom: str, famille: str, couleur) -> "ifcopenshell.entity_instance":
    """Matériau IFC avec sa catégorie (hachure) et un style de surface (couleur 3D)."""
    f = tool.Ifc.get()
    materiau = ifcopenshell.api.material.add_material(f, name=nom, category=FAMILLES[famille][1] or None)
    # Matériau Blender lié au style IFC (comme le fait Bonsai) : la couleur s'affiche sur les objets en 3D.
    rendu = bpy.data.materials.new(nom)
    rendu.diffuse_color = (*couleur, 1.0)
    style = trame.core.style.add_style(tool.Ifc, tool.Style, obj=rendu)
    if contexte := ifcopenshell.util.representation.get_context(f, "Model", "Body", "MODEL_VIEW"):
        ifcopenshell.api.style.assign_material_style(f, material=materiau, style=style, context=contexte)
    return materiau


def materiaux() -> list:
    """Matériaux du projet, triés ; les matériaux par défaut sont créés au premier besoin."""
    f = tool.Ifc.get()
    noms = {m.Name for m in f.by_type("IfcMaterial")}
    for nom, famille, couleur in PAR_DEFAUT:
        if nom not in noms:
            creer_materiau(nom, famille, couleur)
    return sorted(f.by_type("IfcMaterial"), key=lambda m: m.Name or "")


def materiau(nom: str):
    return next((m for m in materiaux() if m.Name == nom), None)


_items = []  # Blender exige que les libellés d'une liste dynamique restent en mémoire


def items_materiaux(self, context):
    _items.clear()
    if tool.Ifc.get():
        existants = sorted(tool.Ifc.get().by_type("IfcMaterial"), key=lambda m: m.Name or "")  # lecture seule
        _items.extend((m.Name, m.Name, FAMILLES[famille_de(m)][0]) for m in existants)
    noms = {i[0] for i in _items}
    _items.extend((nom, nom, FAMILLES[famille][0]) for nom, famille, _ in PAR_DEFAUT if nom not in noms)
    return _items


def famille_de(m) -> str:
    categorie = (m.Category or "").lower() if hasattr(m, "Category") else ""
    return next((k for k, (_, c) in FAMILLES.items() if c and c == categorie), "PLEIN")


class TRAME_OT_creer_materiau(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.trame_creer_materiau"
    bl_label = "Créer un matériau"
    bl_description = "Nouveau matériau : son nom, sa hachure en plan et sa couleur en 3D"
    bl_options = {"REGISTER", "UNDO"}

    nom: bpy.props.StringProperty(name="Nom", default="Nouveau matériau", options={"SKIP_SAVE"})
    famille: bpy.props.EnumProperty(name="Hachure", items=[(k, v[0], "") for k, v in FAMILLES.items()])
    couleur: bpy.props.FloatVectorProperty(name="Couleur 3D", subtype="COLOR", size=3, min=0, max=1,
                                           default=(0.8, 0.8, 0.8))

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get() is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Nouveau matériau", confirm_text="Créer")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        for prop in ("nom", "famille", "couleur"):
            col.prop(self, prop)

    def _execute(self, context):
        if any(m.Name == self.nom for m in tool.Ifc.get().by_type("IfcMaterial")):
            self.report({"WARNING"}, f"Le matériau « {self.nom} » existe déjà")
            return {"CANCELLED"}
        creer_materiau(self.nom, self.famille, self.couleur)
        return {"FINISHED"}
