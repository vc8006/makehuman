#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
**Project Name:**      MakeHuman

**Product Home Page:** http://www.makehumancommunity.org/

**Github Code Home Page:**    https://github.com/makehumancommunity/

**Authors:**           Thomas Larsson, Jonas Hauquier

**Copyright(c):**      MakeHuman Team 2001-2020

**Licensing:**         AGPL3

    This file is part of MakeHuman (www.makehumancommunity.org).

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.


Abstract
--------
Exports proxy mesh to obj

"""

import wavefront
import os
from progress import Progress
import numpy as np

from logging import *
LOG_FORMAT = "[%(asctime)s] [%(filename)s:%(lineno)s - %(funcName)s() ] %(message)s"
# LOG_FORMAT = '%m-%d %H:%M:%S','[%(asctime)s] {%(pathname)s:%(lineno)d} %(funcName)s - %(message)s'
basicConfig(filename="allLogs.log",level = DEBUG,format=LOG_FORMAT)


#
#    exportObj(human, filepath, config):
#

def exportObj(filepath, config=None):
    debug("log")

    print("here at mh2obj_copy")
    print("printing filepath",filepath)
    print(config,"configggggggggg")

    progress = Progress(0, None)
    human = config.human
    config.setupTexFolder(filepath)
    filename = os.path.basename(filepath)
    name = config.goodName(os.path.splitext(filename)[0])

    print(name,"nameeeeeeeeeeee")


    progress(0, 0.3, "Collecting Objects")
    objects = human.getObjects(excludeZeroFaceObjs=not config.hiddenGeom)
    meshes = [o.mesh for o in objects]

    print(meshes,"meshessssssssss")


    if config.hiddenGeom:
        # Disable the face masking on copies of the input meshes
        meshes = [m.clone(filterMaskedVerts=False) for m in meshes]
        for m in meshes:
            # Would be faster if we could tell clone() to do this, but it would 
            # make the interface more complex.
            # We could also let the wavefront module do this, but this would 
            # introduce unwanted "magic" behaviour into the export function.
            face_mask = np.ones(m.face_mask.shape, dtype=bool)
            m.changeFaceMask(face_mask)
            m.calcNormals()
            m.updateIndexBuffer()

    progress(0.3, 0.99, "Writing Objects")
    wavefront.writeObjFile(filepath, meshes, True, config, filterMaskedFaces=not config.hiddenGeom)

    progress(1.0, None, "OBJ Export finished. Output file: %s" % filepath)
