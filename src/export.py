from PyQt5.QtWidgets import (QMessageBox)
# from qgis import processing
from qgis.core import QgsProject, QgsVectorLayer, QgsVectorFileWriter
from os import path
class Writer:
    def __init__(self, controller, layer):
        self.layer  = layer
        self.controller = controller
        return None

    def gpkg(self):
        writer = None
        try:
            writer = QgsVectorFileWriter
            filename = path.normpath(f"{self.controller.parent.dockwidget.fieldWorkingDirectory.text()}/{self.layer.name()}.gpkg")
            coordinateTransformContext = QgsProject.instance().transformContext()
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile        
            options.fileEncoding = "UTF-8"
            options.driverName = "GPKG"
            options.layerName = self.layer.name() 

            writer.writeAsVectorFormatV3(
                self.layer,
                filename,
                coordinateTransformContext,
                options
            )
            # layers = [self.layer,]
            # processing.run("native:package", {'LAYERS': layers, 'OUTPUT': filename, 'OVERWRITE': True, 'SAVE_STYLES': False})
            writer = None
            return True
        except Exception:
            QMessageBox.warning(self.controller.parent.dockwidget, "BulkVectorExport",\
                "Failed to export: " + self.layer.name())
            writer = None
            return False
 