from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
)
from qgis.gui import QgsMapTool
from qgis.PyQt.QtWidgets import QApplication


class ToolPointer(QgsMapTool):
    def __init__(self, iface, layer, inspectionController):
        QgsMapTool.__init__(self, iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer = layer
        self.inspectionController = inspectionController
        return None

    def canvasReleaseEvent(self, e):
        point = self.canvas.getCoordinateTransform().toMapCoordinates(
            e.pos().x(), e.pos().y()
        )
        self.layer.startEditing()
        dataProvider = self.layer.dataProvider()
        imageDate = (
            self.inspectionController.parent.dockwidget.imageDate.text()
        )
        if not self.inspectionController.date_is_valid(imageDate):
            imageDate = None

        feat = QgsFeature(self.layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(point))
        (result, newFeatures) = dataProvider.addFeatures([feat])

        class_idx = self.layer.fields().indexOf('class')
        date_idx = self.layer.fields().indexOf('image_date')

        self.layer.changeAttributeValue(
            newFeatures[0].id(),
            class_idx,
            self.inspectionController.parent.selectedClass,
        )
        self.layer.changeAttributeValue(
            newFeatures[0].id(), date_idx, imageDate
        )

        self.layer.commitChanges()
        return None


class ClipboardPointer(QgsMapTool):
    def __init__(self, iface, controller):
        QgsMapTool.__init__(self, iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.controller = controller
        return None

    def canvasReleaseEvent(self, e):
        point = self.canvas.getCoordinateTransform().toMapCoordinates(
            e.pos().x(), e.pos().y()
        )
        sourceCrs = QgsCoordinateReferenceSystem(3857)
        destCrs = QgsCoordinateReferenceSystem(4326)
        tr = QgsCoordinateTransform(sourceCrs, destCrs, QgsProject.instance())
        clipboardPoint = tr.transform(point)
        clipboard = QApplication.clipboard()
        clipboard.setText(f'{clipboardPoint.y()},{clipboardPoint.x()}')
        self.iface.messageBar().pushMessage(
            'POINT COORDINATE',
            f'The coordinate {clipboardPoint.y()}, {clipboardPoint.x()} copied to the clipboard',
            level=Qgis.Info,
            duration=5,
        )
        self.controller.parent.dockwidget.btnLoadClasses.setVisible(True)
        return None
