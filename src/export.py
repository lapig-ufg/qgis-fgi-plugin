from os import path

from PyQt5.QtWidgets import QMessageBox
from qgis import processing
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
)
class Writer:
    def __init__(self, controller, layer, metadata):
        self.layer = layer
        self.controller = controller
        self.metadata = metadata
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cleanup code here
        self.layer = None
        self.controller = None
        self.metadata = None

    def gpkg_by_native_processing(self):
        work_dir = self.controller.parent.dock_widget.fieldWorkingDirectory.text()
        layer_name = self.layer.name()
        filename = path.normpath(f'{work_dir}/{layer_name}.gpkg')

        # Create the parameters dictionary for the 'native:savefeatures' algorithm
        params = {
            'INPUT': self.layer,
            'OUTPUT': filename,
            'FILE_ENCODING': 'UTF-8',
            'LAYER_NAME': layer_name,
            'LAYER_OPTIONS': self.metadata  # Ensure that this metadata is correctly formatted for the processing tool
        }

        try:
            # Run the save features algorithm
            processing.run("native:savefeatures", params)

            message = f'The gpkg file of tile {layer_name} was generated successfully and can be found on path {filename}'
            self.controller.parent.iface.messageBar().pushMessage('EXPORT GPKG', message, level=Qgis.Info, duration=30)

            return True
        except Exception as e:
            QMessageBox.warning(
                self.controller.parent.dock_widget,
                'BulkVectorExport',
                f'Failed to export: {layer_name}. Error: {str(e)}',
            )
            return False

    def gpkg(self):
        # Avoid repeated calls by storing the values
        work_dir = self.controller.parent.dock_widget.fieldWorkingDirectory.text()
        layer_name = self.layer.name()

        # Construct filename
        filename = path.normpath(f'{work_dir}/{layer_name}.gpkg')

        # Set options for the writer
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        options.fileEncoding = 'UTF-8'
        options.driverName = 'GPKG'
        options.layerName = layer_name
        options.layerOptions = self.metadata

        # Try writing the file
        try:
            QgsVectorFileWriter.writeAsVectorFormatV3(
                self.layer,
                filename,
                QgsProject.instance().transformContext(),
                options
            )

            # Notify success
            message = f'The gpkg file of tile {layer_name} was generated successfully and can be found on path {filename}'
            self.controller.parent.iface.messageBar().pushMessage('EXPORT GPKG', message, level=Qgis.Info, duration=30)
            return True
        except Exception:
            QMessageBox.warning(
                self.controller.parent.dock_widget,
                'BulkVectorExport',
                'Failed to export: ' + layer_name,
            )
            return False