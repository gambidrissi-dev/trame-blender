# Trame - calques façon Archicad : chaque élément sur son calque, qu'on affiche, masque ou verrouille.
# Les calques sont des IfcPresentationLayerWithStyle : leur état (LayerOn, LayerBlocked) est enregistré dans l'IFC.
# This file is part of Trame, derived from Bonsai (GPL-3.0-or-later).

import bpy
import ifcopenshell.api.layer
import ifcopenshell.util.element

import trame.tool as tool

CALQUES = ("Murs", "Cloisons", "Dalles", "Toiture", "Structure", "Menuiseries", "Escaliers", "Cotation", "Terrain")
EPAISSEUR_CLOISON = 0.15  # en dessous, un mur va sur le calque « Cloisons »


def calque_pour(element) -> str:
    """Calque Archicad d'un élément selon sa classe (None s'il n'en a pas)."""
    if element.is_a("IfcWall"):
        type_ = ifcopenshell.util.element.get_type(element) or element
        epaisseur = tool.Model.get_material_layer_parameters(type_)["thickness"] or 0
        return "Cloisons" if 0 < epaisseur < EPAISSEUR_CLOISON else "Murs"
    if element.is_a("IfcSlab"):
        return "Toiture" if element.PredefinedType == "ROOF" or getattr(
            ifcopenshell.util.element.get_type(element), "PredefinedType", None) == "ROOF" else "Dalles"
    for classes, nom in (
        (("IfcRoof",), "Toiture"),
        (("IfcColumn", "IfcBeam"), "Structure"),
        (("IfcDoor", "IfcWindow"), "Menuiseries"),
        (("IfcStair", "IfcStairFlight", "IfcRamp", "IfcRailing"), "Escaliers"),
        (("IfcGeographicElement",), "Terrain"),
    ):
        if any(element.is_a(c) for c in classes):
            return nom
    if element.is_a("IfcAnnotation") and element.ObjectType == "DIMENSION":
        return "Cotation"
    return None


def calques() -> dict:
    """Calques Trame du projet {nom: calque}, créés au premier besoin."""
    f = tool.Ifc.get()
    existants = {c.Name: c for c in f.by_type("IfcPresentationLayerWithStyle")}
    for nom in CALQUES:
        if nom not in existants:
            calque = ifcopenshell.api.layer.add_layer_with_style(f, name=nom)
            calque.LayerOn, calque.LayerFrozen, calque.LayerBlocked = True, False, False
            existants[nom] = calque
    return {nom: existants[nom] for nom in CALQUES}


def representations(element) -> list:
    return list(element.Representation.Representations) if getattr(element, "Representation", None) else []


def calque_de(element):
    for rep in representations(element):
        for affectation in rep.LayerAssignments or []:
            if affectation.is_a("IfcPresentationLayerWithStyle"):
                return affectation
    return None


def ranger_calques() -> int:
    """Range sur son calque chaque élément qui n'en a pas encore ; renvoie le nombre d'éléments rangés."""
    f = tool.Ifc.get()
    tous = calques()
    ranges = 0
    for element in f.by_type("IfcProduct"):
        if calque_de(element) or not (nom := calque_pour(element)) or not (reps := representations(element)):
            continue
        ifcopenshell.api.layer.assign_layer(f, items=reps, layer=tous[nom])
        appliquer_etat(element, tous[nom])
        ranges += 1
    return ranges


def elements_du_calque(calque) -> set:
    elements = set()
    for rep in calque.AssignedItems or []:
        for definition in getattr(rep, "OfProductRepresentation", []) or []:
            elements.update(definition.ShapeOfProduct)
    return elements


def appliquer_etat(element, calque) -> None:
    """Visible / verrouillé dans Blender selon l'état du calque."""
    obj = tool.Ifc.get_object(element)
    if not obj:
        return
    try:
        obj.hide_set(not calque.LayerOn)
    except RuntimeError:
        pass  # objet hors de la scène affichée
    obj.hide_select = bool(calque.LayerBlocked)


def basculer(nom: str, attribut: str) -> None:
    calque = calques()[nom]
    setattr(calque, attribut, not getattr(calque, attribut))
    for element in elements_du_calque(calque):
        appliquer_etat(element, calque)


class TRAME_OT_basculer_calque(bpy.types.Operator):
    bl_idname = "bim.trame_basculer_calque"
    bl_label = "Calque"
    bl_description = "Afficher/masquer ou verrouiller/déverrouiller les éléments de ce calque"
    bl_options = {"REGISTER", "UNDO"}
    nom: bpy.props.StringProperty()
    attribut: bpy.props.EnumProperty(items=(("LayerOn", "Visible", ""), ("LayerBlocked", "Verrouillé", "")))

    def execute(self, context):
        basculer(self.nom, self.attribut)
        return {"FINISHED"}
