import datetime
import time
import json
from sys import platform
from os import path, remove
from glob import glob
import requests as req
from requests.utils import requote_uri
import urllib
from PyQt5.QtWidgets import QPushButton
from qgis.PyQt.QtCore import QVariant
from PyQt5 import QtCore
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.PyQt.QtGui import QColor, QCursor, QPixmap
from qgis.core import Qgis, QgsCoordinateTransform, QgsProject, QgsVectorLayer, QgsSymbol, QgsRuleBasedRenderer, QgsFillSymbol, QgsCoordinateReferenceSystem, QgsField, QgsFeatureRequest
from qgis import processing

from .tools import ToolPointer, ClipboardPointer
from .export import Writer
from .models.dependencies.xmltodict import xmltodict
import unicodedata
class InspectionController:
    """QGIS Plugin Implementation."""

    def __init__(self, parent):
        self.parent = parent
        self.selectedClassObject = None
        self.livestockLayer = None
        self.inspectionStartDatetime = None
        self.tileGeom = None
        self.bingThumUrl = None
        self.inspecting = False
        self.parent.dockwidget.btnNext.clicked.connect(self.nextTile)
        # self.parent.dockwidget.btnBack.clicked.connect(self.backtTile)
        self.parent.dockwidget.btnPointDate.clicked.connect(self.getPoint)
        
    def dialog(self, title, text, info, type):
        obType = None

        if(type == 'Critical'):
            obType = QMessageBox.Critical
        elif(type == 'Information'):
            obType = QMessageBox.Information
        elif(type == 'Question'):
            obType = QMessageBox.Question
        elif(type == 'Warning'):
            obType = QMessageBox.Warning
            
        msg = QMessageBox()
        msg.setIcon(obType)
        msg.setText(text)

        if(info):
            msg.setInformativeText(info)

        msg.setWindowTitle(title)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return msg.exec_()

    def getWidgetObject(self, widget):
        widgetObject = None

        if self.parent.getConfig('imageSource') == 'BING':
            widgetObject = getattr(self.parent.dockwidget, f'{widget}Bing')
        else:
            widgetObject = getattr(self.parent.dockwidget, f'{widget}Google')

        return widgetObject

    def getPoint(self):
        canvas = self.parent.iface.mapCanvas()
        tool = ClipboardPointer(self.parent.iface, self)
        canvas.setMapTool(tool)
       
    def normalize(self, text):
        text = (
            unicodedata.normalize('NFD', text)
            .encode('ascii', 'ignore')
            .decode('utf-8')
        )
        return str(text).lower().replace(" ", "_")

    def setFeatureColor(self):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        # symbol = QgsSymbol.defaultSymbol(self.parent.currentPixelsLayer.geometryType())
        symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'black','width_border':'0.1'})
        renderer = QgsRuleBasedRenderer(symbol)
        rules = []
              
        
        for type in self.parent.campaignsConfig['classes']:
            rgb = type['rgb'].split(",")
            if self.parent.getConfig('imageSource') == 'BING':
                rules.append([type['class'], f""""bing_class" = '{type['class']}'""", QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3]))])
            else:
                rules.append([type['class'], f""""google_class" = '{type['class']}'""", QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3]))])

        if self.parent.getConfig('imageSource') == 'BING':
            rules.append(["NOT DEFINED", f""""bing_class" is NULL""", QColor(0, 0, 255, 0)])
        else:
            rules.append(["NOT DEFINED", f""""google_class" is NULL""", QColor(0, 0, 255, 0)])

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
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def dateIsValid(self, date_text):
            try:
                date = datetime.datetime.strptime(date_text, '%Y-%m-%d')
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

    def removePoints(self, selectedFeatures):
        request = QgsFeatureRequest()
        request.setFilterFids(selectedFeatures)
        allFeatures = list(self.livestockLayer.getFeatures(request));
    
        self.livestockLayer.startEditing()
      
        for feature in allFeatures:
            self.livestockLayer.deleteFeature(feature.id())
         
        self.livestockLayer.commitChanges()
        canvas = self.parent.iface.mapCanvas()
        tool = ToolPointer(self.parent.iface, self.livestockLayer, self)
        canvas.setMapTool(tool)

    def addClassToFeature(self, selectedFeatures):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        request = QgsFeatureRequest()
        request.setFilterFids(selectedFeatures)

        if self.parent.selectedClass is None:
           self.parent.iface.mapCanvas().setSelectionColor( QColor(255, 255, 255, 0) )

        else: 
            rgb = self.selectedClassObject['rgb'].split(",")
            self.parent.iface.mapCanvas().setSelectionColor( QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(rgb[3])) )

        if(self.parent.currentPixelsLayer):
        
            allFeatures = list(self.parent.currentPixelsLayer.getFeatures(request));
            google_class_idx = self.parent.currentPixelsLayer.fields().indexOf('google_class')
            google_image_start_date_idx = self.parent.currentPixelsLayer.fields().indexOf('google_image_start_date')
            google_image_end_date_idx = self.parent.currentPixelsLayer.fields().indexOf('google_image_end_date')
            
            bing_class_idx = self.parent.currentPixelsLayer.fields().indexOf('bing_class')
            bing_image_start_date_idx = self.parent.currentPixelsLayer.fields().indexOf('bing_image_start_date')
            bing_image_end_date_idx = self.parent.currentPixelsLayer.fields().indexOf('bing_image_end_date')
     
            imageDate = self.parent.dockwidget.imageDate.date().toString('yyyy-MM-dd')

            imageBindStartDate = self.parent.dockwidget.bingStartDate.date().toString('yyyy-MM-dd')
            imageBindEndDate  = self.parent.dockwidget.bingEndDate.date().toString('yyyy-MM-dd')

            if self.parent.getConfig('imageSource') == 'BING':
                if not self.dateIsValid(imageBindStartDate) and not self.dateIsValid(imageBindEndDate):
                    imageDate = None
                    self.parent.iface.messageBar().pushMessage("", "The image date of Bing valid is required!", level=Qgis.Critical, duration=5)
                    return
            else:
                if not self.dateIsValid(imageDate):
                    imageDate = None
                    self.parent.iface.messageBar().pushMessage("", "The image date of Google valid is required!", level=Qgis.Critical, duration=5)
                    return

  
            self.parent.currentPixelsLayer.startEditing()
            
            if not self.parent.selectedClass:
                imageDate = None  

            for feature in allFeatures:
                if self.parent.getConfig('imageSource') == 'BING':
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), bing_class_idx, self.parent.selectedClass)
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), bing_image_start_date_idx, imageBindStartDate)
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), bing_image_end_date_idx, imageBindEndDate)
                else:
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), google_class_idx, self.parent.selectedClass)
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), google_image_start_date_idx, imageDate)
                    self.parent.currentPixelsLayer.changeAttributeValue(feature.id(), google_image_end_date_idx, imageDate)
           

            self.parent.currentPixelsLayer.commitChanges()
            self.setFeatureColor()
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
        else:
           self.parent.iface.messageBar().pushMessage("", "Something went wrong with the pixels layer, Please close the plugin and try again", level=Qgis.Critical, duration=10)
                  
    def setDefaultClass(self, layer):
        imageDate = self.parent.dockwidget.imageDate.date().toString('yyyy-MM-dd')
        if not self.dateIsValid(imageDate):
            imageDate = None

        layer.startEditing()
        allFeatures = layer.getFeatures();
        google_class_idx = layer.fields().indexOf('google_class')
        google_image_start_date_idx = layer.fields().indexOf('google_image_start_date')
        google_image_end_date_idx = layer.fields().indexOf('google_image_end_date')

        bing_class_idx = layer.fields().indexOf('bing_class')
        bing_image_start_date_idx = layer.fields().indexOf('bing_image_start_date')
        bing_image_end_date_idx = layer.fields().indexOf('bing_image_end_date')

        imageDate = self.parent.dockwidget.imageDate.date().toString('yyyy-MM-dd')

        imageBindStartDate = self.parent.dockwidget.bingStartDate.date().toString('yyyy-MM-dd')
        imageBindEndDate  = self.parent.dockwidget.bingEndDate.date().toString('yyyy-MM-dd')

        for feature in allFeatures:
            if self.parent.getConfig('imageSource') == 'BING':
                layer.changeAttributeValue(feature.id(), bing_class_idx, self.parent.selectedClass)
                layer.changeAttributeValue(feature.id(), bing_image_start_date_idx, imageBindStartDate)
                layer.changeAttributeValue(feature.id(), bing_image_end_date_idx, imageBindEndDate) 
            else: 

                layer.changeAttributeValue(feature.id(), google_class_idx, self.parent.selectedClass)
                layer.changeAttributeValue(feature.id(), google_image_start_date_idx, imageDate)
                layer.changeAttributeValue(feature.id(), google_image_end_date_idx, imageDate)

        layer.commitChanges()

    def loadThumbnailBing(self, url): 
        data = urllib.request.urlopen(url).read()
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.getWidgetObject('thum').setPixmap(pixmap)

    def loadTileMetadataFromBing(self, geom):
        sourceCrs = QgsCoordinateReferenceSystem(3857)
        destCrs = QgsCoordinateReferenceSystem(4326)

        tr = QgsCoordinateTransform(sourceCrs, destCrs, QgsProject.instance())
        point = tr.transform(geom.centroid().asPoint()).toString().split(',')

        lat = point[1].replace(' ', '')
        lon = point[0].replace(' ', '')
       
        
        url = requote_uri(f"https://dev.virtualearth.net/REST/V1/Imagery/Metadata/Aerial/{lat},{lon}?centerPoint={lat},{lon}&zl=15&o=xml&key=AlXOiUXLu-4TbJpayRnVBURzY6RNXLLlK-STT2JIzBrkbXe0-53aSfaQXfDA7rt6")
        data = urllib.request.urlopen(url).read()
        
        metadataBing = xmltodict.parse(data)
        metadataBing = metadataBing.pop('Response').get('ResourceSets').get('ResourceSet').get('Resources').get('ImageryMetadata')

        start_date = metadataBing.get('VintageStart')
        end_date = metadataBing.get('VintageEnd')

        dateStart = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        dateEnd = datetime.datetime.strptime(end_date, "%Y-%m-%d")

        period = dateEnd - dateStart

        self.loadThumbnailBing(metadataBing.get('ImageUrl'))
        self.bingThumUrl = metadataBing.get('ImageUrl')

        self.parent.dockwidget.bingStartDate.setDateTime(dateStart)
        self.parent.dockwidget.bingEndDate.setDateTime(dateEnd)

        self.parent.dockwidget.bingPeriod.setText(str(period.days))

 
    def createGridPixels(self, tile):
        self.tileGeom = None
        grid = None
        out = None
        self.parent.currentPixelsLayer = None
        self.inspectionStartDatetime = datetime.datetime.now()
        name = self.parent.getConfig('interpreterName')
        self.inspecting = True

        if name is "":
            name = self.parent.dockwidget.interpreterName.text()
        
        self.interpreterName = self.normalize(name)
        
        gridOutput = path.normpath(f"{self.parent.workDir}/{tile[0]}_grid.gpkg")
        prevTile = self.parent.tiles[self.parent.currentTileIndex - 1] 

        try:
            if (path.exists(path.normpath(f"{self.parent.workDir}/{prevTile[0]}_grid.gpkg"))):
                remove(path.normpath(f"{self.parent.workDir}/{prevTile[0]}_grid.gpkg"))

            if (path.exists(path.normpath(f"{self.parent.workDir}/{prevTile[0]}_grid.gpkg-shm"))):
                remove(path.normpath(f"{self.parent.workDir}/{prevTile[0]}_grid.gpkg-shm"))

            if (path.exists(path.normpath(f"{self.parent.workDir}/{tile[0]}_grid.gpkg-wal"))):
                 remove(path.normpath(f"{self.parent.workDir}/{tile[0]}_grid.gpkg-wal"))
        except Exception:
             pass

        request = QgsFeatureRequest().setFilterFids([tile[0]])
        tilesFeatures = list(self.parent.tilesLayer.getFeatures(request))
        geom = tilesFeatures[0].geometry()
        self.tileGeom = geom

        self.loadTileMetadataFromBing(geom)

        if self.parent.getConfig('imageSource') == 'BING':
            self.parent.loadClasses()
            self.parent.dockwidget.btnFinishBing.setVisible(True)
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerBing.id()).setItemVisibilityChecked(True)
        else:
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerGoogle.id()).setItemVisibilityChecked(True)
            
         
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
            'OUTPUT': gridOutput}

        out = processing.run('native:creategrid', params)
        # self.parent.iface.messageBar().clearWidgets()
       
        grid = QgsVectorLayer(out['OUTPUT'], f"{tile[0]}_{self.interpreterName}", 'ogr')
        
        
        dataProvider = grid.dataProvider()
        # Enter editing mode
        grid.startEditing()

        # add fields
        dataProvider.addAttributes( 
            [ 
                QgsField("google_class", QVariant.String),
                QgsField("google_image_start_date",  QVariant.String),
                QgsField("google_image_end_date",  QVariant.String),
                QgsField("bing_class", QVariant.String),
                QgsField("bing_image_start_date",  QVariant.String),
                QgsField("bing_image_end_date",  QVariant.String),
                QgsField("missing_image_date",  QVariant.Int),
                QgsField("same_image_bing_google",  QVariant.Bool)
            ] 
        )

        # allFeatures = grid.getFeatures();
        # field_idx = grid.fields().indexOf('class')
        # for feature in allFeatures:
        #     grid.changeAttributeValue(feature.id(), field_idx, self.parent.selectedClass)

        grid.commitChanges()
    
        self.parent.currentPixelsLayer = grid
        QgsProject().instance().addMapLayer(grid)

        symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'black','width_border':'0.1'})
        grid.renderer().setSymbol(symbol)
        grid.triggerRepaint()
        self.parent.iface.setActiveLayer(grid);
        self.parent.iface.zoomToActiveLayer();
        
        grid.selectionChanged.connect(self.addClassToFeature)
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def clearButtons(self, layout):
        for i in reversed(range(layout.count())): 
            layout.itemAt(i).widget().setParent(None)
   
    def removeSelection(self):
        self.parent.selectedClass = None
        self.parent.iface.actionSelectFreehand().trigger() 
        self.getWidgetObject('selectedClass').setText(f"Removing classes...")
        self.getWidgetObject('selectedClass').setStyleSheet(f"background-color: transparent; border-radius: 5px; padding :5px; border: 2px solid red")
    

    def onClickClass(self, item):
        """Write config in config file"""
     
        imageDate = self.parent.dockwidget.imageDate.date().toString('yyyy-MM-dd')
        if (self.dateIsValid(imageDate)):
            self.getWidgetObject('selectedClass').setText(f"Selected class:  {item['class'].upper()}")
            self.getWidgetObject('selectedClass').setStyleSheet(f"background-color: {item['color']}; border-radius: 5px; padding :5px; border: 2px solid black")
            self.parent.selectedClass = item['class'].upper()
            self.selectedClassObject = item
            self.parent.iface.actionSelectFreehand().trigger() 
               
        else:
            self.parent.iface.messageBar().pushMessage("", f"The image date valid is required!", level=Qgis.Critical, duration=5)    
    
    def initInspectionTile(self, noImageDate=False):
        """Load all class of type inspection"""

        self.clearButtons(self.getWidgetObject('layoutClasses'))

        if not noImageDate:
            # self.parent.dockwidget.btnBack.setEnabled(True)
            self.parent.dockwidget.btnNext.setEnabled(True)
        else: 
            self.nextTile(noImageDate)
            return
         
       
        for _class in self.parent.campaignsConfig['classes']:
            if(_class['selected']):
                self.onClickClass(_class)

            if not noImageDate:
                button = QPushButton(_class['class'].upper(), checkable=True)
                button.setStyleSheet(f"background-color: {_class['color']}")
                button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
                button.clicked.connect(lambda checked, value = _class : self.onClickClass(value))
                self.getWidgetObject('layoutClasses').addWidget(button)
                
                
        self.getWidgetObject('btnClearSelection').setVisible(True)

    def clearContainerClasses(self, finished=False):
        
        if(self.parent.dockwidget):
            self.inspecting = False
            self.getWidgetObject('selectedClass').setVisible(False)
            self.parent.dockwidget.btnLoadClasses.setVisible(False)
            self.getWidgetObject('btnClearSelection').setVisible(False)
            self.clearButtons(self.getWidgetObject('layoutClasses'))
            self.parent.dockwidget.importBingClassification.setVisible(False)
            self.parent.dockwidget.imageDate.setDateTime(datetime.datetime.strptime('2000-01-01', '%Y-%m-%d'))
            self.parent.dockwidget.sameImage.setChecked(False)

            if(finished):
                    self.parent.dockwidget.btnNext.setVisible(False)
                    self.parent.dockwidget.btnPointDate.setVisible(False)
                    self.parent.dockwidget.labelImageDate.setVisible(False)
                    self.parent.dockwidget.imageDate.setVisible(False)
                    self.parent.dockwidget.btnLoadClasses.setVisible(False)
            else:
                self.getWidgetObject('labelClass').setVisible(False)

            for i in reversed(range(self.getWidgetObject('layoutClasses').count())): 
                self.getWidgetObject('layoutClasses').itemAt(i).widget().setParent(None)


    def layerIsEmpty(self, layer):
        request = QgsFeatureRequest().setFilterExpression(' "google_class" is NULL AND "google_image_start_date" is NULL AND "google_image_start_date" is NULL OR "bing_class" is NULL AND "bing_image_start_date" is NULL AND "bing_image_end_date" is NULL')
        resultFeatures = layer.getFeatures(request);

        if(layer.featureCount() == len(list(resultFeatures))):
            return True
        else:
            return False

    def tileMissingDate(self, tile):
        # Enter editing mode
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        self.parent.tilesLayer.startEditing()
        request = QgsFeatureRequest()
        request.setFilterFids([tile[0]])
        allFeatures = self.parent.tilesLayer.getFeatures(request);
        missing_image_date_idx = self.parent.tilesLayer.fields().indexOf('missing_image_date')
        for feature in allFeatures:
            self.parent.tilesLayer.changeAttributeValue(feature.id(), missing_image_date_idx, 1)    

        self.parent.tilesLayer.commitChanges()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def noDataInTile(self, layer, index, tilesLength):
        self.tileMissingDate(self.parent.tiles[self.parent.currentTileIndex])
        if(index < tilesLength):
            self.parent.currentTileIndex = index
            self.parent.setConfig(key='currentTileIndex', value= index)
            QgsProject.instance().removeMapLayer(layer.id())
            self.parent.configTiles()
            self.clearContainerClasses()
            self.onChangeTab(1)

        if(index == tilesLength):
            self.parent.iface.messageBar().pushMessage("", "Inspection FINISHED!", level=Qgis.Info, duration=15)
            self.getWidgetObject('tileInfo').setText(f"INSPECTION FINISHED!")
            self.clearContainerClasses(finished=True)
            self.parent.setConfig(key='currentTileIndex', value=0)
            self.parent.setConfig(key='filePath', value='')
            self.parent.setConfig(key='workingDirectory', value='')
            self.parent.setConfig(key='interpreterName', value='')
            self.parent.setConfig(key='imageSource', value='BING')
            self.parent.currentTileIndex = 0
            time.sleep(2)
            self.parent.onClosePlugin();
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
           
    
    def setSameImage(self, value):
        if self.inspecting:
            layer = self.parent.currentPixelsLayer
            QApplication.instance().setOverrideCursor(Qt.BusyCursor)
            layer.startEditing()
            allFeatures = layer.getFeatures();
            same_image_bing_google_idx = layer.fields().indexOf('same_image_bing_google')
            for feature in allFeatures:
                layer.changeAttributeValue(feature.id(), same_image_bing_google_idx, value)
            layer.commitChanges()
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def setImportClassesBing(self):
        layer = self.parent.currentPixelsLayer
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        layer.startEditing()
        allFeatures = layer.getFeatures()
        google_class_idx = self.parent.currentPixelsLayer.fields().indexOf('google_class')
        google_image_start_date_idx = self.parent.currentPixelsLayer.fields().indexOf('google_image_start_date')
        google_image_end_date_idx = self.parent.currentPixelsLayer.fields().indexOf('google_image_end_date')
     
        imageDate = self.parent.dockwidget.imageDate.date().toString('yyyy-MM-dd')
        for feature in allFeatures:
            layer.changeAttributeValue(feature.id(), google_class_idx, feature["bing_class"])
            layer.changeAttributeValue(feature.id(), google_image_start_date_idx, imageDate)
            layer.changeAttributeValue(feature.id(), google_image_end_date_idx, imageDate)

        layer.commitChanges()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def nextTile(self, noImageDate=False):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        layer = None
        index = self.parent.currentTileIndex + 1
        tilesLength = len(self.parent.tiles)
        retvalNoImageDate = None

        layer = self.parent.currentPixelsLayer
              
        if(layer):

            if(not noImageDate):
                if(self.layerIsEmpty(layer)):
                    retvalNoImageDate = self.dialog(
                        title="INSPECTION TILES",
                        text="Valid image date is required to classify this tile!",
                        info="If the image date were not found, the tile would be ignored. Do you confirm the missing date of the image?",
                        type="Question"
                    )
                    if (retvalNoImageDate == 16384):
                        self.initInspectionTile(noImageDate=True)
                        return

            if( index <= tilesLength):
                if not noImageDate:
                    endTime = datetime.datetime.now()
                    name = self.parent.getConfig('interpreterName')

                    if name is "":
                        name = self.parent.dockwidget.interpreterName.text()
                    
                    metadata = [f'DESCRIPTION=start_time: {self.inspectionStartDatetime.strftime("%Y-%m-%d %H:%M:%S")} | end_time: {endTime.strftime("%Y-%m-%d %H:%M:%S")} | time_in_seconds: {str((endTime - self.inspectionStartDatetime).total_seconds())} | interpreter: {self.normalize(name)}']
                    result =  Writer(self, layer, metadata).gpkg()
                    if(result and (index < tilesLength)):
                        self.parent.currentTileIndex = index
                        self.parent.setConfig(key='currentTileIndex', value= index)
                        QgsProject.instance().removeMapLayer(layer.id())
                        self.parent.configTiles()
                else:
                    self.noDataInTile(layer, index, tilesLength)
                    return

            self.clearContainerClasses()

            if(index == tilesLength):
                self.parent.iface.messageBar().pushMessage("", "Inspection FINISHED!", level=Qgis.Info, duration=15)
                if(self.parent.dockwidget):
                    self.getWidgetObject('tileInfo').setText(f"INSPECTION FINISHED!")
                    self.parent.setConfig(key='currentTileIndex', value=0)
                    self.parent.setConfig(key='filePath', value='')
                    self.parent.setConfig(key='workingDirectory', value='')
                    self.parent.setConfig(key='interpreterName', value='')
                    self.parent.setConfig(key='imageSource', value='BING')
                    self.clearContainerClasses(finished=True)
                    QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

                self.parent.currentTileIndex = 0
                time.sleep(2)
                self.parent.onClosePlugin();
            
        else: 
            self.parent.iface.messageBar().pushMessage("", "Something went wrong with the layer, Please close the plugin and try again", level=Qgis.Critical, duration=10)  

        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
        self.parent.iface.actionPan().trigger() 

    def loadTileFromFile(self, tile):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        self.parent.currentPixelsLayer = None
        self.livestockLayer = None
        
        self.initInspectionTile()
        
        filename = path.normpath(f"{self.parent.dockwidget.fieldWorkingDirectory.text()}/{tile[0]}_{self.parent.campaignsConfig['_id']}.gpkg") 
        layer = QgsVectorLayer(filename, f"{tile[0]}", 'ogr')

        symbol = QgsFillSymbol.createSimple({'color':'0,0,0,0','color_border':'black','width_border':'0.1'})
        layer.renderer().setSymbol(symbol)
        self.parent.currentPixelsLayer = layer
        self.setFeatureColor()

        QgsProject().instance().addMapLayer(layer)
        self.parent.iface.setActiveLayer(layer);
        self.parent.iface.zoomToActiveLayer();
        self.clearContainerClasses()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
            
    def startInspectionGoogle(self):
        self.parent.setConfig(key='imageSource', value='GOOGLE')
        self.setFeatureColor()
        QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerGoogle.id()).setItemVisibilityChecked(True)
        QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerBing.id()).setItemVisibilityChecked(False)
        self.parent.dockwidget.tabWidget.setCurrentIndex(2)
        self.parent.dockwidget.tabWidget.setTabEnabled(2, True)

    def onChangeTab(self, tab): 
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        if tab == 1:
            self.parent.iface.mapCanvas().setSelectionColor(QColor(255, 255, 255, 0))
            self.parent.setConfig(key='imageSource', value='BING')
            self.loadTileMetadataFromBing(self.tileGeom)
            self.setFeatureColor()
            self.parent.loadClasses()
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerGoogle.id()).setItemVisibilityChecked(False)
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerBing.id()).setItemVisibilityChecked(True)
            self.parent.dockwidget.btnFinishBing.setVisible(True)
            self.parent.dockwidget.tabWidget.setCurrentIndex(1)
            self.parent.dockwidget.tabWidget.setTabEnabled(1, True)
        elif tab == 2:
            self.parent.setConfig(key='imageSource', value='GOOGLE')
            self.parent.iface.mapCanvas().setSelectionColor(QColor(255, 255, 255, 0))
            self.loadThumbnailBing(self.bingThumUrl)
            self.setFeatureColor()
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerGoogle.id()).setItemVisibilityChecked(True)
            QgsProject.instance().layerTreeRoot().findLayer(self.parent.layerBing.id()).setItemVisibilityChecked(False)
            self.parent.dockwidget.tabWidget.setCurrentIndex(2)
            self.parent.dockwidget.tabWidget.setTabEnabled(2, True)

        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

