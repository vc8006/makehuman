#!/usr/bin/python

from .namespace import NameSpace
 
from logging import *
LOG_FORMAT = "[%(asctime)s] [%(filename)s:%(lineno)s - %(funcName)s() ] %(message)s"
# LOG_FORMAT = '%m-%d %H:%M:%S','[%(asctime)s] {%(pathname)s:%(lineno)d} %(funcName)s - %(message)s'
basicConfig(filename="allLogs.log",level = DEBUG,format=LOG_FORMAT)

import log 
class API(NameSpace): 

    def __init__(self,app):
        debug("log")
        self._app = app
        NameSpace.__init__(self)
        self.trace()

        from ._assets import Assets
        self.assets = Assets(self)

        from ._exports import Exports
        self.exports = Exports(self)

        from ._internals import Internals
        self.internals = Internals(self)

        from ._mesh import Mesh
        self.mesh = Mesh(self)

        from ._locations import Locations
        self.locations = Locations(self)

        from ._version import Version
        self.version = Version(self)

        from ._viewport import Viewport
        self.viewport = Viewport(self)

        from ._modifiers import Modifiers
        self.modifiers = Modifiers(self)

        from ._ui import UI
        self.ui = UI(self)

        from ._utility import Utility
        self.utility = Utility(self)
        
        from ._skeleton import Skeleton
        self.skeleton = Skeleton(self)

