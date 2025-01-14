#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
**Project Name:**      MakeHuman

**Product Home Page:** http://www.makehumancommunity.org/

**Github Code Home Page:**    https://github.com/makehumancommunity/

**Authors:**           Thomas Larsson, Jonas Hauquier

**Copyright(c):**      MakeHuman Team 2001-2020

**Licensing:**         AGPL3

    This file is part of MakeHuman Community (www.makehumancommunity.org).

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

TODO
"""

import os
import math
import numpy as np
from core import G
import getpath
import log
from collections import OrderedDict
import makehuman

import material
import json

#
#   Proxy types. Loop over simple proxy types to do all proxies.
#   Some code use lowercase proxy types instead.
#

SimpleProxyTypes = ['Hair', 'Eyes', 'Eyebrows', 'Eyelashes', 'Teeth', 'Tongue']
ProxyTypes = ['Proxymeshes', 'Clothes'] + SimpleProxyTypes

SimpleProxyTypesLower = []
for name in SimpleProxyTypes:
    SimpleProxyTypesLower.append(name.lower())

_A7converter = None
Unit3 = np.identity(3,float)


class Proxy:
    def __init__(self, file, type, human):
        log.debug("Loading proxy file: %s.", file)
        import makehuman

        name = os.path.splitext(os.path.basename(file))[0]
        self.name = name.capitalize().replace(" ","_")
        self.license = makehuman.getAssetLicense()
        self.description = ""
        self.type = type
        self.object = None
        self.human = human
        if not human:
            raise RuntimeError("Proxy constructor expects a valid human object.")
        self.file = file
        if file:
            self.mtime = os.path.getmtime(file)
        else:
            self.mtime = None
        self.uuid = None
        self.basemesh = makehuman.getBasemeshVersion()
        self.tags = []
        self.version = 110

        self.ref_vIdxs = None       # (Vidx1,Vidx2,Vidx3) list with references to human vertex indices, indexed by proxy vert
        self.weights = None         # (w1,w2,w3) list, with weights per human vertex (mapped by ref_vIdxs), indexed by proxy vert
        self.vertWeights = {}       # (proxy-vert, weight) list for each parent vert (reverse mapping of self.weights, indexed by human vertex)
        self.offsets = None         # (x,y,z) list of vertex offsets, indexed by proxy vert

        self.vertexBoneWeights = None   # Explicitly defined custom vertex-to-bone weights, connecting the proxy mesh to the reference skeleton (optional)
                                        # Not to be confused with the vertex weights assigned for mapping the proxy mesh geometry to the base mesh

        self.tmatrix = TMatrix()    # Offset transformation matrix. Replaces scale

        self.z_depth = -1       # Render order depth for the proxy object. Also used to determine which proxy object should mask others (delete faces)
        self.max_pole = None    # Signifies the maximum number of faces per vertex on the mesh topology. Set to none for default.

        self.special_pose = {}  # Special poses that should be set on the human when this proxy is active to make it look good

        self.uvLayers = {}  # TODO what is this used for?

        self.material = material.Material(self.name)
        self._backUpMaterial = None

        self._obj_file = None
        self._vertexBoneWeights_file = None
        self._material_file = None

        self.deleteVerts = np.zeros(human.meshData.getVertexCount(), bool)

        self.weightsCache = None
        self.cacheSkel = None

    @property
    def material_file(self):
        folder = os.path.dirname(self.file) if self.file else None
        return _getFilePath(self._material_file, folder)

    @property
    def obj_file(self):
        folder = os.path.dirname(self.file) if self.file else None
        return _getFilePath(self._obj_file, folder, ['npz', 'obj'])

    @property
    def vertexBoneWeights_file(self):
        folder = os.path.dirname(self.file) if self.file else None
        return _getFilePath(self._vertexBoneWeights_file, folder)

    def __repr__(self):
        return ("<Proxy %s %s %s %s>" % (self.name, self.type, self.file, self.uuid))


    def getSeedMesh(self):
        for pxy in self.human.getProxies():
            if self == pxy:
                return pxy.object.getSeedMesh()

        if self.type == "Proxymeshes":
            if not self.human.proxy:
                return None
            return self.human.getProxyMesh()
        elif self.type in ["Converter"]:
            return None
        else:
            raise NameError("Unknown proxy type %s" % self.type)


    def getMesh(self):
        if not self.object:
            return None
        return self.object.mesh


    def loadMeshAndObject(self, human):
        import files3d
        import guicommon

        obj = False
        mesh = files3d.loadMesh(self.obj_file, maxFaces = self.max_pole)
        if not mesh:
            log.error("Failed to load %s", self.obj_file)
        else:
            mesh.priority = self.z_depth           # Set render order
            mesh.setCameraProjection(0)             # Set to model camera
        
            obj = self.object = guicommon.Object(mesh, human.getPosition())
            obj.proxy = self
            obj.material = self.material
            obj.setRotation(human.getRotation())
            obj.setSolid(human.solid)    # Set to wireframe if human is in wireframe
            # TODO perhaps other properties should be copied from human to object, such as subdivision state. For other hints, and duplicate code, see guicommon Object.setProxy()

        # TODO why return both obj and mesh if you can access the mesh easily through obj.mesh?
        return mesh,obj


    def _finalize(self, refVerts):
        """
        Final step in parsing/loading a proxy file. Initializes numpy structures
        for performance improvement.
        """
        self.weights = np.asarray([v._weights for v in refVerts], dtype=np.float32)
        self.ref_vIdxs = np.asarray([v._verts for v in refVerts], dtype=np.uint32)
        self.offsets = np.asarray([v._offset for v in refVerts], dtype=np.float32)


    def _reloadReverseMapping(self):
        """
        Reconstruct reverse vertex (and weights) mapping
        """
        self.vertWeights = {}
        for pxy_vIdx in range(self.ref_vIdxs.shape[0]):
            _addProxyVertWeight(self.vertWeights, self.ref_vIdxs[pxy_vIdx, 0], pxy_vIdx, self.weights[pxy_vIdx, 0])
            _addProxyVertWeight(self.vertWeights, self.ref_vIdxs[pxy_vIdx, 1], pxy_vIdx, self.weights[pxy_vIdx, 1])
            _addProxyVertWeight(self.vertWeights, self.ref_vIdxs[pxy_vIdx, 2], pxy_vIdx, self.weights[pxy_vIdx, 2])


    def getCoords(self, fit_to_posed=False):
        if fit_to_posed:
            hcoord = self.human.meshData.coord
        else:
            hcoord = self.human.getRestposeCoordinates()
        matrix = self.tmatrix.getMatrix(hcoord)

        ref_vIdxs = self.ref_vIdxs
        weights = self.weights

        coord = (
            hcoord[ref_vIdxs[:,0]] * weights[:,0,None] +
            hcoord[ref_vIdxs[:,1]] * weights[:,1,None] +
            hcoord[ref_vIdxs[:,2]] * weights[:,2,None] +
            np.dot(matrix, self.offsets.transpose()).transpose()
            )

        return coord


    def update(self, mesh, fit_to_posed=False):
        #log.debug("Updating proxy %s.", self.name)
        coords = self.getCoords(fit_to_posed)
        mesh.changeCoords(coords)
        mesh.calcNormals()


    def getUuid(self):
        if self.uuid:
            return self.uuid
        else:
            return self.name

    def hasCustomVertexWeights(self):
        """
        Determines whether this proxy explicitly defines its own set of vertex
        to bone weights (defined on the bones of the reference skeleton).
        Returns True if this proxy has custom vertex weights, False if it does
        not, in which case vertex weights will be derived from the weights of
        the basemesh, mapped through the vertex mapping of the proxy.
        """
        return self.vertexBoneWeights is not None


    def getVertexWeights(self, humanWeights, skel=None, allowCache=False):
        """
        Map armature weights mapped to the human to the proxy mesh through the
        proxy mapping.
        humanWeights is expected to be an animation.VertexBoneWeights object.

        Only when this proxy has custom weights:
        Optionally remaps the weights to fit a user-selected skeleton when a
        skel is supplied as argument. If no skel argument is provided, the 
        weights for the base skeleton are returned.

        Note: these vertex weights are intended for rigging and are not to be 
        confused with getWeights() which returns the weights of the proxy 
        mapping to the basemesh.
        """
        # Override proxy weights mapping behaviour if this proxy has its own
        # bone weights defined explicitly.
        # This requires remapping the vertex weights of the proxy, defined on
        # the bones of the reference skeleton, to those of the current skeleton.
        # The current skeleton is retrieved from the human object linked to this
        # proxy.
        
        import time
        import log

        if self.hasCustomVertexWeights():
            # TODO we could introduce caching of weights here as long as the skeleton is not changed
            if skel is None:
                return self.human.getBaseSkeleton().getVertexWeights(self.vertexBoneWeights, force_remap=True)
            else:
                return skel.getVertexWeights(self.vertexBoneWeights, force_remap=True)

        # Remap weights through proxy mapping
        WEIGHT_THRESHOLD = 1e-4  # Threshold for including bone weight

        recalculate = True
        weights = OrderedDict()

        if not allowCache:
            pass
            #print("Caching not allowed")
        else:
            if self.weightsCache is None:
                pass
                #print("There is no cache")
            else:
                if not skel is None:
                    if skel == self.cacheSkel:
                        recalculate = False
                    else:
                        log.debug("The skeleton is different")

        if recalculate:
            log.debug("remapping weights for proxy " + self.name)
            start = time.perf_counter()
            for bname, (indxs, wghts) in list(humanWeights.data.items()):
                vgroup = []
                empty = True
                for (v,wt) in zip(indxs, wghts):
                    try:
                        vlist = self.vertWeights[v]
                    except KeyError:
                        vlist = []
                    for (pv, w) in vlist:
                        pw = w*wt
                        if (pw > WEIGHT_THRESHOLD):
                            vgroup.append((pv, pw))
                            empty = False
                if not empty:
                    weights[bname] = vgroup
            stop = time.perf_counter()

            hw = humanWeights.create(weights)
            if allowCache:
                self.weightsCache = hw
                self.cacheSkel = skel
            else:
                self.weightsCache = None
                self.cacheSkel = None

            log.debug("remapping weights for %s took %.5f seconds", self.name, stop - start)
        else:
            hw = self.weightsCache
        
        return hw


doRefVerts = 1
doWeights = 2
doDeleteVerts = 3

def loadProxy(human, path, type="Clothes"):
    try:
        print("here at loadproxy at proxy.py path ",path)
        npzpath = os.path.splitext(path)[0] + '.mhpxy'
        asciipath = os.path.splitext(path)[0] + getAsciiFileExtension(type)
        try:
            if not os.path.isfile(npzpath):
                log.message('compiled proxy file missing: %s', npzpath)
                raise RuntimeError('compiled proxy file missing: %s', npzpath)
            if os.path.isfile(asciipath) and os.path.getmtime(asciipath) > os.path.getmtime(npzpath):
                log.message('compiled proxy file out of date: %s', npzpath)
                raise RuntimeError('compiled file out of date: %s', npzpath)
            print("here at second try block in proxy.py")
            proxy = loadBinaryProxy(npzpath, human, type)
            print("here at proxy.py after loadbinaryproxy call proxy = ",proxy)
        except Exception as e:
            showTrace = not isinstance(e, RuntimeError)
            log.warning("Problem loading binary proxy: %s", e, exc_info=showTrace)
            proxy = loadTextProxy(human, asciipath, type)    # TODO perhaps proxy type should be stored in .mhclo file too
            #!!!!!!!!!!!!!!!!!
            print("printing proxy from proxy.py",proxy)
            
            if getpath.isSubPath(npzpath, getpath.getPath()):
                # Only write compiled binary proxies to user data path
                print("here if getpath.isSubpath")
                try:
                    log.message('Compiling binary proxy file %s', npzpath)
                    print("here at exception in proxy.py now savebinaryproxy will run")
                    saveBinaryProxy(proxy, npzpath)
                except Exception:
                    log.notice('unable to save compiled proxy: %s', npzpath, exc_info=True)
                    if os.path.isfile(npzpath):
                        # Remove file again, in case an empty file is left
                        try:
                            os.remove(npzpath)
                        except Exception as e:
                            log.warning("Could not remove empty file %s that was left behind (%s).", npzpath, e)
            else:
                print("here at not writing compilex proxies to system paths")
                log.debug('Not writing compiled proxies to system paths (%s).', npzpath)
    except:
        print("unable to load proxy file")
        log.error('Unable to load proxy file: %s', path, exc_info=True)
        return None

    return proxy

def loadTextProxy(human, filepath, type="Clothes"):
    try:
        fp = open(filepath, "r", encoding="utf-8", errors='ignore')
    except IOError:
        log.error("*** Cannot open %s", filepath)
        return None

    folder = os.path.realpath(os.path.expanduser(os.path.dirname(filepath)))
    proxy = Proxy(filepath, type, human)
    proxy.max_pole = 8
    refVerts = []

    status = 0
    vnum = 0
    for line in fp:
        words = line.split()

        if len(words) == 0:
            # Reset status on empty line
            #status = 0
            continue

        if words[0].startswith('#'):
            # Comment
            # Try interpreting comment attributes as license info
            proxy.license.updateFromComment(line)
            continue

        key = words[0]

        if key == 'name':
            proxy.name = " ".join(words[1:])
        elif key == 'uuid':
            proxy.uuid = " ".join(words[1:])
        elif key == 'description':
            proxy.description = " ".join(words[1:])
        elif key in ['author', 'license', 'homepage', 'author:', 'license:']:
            proxy.license.updateFromComment(words)
        elif key == 'tag':
            proxy.tags.append( " ".join(words[1:]).lower() )
        elif key == 'version':
            proxy.version = int(words[1])
        elif key == 'z_depth':
            proxy.z_depth = int(words[1])
        elif key == 'max_pole':
            proxy.max_pole = int(words[1])
        elif key == 'special_pose':
            proxy.special_pose[words[1]] = words[2]

        elif key == 'verts':
            status = doRefVerts
        elif key == 'weights':
            status = doWeights
            if proxy.weights is None:
                proxy.weights = {}
            weights = []
            proxy.weights[words[1]] = weights
        elif key == "delete_verts":
            status = doDeleteVerts

        elif key == 'obj_file':
            proxy._obj_file = _getFileName(folder, words[1], ".obj")

        elif key == 'material':
            matFile = _getFileName(folder, words[1], ".mhmat")
            proxy._material_file = matFile
            proxy.material.fromFile(proxy.material_file)

        elif key == 'vertexboneweights_file':
            from animation import VertexBoneWeights
            proxy._vertexBoneWeights_file = _getFileName(folder, words[1], ".jsonw")
            proxy.vertexBoneWeights = VertexBoneWeights.fromFile(proxy.vertexBoneWeights_file)

        elif key == 'backface_culling':
            # TODO remove in future
            log.warning('Deprecated parameter "backface_culling" used in proxy file. Set property backfaceCull in material instead.')
        elif key == 'transparent':
            # TODO remove in future
            log.warning('Deprecated parameter "transparent" used in proxy file. Set property in material file instead.')

        elif key == 'uvLayer':
            # TODO is this still used?
            if len(words) > 2:
                layer = int(words[1])
                uvFile = words[2]
            else:
                layer = 0
                uvFile = words[1]
            #uvMap = material.UVMap(proxy.name+"UV"+str(layer))
            #uvMap.read(proxy.mesh, _getFileName(folder, uvFile, ".mhuv"))
            # Delayed load, only store path here
            proxy.uvLayers[layer] = _getFileName(folder, uvFile, ".mhuv")

        elif key == 'x_scale':
            proxy.tmatrix.getScaleData(words, 0)
        elif key == 'y_scale':
            proxy.tmatrix.getScaleData(words, 1)
        elif key == 'z_scale':
            proxy.tmatrix.getScaleData(words, 2)

        elif key == 'shear_x':
            proxy.tmatrix.getShearData(words, 0, None)
        elif key == 'shear_y':
            proxy.tmatrix.getShearData(words, 1, None)
        elif key == 'shear_z':
            proxy.tmatrix.getShearData(words, 2, None)
        elif key == 'l_shear_x':
            proxy.tmatrix.getShearData(words, 0, 'Left')
        elif key == 'l_shear_y':
            proxy.tmatrix.getShearData(words, 1, 'Left')
        elif key == 'l_shear_z':
            proxy.tmatrix.getShearData(words, 2, 'Left')
        elif key == 'r_shear_x':
            proxy.tmatrix.getShearData(words, 0, 'Right')
        elif key == 'r_shear_y':
            proxy.tmatrix.getShearData(words, 1, 'Right')
        elif key == 'r_shear_z':
            proxy.tmatrix.getShearData(words, 2, 'Right')

        elif key == 'basemesh':
            proxy.basemesh = words[1]

        elif key in ['shapekey', 'subsurf', 'shrinkwrap', 'solidify', 'objfile_layer', 'uvtex_layer', 'use_projection', 'mask_uv_layer', 'texture_uv_layer', 'delete', 'vertexgroup_file']:
            log.warning('Deprecated parameter "%s" used in proxy file. Please remove.', key)


        elif status == doRefVerts:
            refVert = ProxyRefVert(human)
            refVerts.append(refVert)
            if len(words) == 1:
                refVert.fromSingle(words, vnum, proxy.vertWeights)
            else:
                refVert.fromTriple(words, vnum, proxy.vertWeights)
            vnum += 1

        elif status == doWeights:
            v = int(words[0])
            w = float(words[1])
            weights.append((v,w))

        elif status == doDeleteVerts:
            sequence = False
            for v in words:
                if v == "-":
                    sequence = True
                else:
                    v1 = int(v)
                    if sequence:
                        for vn in range(v0,v1+1):
                            proxy.deleteVerts[vn] = True
                        sequence = False
                    else:
                        proxy.deleteVerts[v1] = True
                    v0 = v1

        else:
            log.warning('Unknown keyword %s found in proxy file %s', key, filepath)
    fp.close()

    if proxy.z_depth == -1:
        log.warning('Proxy file %s does not specify a Z depth. Using 50.', filepath)
        proxy.z_depth = 50

    # since max-pole is used for the calculation of neighboring planes we have to double it initially
    proxy.max_pole *= 2
    proxy._finalize(refVerts)

    return proxy


def saveBinaryProxy(proxy, path):
    def _properPath(path):
        return getpath.getJailedPath(path, folder)

    with open(path, 'wb') as fp:
        tagStr, tagIdx = _packStringList(proxy.tags)
        uvStr,uvIdx = _packStringList([ _properPath(proxy.uvLayers[k]) for k in sorted(proxy.uvLayers.keys()) ])

        licStr, licIdx = proxy.license.toNumpyString()

        folder = os.path.dirname(path)


        vars_ = dict(
            #proxyType = np.fromstring(proxy.type, dtype='S1'),     # TODO store proxy type?
            name = np.fromstring(proxy.name, dtype='S1'),
            uuid = np.fromstring(proxy.uuid, dtype='S1'),
            description = np.fromstring(proxy.description, dtype='S1'),
            basemesh = np.fromstring(proxy.basemesh, dtype='S1'),
            tags_str = tagStr,
            tags_idx = tagIdx,
            lic_str = licStr,
            lic_idx = licIdx,
            uvLayers_str = uvStr,
            uvLayers_idx = uvIdx,
            obj_file = np.fromstring(_properPath(proxy.obj_file), dtype='S1'),
            version = np.asarray(proxy.version, dtype=np.int32)
        )

        if proxy.material_file:
            vars_["material_file"] = np.fromstring(_properPath(proxy.material_file), dtype='S1')

        if np.any(proxy.deleteVerts):
            vars_["deleteVerts"] = proxy.deleteVerts

        if proxy.z_depth is not None and proxy.z_depth != -1:
            vars_["z_depth"] = np.asarray(proxy.z_depth, dtype=np.int32)

        if proxy.max_pole:
            vars_["max_pole"] = np.asarray(proxy.max_pole, dtype=np.uint32)

        proxy.tmatrix.toNumpyStruct(vars_)

        special_poses = []
        for posetype, posename in list(proxy.special_pose.items()):
            special_poses.append(posetype)
            special_poses.append(posename)
        specialposeStr, specialposeIdx = _packStringList(special_poses)
        vars_["special_pose_str"] = specialposeStr
        vars_["special_pose_idx"] = specialposeIdx

        if proxy.weights[:,1:].any():
            # 3 ref verts used in this proxy
            num_refverts = 3
            vars_["ref_vIdxs"] = proxy.ref_vIdxs
            vars_["offsets"] = proxy.offsets
            vars_["weights"] = proxy.weights
        else:
            # Proxy uses exact fitting exclusively: store npz file more compactly
            num_refverts = 1
            vars_["ref_vIdxs"] = proxy.ref_vIdxs[:,0]
            vars_["weights"] = proxy.weights[:,0]
        vars_['num_refverts'] = np.asarray(num_refverts, dtype=np.int32)

        if proxy.vertexBoneWeights_file:
            vars_['vertexBoneWeights_file'] = np.fromstring(_properPath(proxy.vertexBoneWeights_file), dtype='S1')

        np.savez_compressed(fp, **vars_)
    os.utime(path, None)  # Ensure modification time is updated

def loadBinaryProxy(path, human, type):
    log.debug("Loading binary proxy %s.", path)

    npzfile = np.load(path)
    #if type is None:
    #    proxyType = npzfile['proxyType'].tostring()
    #else:
    proxyType = type

    proxy = Proxy(path, proxyType, human)

    proxy.name = str(npzfile['name'].tostring(), 'utf8')
    proxy.uuid = str(npzfile['uuid'].tostring(), 'utf8')
    proxy.basemesh = str(npzfile['basemesh'].tostring(), 'utf8')

    if 'description' in npzfile:
        proxy.description = str(npzfile['description'].tostring(), 'utf8')

    if 'version' in npzfile:
        proxy.version = int(npzfile['version'])

    if 'lic_str' in npzfile and 'lic_idx' in npzfile:
        proxy.license.fromNumpyString(npzfile['lic_str'], npzfile['lic_idx'])

    proxy.tags = set(_unpackStringList(npzfile['tags_str'], npzfile['tags_idx']))

    if 'z_depth' in npzfile:
        proxy.z_depth = int(npzfile['z_depth'])

    if 'max_pole' in npzfile:
        proxy.max_pole = int(npzfile['max_pole'])

    if 'special_pose_str' in npzfile:
        special_poses = _unpackStringList(npzfile['special_pose_str'], npzfile['special_pose_idx'])
        for idx in range(0, len(special_poses), 2):
            proxy.special_pose[special_poses[idx]] = special_poses[idx+1]

    num_refverts = int(npzfile['num_refverts'])

    if num_refverts == 3:
        proxy.ref_vIdxs = npzfile['ref_vIdxs']
        proxy.offsets = npzfile['offsets']
        proxy.weights = npzfile['weights']
    else:
        num_refs = npzfile['ref_vIdxs'].shape[0]
        proxy.ref_vIdxs = np.zeros((num_refs,3), dtype=np.uint32)
        proxy.ref_vIdxs[:,0] = npzfile['ref_vIdxs']
        proxy.offsets = np.zeros((num_refs,3), dtype=np.float32)
        proxy.weights = np.zeros((num_refs,3), dtype=np.float32)
        proxy.weights[:,0] = npzfile['weights']

    if "deleteVerts" in npzfile:
        proxy.deleteVerts = npzfile['deleteVerts']

    # Reconstruct reverse vertex (and weights) mapping
    proxy._reloadReverseMapping()

    proxy.tmatrix.fromNumpyStruct(npzfile)

    proxy.uvLayers = {}
    for uvIdx, uvName in enumerate(_unpackStringList(npzfile['uvLayers_str'], npzfile['uvLayers_idx'])):
        proxy.uvLayers[uvIdx] = uvName

    proxy.material = material.Material(proxy.name)
    if 'material_file' in npzfile:
        proxy._material_file = str(npzfile['material_file'].tostring(), 'utf8')
    if proxy.material_file:
        proxy.material.fromFile(proxy.material_file)

    proxy._obj_file = str(npzfile['obj_file'].tostring(), 'utf8')

    if 'vertexBoneWeights_file' in npzfile:
        proxy._vertexBoneWeights_file = str(npzfile['vertexBoneWeights_file'].tostring(), 'utf8')
        if proxy.vertexBoneWeights_file:
            from animation import VertexBoneWeights
            proxy.vertexBoneWeights = VertexBoneWeights.fromFile(proxy.vertexBoneWeights_file)


    if proxy.z_depth == -1:
        log.warning('Proxy file %s does not specify a Z depth. Using 50.', path)
        proxy.z_depth = 50

    return proxy


#
#   class ProxyRefVert:
#

class ProxyRefVert:

    def __init__(self, human):
        self.human = human

    def fromSingle(self, words, vnum, vertWeights):
        # TODO store the number of reference verts in proxy so that we can efficiently save and load them.
        v0 = int(words[0])
        self._verts = (v0,0,1)
        self._weights = (1.0,0.0,0.0)
        self._offset = np.zeros(3, float)
        _addProxyVertWeight(vertWeights, v0, vnum, 1)
        return self

    def fromTriple(self, words, vnum, vertWeights):
        v0 = int(words[0])
        v1 = int(words[1])
        v2 = int(words[2])
        w0 = float(words[3])
        w1 = float(words[4])
        w2 = float(words[5])
        if len(words) > 6:
            d0 = float(words[6])
            d1 = float(words[7])
            d2 = float(words[8])
        else:
            (d0,d1,d2) = (0,0,0)

        self._verts = (v0,v1,v2)
        self._weights = (w0,w1,w2)
        self._offset = np.array((d0,d1,d2), float)

        _addProxyVertWeight(vertWeights, v0, vnum, w0)
        _addProxyVertWeight(vertWeights, v1, vnum, w1)
        _addProxyVertWeight(vertWeights, v2, vnum, w2)
        return self

    def getWeights(self):
        return self._weights

    def getCoord(self, matrix):
        hcoord = self.human.getRestposeCoordinates()
        return (
            np.dot(hcoord[self._verts], self._weights) +
            np.dot(matrix, self._offset)
            )

def _addProxyVertWeight(vertWeights, v, pv, w):
    try:
        vertWeights[v].append((pv, w))
    except KeyError:
        vertWeights[v] = [(pv,w)]
    return

#
#   class TMatrix:
#   Transformation matrix. Replaces previous scale
#

class TMatrix:
    def __init__(self):
        self.scaleData = None
        self.shearData = None
        self.lShearData = None
        self.rShearData = None


    def toNumpyStruct(self, npzfile, prefix=""):
        """Serialize TMatrix in npz file"""
        def _nan_array(size):
            return np.repeat(float('nan'), size).astype(np.float32)

        def _pack_scales(scaleData):
            scales = list()
            vidxs = list()
            for e_idx, entry in enumerate(scaleData):
                # Should be 3 entries
                if entry is None:
                    scales.append(float('nan'))
                    vidxs.extend([0, 0])
                else:
                    vidx1, vidx2, scale = entry
                    scales.append(scale)
                    vidxs.extend([vidx1, vidx2])
            return (np.asarray(scales, dtype=np.float32), 
                    np.asarray(vidxs, dtype=np.uint32))

        def _pack_shears(shearData):
            shears = list()
            vidxs = list()
            for e_idx, entry in enumerate(shearData):
                # Should be 3 entries
                if entry is None:
                    shears.extend([float('nan'), float('nan')])
                    vidxs.extend([0, 0])
                else:
                    vidx1, vidx2, shear1, shear2 = entry
                    shears.extend([shear1, shear2])
                    vidxs.extend([vidx1, vidx2])
            return (np.asarray(shears, dtype=np.float32), 
                    np.asarray(vidxs, dtype=np.uint32))

        if prefix:
            prefix += "_"
        if self.scaleData:
            scales, vidxs = _pack_scales(self.scaleData)
            npzfile[prefix+"tmat_scale"] = scales
            npzfile[prefix+"tmat_scale_idx"] = vidxs
        if self.shearData:
            shears, vidxs = _pack_shears(self.shearData)
            npzfile[prefix+"tmat_shear"] = shears
            npzfile[prefix+"tmat_shear_idx"] = vidxs
        if self.lShearData:
            shears, vidxs = _pack_shears(self.lShearData)
            npzfile[prefix+"tmat_lshear"] = shears
            npzfile[prefix+"tmat_lshear_idx"] = vidxs
        if self.rShearData:
            shears, vidxs = _pack_shears(self.rShearData)
            npzfile[prefix+"tmat_rshear"] = shears
            npzfile[prefix+"tmat_rshear_idx"] = vidxs


    def fromNumpyStruct(self, npzfile, prefix=""):
        """Deserialize TMatrix from npz file"""
        def _unpack_scales(scales, vidxs):
            scaleData = [None, None, None]
            for i in range(3):
                if i >= min(len(scales), len(vidxs)//2):
                    break
                scale = scales[i]
                if not math.isnan(scale):
                    vidx1, vidx2 = vidxs[i*2], vidxs[i*2+1]
                    scaleData[i] = (int(vidx1), int(vidx2), float(scale))
            return scaleData

        def _unpack_shears(shears, vidxs):
            shearData = [None, None, None]
            for i in range(3):
                if i >= min(len(shears)//2, len(vidxs)//2):
                    break
                shear1, shear2 = shears[i*2], shears[i*2+1]
                vidx1, vidx2 = vidxs[i*2], vidxs[i*2+1]
                shearData[i] = (int(vidx1), int(vidx2), float(shear1), float(shear2))
            return shearData

        if prefix:
            prefix += "_"

        if prefix+'tmat_scale' in npzfile and prefix+'tmat_scale_idx' in npzfile:
            scales = npzfile[prefix+'tmat_scale']
            vidxs = npzfile[prefix+'tmat_scale_idx']
            self.scaleData = _unpack_scales(scales, vidxs)
        if prefix+'tmat_shear' in npzfile and prefix+'tmat_shear_idx' in npzfile:
            shears = npzfile[prefix+'tmat_shear']
            vidxs = npzfile[prefix+'tmat_shear_idx']
            self.shearData = _unpack_shears(shears, vidxs)
        if prefix+'tmat_lshear' in npzfile and prefix+'tmat_lshear_idx' in npzfile:
            shears = npzfile[prefix+'tmat_lshear']
            vidxs = npzfile[prefix+'tmat_lshear_idx']
            self.lShearData = _unpack_shears(shears, vidxs)
        if prefix+'tmat_rshear' in npzfile and prefix+'tmat_rshear_idx' in npzfile:
            shears = npzfile[prefix+'tmat_rshear']
            vidxs = npzfile[prefix+'tmat_rshear_idx']
            self.rShearData = _unpack_shears(shears, vidxs)


    def getScaleData(self, words, idx):
        vn1 = int(words[1])
        vn2 = int(words[2])
        den = float(words[3])
        if not self.scaleData:
            self.scaleData = [None, None, None]
        self.scaleData[idx] = (vn1, vn2, den)


    def getShearData(self, words, idx, side):
        vn1 = int(words[1])
        vn2 = int(words[2])
        x1 = float(words[3])
        x2 = float(words[4])
        bbdata = (vn1, vn2, x1, x2)
        if side == "Left":
            if not self.lShearData:
                self.lShearData = [None, None, None]
            self.lShearData[idx] = bbdata
        elif side == "Right":
            if not self.rShearData:
                self.rShearData = [None, None, None]
            self.rShearData[idx] = bbdata
        else:
            if not self.shearData:
                self.shearData = [None, None, None]
            self.shearData[idx] = bbdata


    def getMatrix(self, hcoord):
        if self.scaleData:
            matrix = np.identity(3, float)
            for n in range(3):
                (vn1, vn2, den) = self.scaleData[n]
                co1 = hcoord[vn1]
                co2 = hcoord[vn2]
                num = abs(co1[n] - co2[n])
                matrix[n][n] = (num/den)
            return matrix

        elif self.shearData:
            return self.matrixFromShear(self.shearData, hcoord)
        elif self.lShearData:
            return self.matrixFromShear(self.lShearData, hcoord)
        elif self.rShearData:
            return self.matrixFromShear(self.rShearData, hcoord)
        else:
            return Unit3


    def matrixFromShear(self, shear, hcoord):
        from transformations import affine_matrix_from_points

        # sfaces and tfaces are the face coordinates
        sfaces = np.zeros((3,2), float)
        tfaces = np.zeros((3,2), float)
        for n in range(3):
            (vn1, vn2, sfaces[n,0], sfaces[n,1]) = shear[n]
            tfaces[n,0] = hcoord[vn1][n]
            tfaces[n,1] = hcoord[vn2][n]

        # sverts and tverts are the vertex coordinates
        sverts = []
        tverts = []
        for i in [0,1]:
            for j,k in [(0,0),(0,1),(1,1),(1,0)]:
                sverts.append( np.array((sfaces[0,i], sfaces[1,j], sfaces[2,k])) )
                tverts.append( np.array((tfaces[0,i], tfaces[1,j], tfaces[2,k])) )

        sbox = vertsToNumpy(sverts)
        tbox = vertsToNumpy(tverts)
        mat = affine_matrix_from_points(sbox, tbox)
        return mat[:3,:3]


def vertsToNumpy(verts):
    result = np.asarray(verts)
    return np.asarray([result[:,0], result[:,1], result[:,2]], dtype=np.float32)



def _getFileName(folder, file, suffix):
    (name, ext) = os.path.split(file)
    if ext:
        return os.path.join(folder, file)
    else:
        return os.path.join(folder, file+suffix)


def transferVertexMaskToProxy(vertsMask, proxy):
    """
    Transfer a vertex mask defined on the parent mesh to a proxy using the
    proxy mapping to this parent mesh.
    A vertex mask defines for each vertex if it should be hidden, only faces
    that have all vertices hidden will be hidden.
    True in vertex mask means: show vertex, false means hide (masked)
    """
    # preset new mask to unhidden and calculate all the vertices which depend directly to base mesh
    # (value 1.0, 0.0, 0.0 in weighting), create this mask with negation using np.any
    masksize = len(proxy.ref_vIdxs)
    proxyVertMask = np.ones(masksize, dtype=bool)
    exact_mask = ~np.any(proxy.weights[:,1:], axis=1)

    # now set values according to mask
    for c in range(masksize):
        p = proxy.ref_vIdxs[c]
        if exact_mask[c]:
            proxyVertMask[c] = vertsMask[p[0]]
        else:
            if (int(vertsMask[p[0]]) + int(vertsMask[p[1]]) + int(vertsMask[p[2]])) < 2:
                proxyVertMask[c] = False            # at least two visible Reference

    return proxyVertMask


def getAsciiFileExtension(proxyType):
    """
    The file extension used for ASCII (non-compiled) proxy source files
    for the proxies of specified type.
    """
    return '.proxy' if proxyType == 'Proxymeshes' else '.mhclo'


def peekMetadata(proxyFilePath, proxyType=None):
    """
    Read UUID and tags from proxy file, and return as soon as vertex data
    begins. Reads only the necessary lines of the proxy file from disk, not the
    entire proxy file is loaded in memory.
    """
    #import zipfile
    #if zipfile.is_zipfile(proxyFilePath):
    # Using the filename extension is faster (and will have to do):
    if os.path.splitext(proxyFilePath)[1][1:].lower() == 'mhpxy':
        try:
            if proxyType is not None:
                asciipath = os.path.splitext(proxyFilePath)[0] + getAsciiFileExtension(proxyType)
                if os.path.isfile(asciipath) and os.path.getmtime(asciipath) > os.path.getmtime(proxyFilePath):
                    _npzpath = proxyFilePath
                    proxyFilePath = asciipath
                    raise RuntimeError('compiled file out of date: %s', _npzpath)

            # Binary proxy file
            npzfile = np.load(proxyFilePath)

            uuid = str(npzfile['uuid'].tostring(), 'utf8')
            tags = set(_unpackStringList(npzfile['tags_str'], npzfile['tags_idx']))
            return (uuid, tags)
        except Exception as e:
            showTrace = not isinstance(e, RuntimeError)
            log.warning("Problem loading metadata from binary proxy, trying ASCII file: %s", e, exc_info=showTrace)

    # ASCII proxy file
    with open(proxyFilePath, 'r', encoding="utf-8", errors='ignore') as fp:
        uuid = None
        tags = set()
        for line in fp:
            words = line.split()
            if len(words) == 0:
                pass
            elif words[0] == 'uuid':
                uuid = words[1]
            elif words[0] == 'tag':
                tags.add(" ".join(words[1:]).lower())
            elif words[0] == 'verts':
                break
    return (uuid, tags)


def _packStringList(strings):
    text = ''
    index = []
    for string in strings:
        asbytes = bytearray(text,'utf-8')
        index.append(len(asbytes))
        text += string
    text = np.fromstring(text, dtype='S1')
    index = np.array(index, dtype=np.uint32)
    return text, index

def _unpackStringList(text, index):
    strings = []
    last = None
    for i in index:
        if last is not None:
            name = str(text[last:i].tostring(), 'utf8')
            strings.append(name)
        last = i
    if last is not None:
        name = str(text[last:].tostring(), 'utf8')
        strings.append(name)

    return strings

def _getFilePath(filename, folder = None, altExtensions=None):
    import getpath
    if altExtensions is not None:
        # Search for existing path with alternative file extension
        for aExt in altExtensions:
            if aExt.startswith('.'):
                aExt = aExt[1:]
            aFile = os.path.splitext(filename)[0]+'.'+aExt
            aPath = _getFilePath(aFile, folder, altExtensions=None)
            if os.path.isfile(aPath):
                # Path found, return result with original extension
                orgExt = os.path.splitext(filename)[1]
                path = os.path.splitext(aPath)[0]+orgExt
                return getpath.formatPath(path)

    if not filename or not isinstance(filename, str):
        return filename

    searchPaths = []

    # Search within current folder
    if folder:
        searchPaths.append(folder)

    return getpath.thoroughFindFile(filename, searchPaths)
