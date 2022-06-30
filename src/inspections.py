import datetime
import time
from os import path, remove
from glob import glob
from PyQt5.QtWidgets import QPushButton, QProgressBar
from qgis.PyQt.QtCore import QVariant
from PyQt5 import QtCore
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.core import Qgis, QgsWkbTypes, QgsProject, QgsVectorLayer, QgsSymbol, QgsRuleBasedRenderer, QgsFillSymbol, QgsProcessingFeedback, QgsRectangle, QgsField, QgsFeatureRequest
from qgis import processing
from .tools import ToolPointer, ClipboardPointer
from .export import Writer
class InspectionController:
    """QGIS Plugin Implementation."""

    def __init__(self, parent):
        self.parent = parent
        self.selectedClassObject = None
        self.livestockLayer = None
        self.parent.dockwidget.btnNext.clicked.connect(self.nextTile)
        # self.parent.dockwidget.btnBack.clicked.connect(self.backtTile)
        self.parent.dockwidget.btnPointDate.clicked.connect(self.getPoint)
        
    
    def getPoint(self):
        canvas = self.parent.iface.mapCanvas()
        tool = ClipboardPointer(self.parent.iface, self)
        canvas.setMapTool(tool)
       
            
    def setFeatureColor(self):
        # symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'#404040','width_border':'0.1'})
        symbol = QgsSymbol.defaultSymbol(self.parent.currentPixelsLayer.geometryType())
        renderer = QgsRuleBasedRenderer(symbol)
        
        rules = []

        for type in self.parent.typeInspection['classes']:
            rgb = type['rgb'].split(",")
            rules.append([type['class'], f""""class" = '{type['class']}'""", QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3]))])

        rules.append(["NOT DEFINED", f""""class" is NULL""", QColor(0, 0, 255, 0)])

        def rule_based_symbology(layer, renderer, label, expression, symbol, color):
            root_rule = renderer.rootRule()
            rule = root_rule.children()[0].clone()
            rule.setLabel(label)
            rule.setFilterExpression(expression)
            rule.symbol().setColor(QColor(color))
            root_rule.appendChild(rule)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

        for rule in rules:
            rule_based_symbology(self.parent.currentPixelsLayer, renderer, rule[0], rule[1], symbol, rule[2])

        renderer.rootRule().removeChildAt(0)
        self.parent.iface.layerTreeView().refreshLayerSymbology(self.parent.currentPixelsLayer.id())

    def dateIsValid(self, date_text):
            try:
                datetime.datetime.strptime(date_text, '%Y-%m-%d')
                return True
            except ValueError:
               return False

    def getFeature(self, featureId):
        feature = None
        allFeatures = self.parent.currentPixelsLayer.getFeatures();
        for feat in allFeatures:
            if(feat.id() == featureId): 
                feature = feat
        return feature

    def addClassToFeature(self, selectedFeatures):
        request = QgsFeatureRequest()
        request.setFilterFids(selectedFeatures)
        rgb = self.selectedClassObject['rgb'].split(",")
        self.parent.iface.mapCanvas().setSelectionColor( QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), 135) )
        allFeatures = self.parent.currentPixelsLayer.getFeatures(request);
        class_idx = self.parent.currentPixelsLayer.fields().indexOf('class')
        date_idx = self.parent.currentPixelsLayer.fields().indexOf('image_date')
        imageDate = self.parent.dockwidget.imageDate.text()
       
        if not self.dateIsValid(imageDate):
            imageDate = None
            self.parent.iface.messageBar().pushMessage("", "The image date valid is required!", level=Qgis.Critical, duration=5)
            return
       
        self.parent.currentPixelsLayer.startEditing()
        
        if not self.parent.selectedClass:
            imageDate = None  

        for feature in allFeatures:
            self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), class_idx, self.parent.selectedClass)
            self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), date_idx, imageDate)
        
        self.parent.currentPixelsLayer.commitChanges()
        self.setFeatureColor()

    def createPointsLayer(self, tile):
        uri = "point?crs=epsg:3857"
        self.livestockLayer = QgsVectorLayer(uri, f"{tile[0]}_{self.parent.typeInspection['_id']}", "memory")
        pr = self.livestockLayer.dataProvider()
        # Enter editing mode
        self.livestockLayer.startEditing()
        pr.addAttributes( [ QgsField("class", QVariant.String), QgsField("image_date",  QVariant.String) ] )
        self.livestockLayer.commitChanges()
        
        request = QgsFeatureRequest().setFilterFids([tile[0]])
        tilesFeatures = list(self.parent.tilesLayer.getFeatures(request))
        geom = tilesFeatures[0].geometry()
        zoomRectangle = QgsRectangle(geom.boundingBox())
        
        QgsProject().instance().addMapLayer(self.livestockLayer)
        self.parent.canvas.setExtent(zoomRectangle)
    
    def setDefaultClass(self, layer):
        imageDate = self.parent.dockwidget.imageDate.text() 
        if not self.dateIsValid(imageDate):
            imageDate = None

        layer.startEditing()
        allFeatures = layer.getFeatures();
        class_idx = layer.fields().indexOf('class')
        date_idx = layer.fields().indexOf('image_date')
        for feature in allFeatures:
            layer.changeAttributeValue(feature.id(), class_idx, self.parent.selectedClass)
            layer.changeAttributeValue(feature.id(), date_idx, imageDate)
        layer.commitChanges()

    def createGridPixels(self, tile):
        self.parent.currentPixelsLayer = None
        # self.parent.iface.messageBar().clearWidgets()
        # progressMessageBar = self.parent.iface.messageBar()
        # progressbar = QProgressBar()
        # progressbar.setMaximum(100) 
        # progressMessageBar.pushWidget(progressbar)

        # def onProgress(progress):
        #     progressbar.setValue(progress) 

        # feedback = QgsProcessingFeedback()
        # feedback.progressChanged.connect(onProgress)

        request = QgsFeatureRequest().setFilterFids([tile[0]])
        tilesFeatures = list(self.parent.tilesLayer.getFeatures(request))
        geom = tilesFeatures[0].geometry()
         
        cellsize = 10 #Cell Size in EPSG:3857 will be 10 x 10 meters
        # extent = str(tile[2])+ ',' + str(tile[4])+ ',' +str(tile[3])+ ',' +str(tile[5])  
        extent = geom.boundingBox()
        params = {'TYPE':2,
            'EXTENT': extent,
            'HSPACING':cellsize,
            'VSPACING':cellsize,
            'HOVERLAY':0,
            'VOVERLAY':0,
            'CRS':"EPSG:3857",
            'OUTPUT':'memory'}
        out = processing.run('native:creategrid', params)
        # self.parent.iface.messageBar().clearWidgets()
        
        grid = QgsVectorLayer(out['OUTPUT'], f"{tile[0]}_{self.parent.typeInspection['_id']}", 'ogr')
        symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'#404040','width_border':'0.1'})
        grid.renderer().setSymbol(symbol)
        dataProvider = grid.dataProvider()
        # Enter editing mode
        grid.startEditing()

        # add fields
        dataProvider.addAttributes( [ QgsField("class", QVariant.String), QgsField("image_date",  QVariant.String) ] )

        allFeatures = grid.getFeatures();
        field_idx = grid.fields().indexOf('class')
        for feature in allFeatures:
            grid.changeAttributeValue(feature.id(), field_idx, self.parent.selectedClass)

        grid.commitChanges()

        # self.setDefaultClass(grid)
    
        self.parent.currentPixelsLayer = grid
        QgsProject().instance().addMapLayer(grid)

        self.parent.iface.setActiveLayer(grid);
        self.parent.iface.zoomToActiveLayer();
        
        grid.selectionChanged.connect(self.addClassToFeature)
        self.setFeatureColor()

    def clearButtons(self, layout):
        for i in reversed(range(layout.count())): 
            layout.itemAt(i).widget().setParent(None)
   
    def removeSelection(self):
        self.parent.selectedClass = None
        if( self.selectedClassObject['type'] == 'point'):
            # Taken clicked point and add as cattle in the layer 
            canvas = self.parent.iface.mapCanvas()
            tool = ToolPointer(self.parent.iface, self.livestockLayer, self)
            canvas.setMapTool(tool)
        else: 
            self.parent.iface.actionSelectFreehand().trigger() 

    def onClickClass(self, item):
        """Write config in config file"""
        imageDate = self.parent.dockwidget.imageDate.text()
        if (self.dateIsValid(imageDate)):
            self.parent.dockwidget.selectedClass.setText(f"Selected class:  {item['class'].upper()}")
            self.parent.dockwidget.selectedClass.setStyleSheet(f"background-color: {item['color']}; border-radius :5px; padding :5px")
            self.parent.selectedClass = item['class'].upper()
            self.selectedClassObject = item
            if(item['type'] == 'point'):
                # Taken clicked point and add as cattle in the layer 
                canvas = self.parent.iface.mapCanvas()
                tool = ToolPointer(self.parent.iface, self.livestockLayer, self)
                canvas.setMapTool(tool)
            else: 
                self.parent.iface.actionSelectFreehand().trigger() 
        else:
            self.parent.iface.messageBar().pushMessage("", f"The image date valid is required!", level=Qgis.Critical, duration=5)    
    
    def initInspectionTile(self, noImageDate=False):
        """Load all class of type inspection"""
        self.clearButtons(self.parent.dockwidget.layoutClasses)

        if not noImageDate:
            # self.parent.dockwidget.btnBack.setEnabled(True)
            self.parent.dockwidget.btnNext.setEnabled(True)
        else: 
            self.nextTile(noImageDate)
            return
         
        for type in self.parent.typeInspection['classes']:
            if(type['selected']):
                self.onClickClass(type)

            if not noImageDate:
                button = QPushButton(type['class'].upper(), checkable=True)
                button.setStyleSheet(f"background-color: {type['color']}")
                button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
                button.clicked.connect(lambda checked, value = type : self.onClickClass(value))
                self.parent.dockwidget.layoutClasses.addWidget(button)
        self.parent.dockwidget.btnClearSelection.setVisible(True)

    def clearContainerClasses(self, finished=False):
        self.parent.dockwidget.labelClass.setVisible(False)
        self.parent.dockwidget.selectedClass.setVisible(False)
        self.parent.dockwidget.btnLoadClasses.setVisible(False)
        self.parent.dockwidget.btnClearSelection.setVisible(False)
        self.clearButtons(self.parent.dockwidget.layoutClasses)
        # self.parent.dockwidget.btnBack.setEnabled(False)
        # self.parent.dockwidget.btnNext.setEnabled(False)
        self.parent.dockwidget.imageDate.setText("")

        if(finished):
            self.parent.dockwidget.btnNext.setVisible(False)
            self.parent.dockwidget.btnPointDate.setVisible(False)
            self.parent.dockwidget.labelImageDate.setVisible(False)
            self.parent.dockwidget.imageDate.setVisible(False)
            self.parent.dockwidget.btnLoadClasses.setVisible(False)

        for i in reversed(range(self.parent.dockwidget.layoutClasses.count())): 
            self.parent.dockwidget.layoutClasses.itemAt(i).widget().setParent(None)

    def layerIsEmpty(self, layer):
        request = QgsFeatureRequest().setFilterExpression(' "class" is NULL AND "image_date" is NULL ')
        resultFeatures = layer.getFeatures(request);

        if(layer.featureCount() == len(list(resultFeatures))):
            return True
        else:
            return False

    def tileMissingDate(self, tile):
        # Enter editing mode
        self.parent.tilesLayer.startEditing()
        request = QgsFeatureRequest()
        request.setFilterFids([tile[0]])
        allFeatures = self.parent.tilesLayer.getFeatures(request);
        has_image_date_idx = self.parent.tilesLayer.fields().indexOf('missing_image_date')
        for feature in allFeatures:
            self.parent.tilesLayer.changeAttributeValue(feature.id(), has_image_date_idx, 1)

        self.parent.tilesLayer.commitChanges()
    
    def sendInspections(self):
        workingDirectory = self.parent.getConfig('workingDirectory')
      
        # layer.saveSldStyle(path.join(workingDirectory, f"{self.parent.typeInspection['_id']}.sld"))
        # types = (path.join(workingDirectory, f"*_{self.parent.typeInspection['_id']}.gpkg"), f"*_{self.parent.typeInspection['_id']}.sld")
        files = glob(path.join(workingDirectory, f"*_{self.parent.typeInspection['_id']}.gpkg"))

        print(files)



    def nextTile(self, noImageDate=False):
        layer = None
        index = self.parent.currentTileIndex + 1

        if( self.parent.geometryType == 'point'): 
            layer = self.livestockLayer
        else: 
            layer = self.parent.currentPixelsLayer

        tilesLength = len(self.parent.tiles)

        if(not noImageDate and self.layerIsEmpty(layer) and layer.wkbType() == QgsWkbTypes.Polygon):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("The image date is required to classify this tile!")
            msg.setInformativeText("If the image date was not found, the tile would be ignored. Do you confirm the missing date of the image?")
            msg.setWindowTitle("INSPECTION TILES")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            retval = msg.exec_()
            if (retval == 16384):
                self.initInspectionTile(noImageDate=True)
                return

        if( index <= tilesLength):
            if not noImageDate:
                result =  Writer(self, layer).gpkg()
                if(result and (index < tilesLength)):
                    self.parent.currentTileIndex = index
                    self.parent.setConfig(key='currentTileIndex', value= index)
                    QgsProject.instance().removeMapLayer(layer.id())
                    self.parent.configTiles()
            else:
                self.tileMissingDate(self.parent.tiles[self.parent.currentTileIndex])
                if(index < tilesLength):
                    self.parent.currentTileIndex = index
                    self.parent.setConfig(key='currentTileIndex', value= index)
                    QgsProject.instance().removeMapLayer(layer.id())
                    self.parent.configTiles()

            self.clearContainerClasses()

        if(index == tilesLength):
            self.parent.iface.messageBar().pushMessage("", "Inspection FINISHED!", level=Qgis.Info, duration=15)
            self.clearContainerClasses(finished=True)
            self.parent.dockwidget.tileInfo.setText(f"INSPECTION FINISHED!")

            time.sleep(6)
            self.parent.onClosePlugin();
            remove(self.parent.workDir + 'config.json')
            
            # button = QPushButton("Send Inpections to Drive", checkable=True)
            # button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
            # button.clicked.connect(self.sendInspections)
            # self.parent.dockwidget.layoutClasses.addWidget(button)

            # TODO compilado dos arquivos e enviar para o drive do LAPIG
     
        self.selectedClassObject = None
        self.parent.currentPixelsLayer = None
        self.livestockLayer = None

    def loadTileFromFile(self, tile):
        self.parent.currentPixelsLayer = None
        self.livestockLayer = None
        
        self.initInspectionTile()
        
        filename = path.normpath(f"{self.parent.dockwidget.fieldWorkingDirectory.text()}/{tile[0]}_{self.parent.typeInspection['_id']}.gpkg") 
        layer = QgsVectorLayer(filename, f"{tile[0]}_{self.parent.typeInspection['_id']}", 'ogr')

        if( layer.wkbType() == QgsWkbTypes.Point): 
            self.livestockLayer = layer
        else:
            symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'#404040','width_border':'0.1'})
            layer.renderer().setSymbol(symbol)
            self.parent.currentPixelsLayer = layer
            self.setFeatureColor()

        QgsProject().instance().addMapLayer(layer)
        self.parent.iface.setActiveLayer(layer);
        self.parent.iface.zoomToActiveLayer();
        self.clearContainerClasses()

    def backtTile(self):
        layer = None
        index = self.parent.currentTileIndex - 1
        if(self.selectedClassObject):

            if( self.parent.geometryType == 'point'): 
                layer = self.livestockLayer
            else:
                layer = self.parent.currentPixelsLayer

            if( index >= 0 ):
                self.parent.currentTileIndex = index
                self.parent.setConfig(key='currentTileIndex', value=self.parent.currentTileIndex)
                QgsProject.instance().removeMapLayer(layer.id())
                self.clearContainerClasses()
                self.parent.configTiles()
        else: 
            self.parent.iface.messageBar().pushMessage("", "The selection of class is required", level=Qgis.Warning, duration=5)
            

