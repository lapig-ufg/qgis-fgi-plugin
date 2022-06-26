from qgis.gui import QgsMapTool
from .compat import pointToWGS84
from qgis.core import QgsFeature, QgsGeometry
class ToolPointer(QgsMapTool):
    def __init__(self,iface, layer, inspectionController):
        QgsMapTool.__init__(self,iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer  = layer
        self.inspectionController = inspectionController
        return None

    def canvasReleaseEvent(self,e):
        point = self.canvas.getCoordinateTransform().toMapCoordinates(e.pos().x(), e.pos().y())
        self.layer.startEditing()
        dataProvider = self.layer.dataProvider()
       

        imageDate = self.inspectionController.parent.dockwidget.imageDate.text() 
        if not self.inspectionController.dateIsValid(imageDate):
            imageDate = None

        feat = QgsFeature(self.layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(point))
        (result, newFeatures) = dataProvider.addFeatures([feat])

        fid_idx = self.layer.fields().indexOf('fid')
        class_idx = self.layer.fields().indexOf('class')
        date_idx = self.layer.fields().indexOf('image_date')

        self.layer.changeAttributeValue(newFeatures[0].id(), class_idx, self.inspectionController.parent.selectedClass)
        self.layer.changeAttributeValue(newFeatures[0].id(), date_idx, imageDate)

        self.layer.commitChanges()        
        return None