# Trame - OpenBIM Blender Add-on
# Copyright (C) 2021 Dion Moult <dion@thinkmoult.com>
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bonsai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bonsai.  If not, see <http://www.gnu.org/licenses/>.
#
# Ignore unused imports.
# ruff: file-ignore[unused-import]

from trame.tool.aggregate import Aggregate
from trame.tool.array import Array
from trame.tool.attribute import Attribute
from trame.tool.bcf import Bcf
from trame.tool.blender import Blender
from trame.tool.boundary import Boundary
from trame.tool.brick import Brick
from trame.tool.bsdd import Bsdd
from trame.tool.cad import Cad
from trame.tool.clash import Clash
from trame.tool.classification import Classification
from trame.tool.clip_box import ClipBox
from trame.tool.collector import Collector
from trame.tool.connection import Connection
from trame.tool.context import Context
from trame.tool.cost import Cost
from trame.tool.covering import Covering
from trame.tool.debug import Debug
from trame.tool.demo import Demo
from trame.tool.document import Document
from trame.tool.drawing import Drawing
from trame.tool.duplicate import Duplicate
from trame.tool.feature import Feature
from trame.tool.geometry import Geometry
from trame.tool.georeference import Georeference
from trame.tool.group import Group
from trame.tool.ifc import Ifc
from trame.tool.ifcgit import IfcGit, IfcGitRepo
from trame.tool.layer import Layer
from trame.tool.library import Library
from trame.tool.loader import Loader
from trame.tool.material import Material
from trame.tool.misc import Misc
from trame.tool.model import Model
from trame.tool.nest import Nest
from trame.tool.owner import Owner
from trame.tool.parametric import Parametric
from trame.tool.patch import Patch
from trame.tool.polyline import Polyline
from trame.tool.profile import Profile
from trame.tool.project import Project
from trame.tool.pset import Pset
from trame.tool.pset_template import PsetTemplate
from trame.tool.qto import Qto
from trame.tool.raycast import Raycast
from trame.tool.resource import Resource
from trame.tool.root import Root
from trame.tool.search import Search
from trame.tool.sequence import Sequence
from trame.tool.slab import Slab
from trame.tool.snap import Snap
from trame.tool.spatial import Spatial
from trame.tool.structural import Structural
from trame.tool.style import Style
from trame.tool.surveyor import Surveyor
from trame.tool.system import System
from trame.tool.tester import Tester
from trame.tool.type import Type
from trame.tool.unit import Unit
from trame.tool.wall import Wall
from trame.tool.web import Web

# Have to move after import of tool.drawing
from trame.tool.autosave import Autosave  # isort: skip
