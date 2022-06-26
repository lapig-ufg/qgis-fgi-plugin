from PyQt5.QtWidgets import (QMessageBox)
from qgis.core import (QgsVectorFileWriter)
from os import path
class Writer:
    def __init__(self, controller, layer):
        self.layer  = layer
        self.controller = controller
        return None

    def gpkg(self):
        filename = path.normpath(f"{self.controller.parent.dockwidget.fieldWorkingDirectory.text()}/{self.layer.name()}.gpkg") 
        options = QgsVectorFileWriter.SaveVectorOptions() 
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer #Update mode
        options.EditionCapability = QgsVectorFileWriter.CanAddNewLayer 
        options.layerName = self.layer.name()  
        crs = self.layer.crs()

        result = QgsVectorFileWriter.writeAsVectorFormat(
            self.layer,
            filename,
            "utf-8",
            crs,
            "gpkg"
        )

        if result[0]:
            QMessageBox.warning(self.controller.parent.dockwidget, "BulkVectorExport",\
                "Failed to export: " + self.layer.name() + \
                " Status: " + str(result))
            return False
        else:
            return True