import datetime
from PyQt5.QtWidgets import QPushButton, QProgressBar
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsProject, QgsVectorLayer, QgsSymbol, QgsRuleBasedRenderer, QgsFillSymbol, QgsProcessingFeedback, QgsRectangle, QgsField, QgsFeatureRequest
from qgis import processing
from .point import ToolPointer
from .export import Writer
class InspectionController:
    """QGIS Plugin Implementation."""

    def __init__(self, parent):
        self.parent = parent
        self.selectedClassObject = None
        self.livestockLayer = None
        self.parent.dockwidget.btnNext.clicked.connect(self.nextTile)
        self.parent.dockwidget.btnBack.clicked.connect(self.nextTile)
        
    
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
       
        self.parent.currentPixelsLayer.startEditing()    
        for feature in allFeatures:
            self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), class_idx, self.parent.selectedClass)
            self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), date_idx, imageDate)
        
        self.parent.currentPixelsLayer.commitChanges()
        self.setFeatureColor()

    def createPointsLayer(self, tile):
        uri = "point?crs=epsg:3857"
        self.livestockLayer = QgsVectorLayer(uri, f"{tile[0]}_livestock", "memory")
        pr = self.livestockLayer.dataProvider()
        # Enter editing mode
        self.livestockLayer.startEditing()
        pr.addAttributes( [ QgsField("class", QVariant.String), QgsField("image_date",  QVariant.String) ] )
        self.livestockLayer.commitChanges()
        zoomRectangle = QgsRectangle(tile[2], tile[3], tile[4], tile[5])
        # Taken clicked point and add as cattle in the layer 
        canvas = self.parent.iface.mapCanvas()
        tool = ToolPointer(self.parent.iface, self.livestockLayer, self)
        canvas.setMapTool(tool)

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
        self.parent.iface.messageBar().clearWidgets()
        progressMessageBar = self.parent.iface.messageBar()
        progressbar = QProgressBar()
        progressbar.setMaximum(100) 
        progressMessageBar.pushWidget(progressbar)

        def onProgress(progress):
            progressbar.setValue(progress) 

        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(onProgress)

        cellsize = 10 #Cell Size in EPSG:3857 will be 10 x 10 meters
        extent = str(tile[2])+ ',' + str(tile[4])+ ',' +str(tile[3])+ ',' +str(tile[5])  
        params = {'TYPE':2,
            'EXTENT': extent,
            'HSPACING':cellsize,
            'VSPACING':cellsize,
            'HOVERLAY':0,
            'VOVERLAY':0,
            'CRS':"EPSG:3857",
            'OUTPUT':'memory'}
        out = processing.run('native:creategrid', params)
        self.parent.iface.messageBar().clearWidgets()

        grid = QgsVectorLayer(out['OUTPUT'], f"{tile[0]}_pasture", 'ogr')
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

    def onClickClass(self, item):
        """Write config in config file"""
        self.parent.dockwidget.selectedClass.setText(f"Selected class:  {item['class'].upper()}")
        self.parent.dockwidget.selectedClass.setStyleSheet(f"background-color: {item['color']}; border-radius :5px; padding :5px")
        self.parent.selectedClass = item['class'].upper()
        self.selectedClassObject = item

        if(item['type'] == 'pasture'):
            self.parent.iface.actionSelectFreehand().trigger()
    
    def initInspectionTile(self):
        """Load all class of type inspection"""
        self.clearButtons(self.parent.dockwidget.layoutClasses)
        for type in self.parent.typeInspection['classes']:
            if(type['selected']):
                self.onClickClass(type) 
            
            button = QPushButton(type['class'].upper(), checkable=True)
            button.setStyleSheet(f"background-color: {type['color']}")
            button.clicked.connect(lambda checked, value = type : self.onClickClass(value))
            self.parent.dockwidget.layoutClasses.addWidget(button)

    def nextTile(self):
        layer = None
      
        if( self.selectedClassObject['type'] == 'livestock'): 
            layer = self.livestockLayer
        else: 
            layer = self.parent.currentPixelsLayer
        
        result =  Writer(self, layer).gpkg()

        if(result):
            self.parent.currentTileIndex = self.parent.currentTileIndex + 1
            self.parent.setConfig(key='currentTileIndex', value=self.parent.currentTileIndex)
            QgsProject.instance().removeMapLayers( [layer.id()] )
            self.parent.configTiles()

    def backtTile(self):
        layer = None
      
        if( self.selectedClassObject['type'] == 'livestock'): 
            layer = self.livestockLayer
        else: 
            layer = self.parent.currentPixelsLayer

        if( self.parent.currentTileIndex >= 0 ):
            self.parent.currentTileIndex = self.parent.currentTileIndex - 1
            self.parent.setConfig(key='currentTileIndex', value=self.parent.currentTileIndex)
            QgsProject.instance().removeMapLayers( [layer.id()] )

