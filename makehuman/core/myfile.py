from export import Exporter, ExportConfig
class ObjConfig(ExportConfig):

    def __init__(self):
        print("here at objconfig init")
        ExportConfig.__init__(self)
        self.useRelPaths = True
        self.useNormals = False
        self.hiddenGeom = False


class ExporterOBJ(Exporter):
    def __init__(self):
        Exporter.__init__(self)
        self.name = "Wavefront obj"
        self.filter = "Wavefront (*.obj)"
        self.fileExtension = "obj"
        self.orderPriority = 60.0

    def build(self, options, taskview):
        import gui
        Exporter.build(self, options, taskview)
        self.useNormals = options.addWidget(gui.CheckBox("Normals", False))
        self.hiddenGeom = options.addWidget(gui.CheckBox("Helper geometry", False))

    def export(self, human, filename):

        print("here at myfile export function now will enter to mh2obj_copy")
        print(human)
        from mh2obj_copy import exportObj
        print(filename)


        cfg = self.getConfig()
        cfg.setHuman(human)
        print(cfg,"printing cfg")
        # cfg =  None
        exportObj(filename,cfg)
        print("here ...........")

    def getConfig(self):
        print("here at getconfig")
        cfg = ObjConfig()
        print("here at getconfig 2")
        cfg.useNormals = False

        cfg.feetOnGround      = True
        cfg.scale = 1.0
        cfg.unit    = "decimeter"
        cfg.hiddenGeom        = False

        return cfg
