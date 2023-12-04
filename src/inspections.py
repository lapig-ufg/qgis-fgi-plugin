import gc
import datetime
import time
import unicodedata
import urllib
from os import path, remove
import urllib.error

from PyQt5 import QtCore
from PyQt5.QtWidgets import QPushButton
from qgis import processing
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsField,
    QgsFillSymbol,
    QgsProject,
    QgsRuleBasedRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QCursor, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QListWidgetItem, QMessageBox
from requests.utils import requote_uri
import xml.etree.ElementTree as ET
from .export import Writer

from .tools import ClipboardPointer, ToolPointer


# from .s2 import Sentinel
# For debuging
# from memory_profiler import profile

class InspectionController:
    """QGIS Plugin Implementation."""

    def __init__(self, parent):
        self.parent = parent
        self.selected_class_object = None
        self.livestock_layer = None
        self.inspection_start_datetime = None
        self.tile = None
        self.tile_geom = None
        self.bing_thumb_url = None
        self.inspecting = False
        self.parent.dock_widget.btnNext.clicked.connect(self.next_tile)
        self.parent.dock_widget.btnSearch.clicked.connect(self.search_tile)
        self.parent.dock_widget.btnPointDate.clicked.connect(self.get_point)

    def dialog(self, title, text, info, type):
        ob_type = None
        msg = QMessageBox()

        if type == 'Critical':
            ob_type = QMessageBox.Critical
            msg.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
        elif type == 'Question':
            ob_type = QMessageBox.Question
            msg.setStandardButtons(QMessageBox.No | QMessageBox.Yes)
        elif type == 'Warning':
            ob_type = QMessageBox.Warning
            msg.setStandardButtons(QMessageBox.Ok)
        elif type == 'Information':
            ob_type = QMessageBox.Information
        else:
            ob_type = QMessageBox.Information

        msg.setIcon(ob_type)
        msg.setText(text)

        if info:
            msg.setInformativeText(info)

        msg.setWindowTitle(title)

        return msg.exec_()

    def get_widget_object(self, widget):
        widget_object = None

        if self.parent.get_config('imageSource') == 'BING':
            widget_object = getattr(self.parent.dock_widget, f'{widget}Bing')
        else:
            widget_object = getattr(self.parent.dock_widget, f'{widget}Google')

        return widget_object

    def get_point(self):
        canvas = self.parent.iface.mapCanvas()
        tool = ClipboardPointer(self.parent.iface, self)
        canvas.setMapTool(tool)

    def normalize(self, text):
        text = (
            unicodedata.normalize('NFD', text)
            .encode('ascii', 'ignore')
            .decode('utf-8')
        )
        return str(text).lower().replace(' ', '_')

    def rgba_string_to_hex(self, rgba_str):
        """Convert an RGBA color string to a hexadecimal string."""
        rgba = tuple(map(int, rgba_str.split(',')))
        color = QColor(
            int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
        )
        return color.name()

    def set_feature_color(self):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        # symbol = QgsSymbol.defaultSymbol(self.parent.current_pixels_layer.geometryType())
        symbol = QgsFillSymbol.createSimple(
            {
                'color': '0,0,0,0',
                'color_border': 'black',
                'width_border': '0.1',
            }
        )
        renderer = QgsRuleBasedRenderer(symbol)
        rules = []
        for type in self.parent.campaigns_config['classes']:
            rgba = None
            if "rgba" not in type:
                rgba = type['rgb'].split(',')
            else:
                rgba = type['rgba'].split(',')
            if self.parent.get_config('imageSource') == 'BING':
                rules.append(
                    [
                        type['class'].upper(),
                        f""""bing_class" = '{type['class'].upper()}'""",
                        QColor(
                            int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
                        ),
                    ]
                )
            else:
                rules.append(
                    [
                        type['class'].upper(),
                        f""""google_class" = '{type['class'].upper()}'""",
                        QColor(
                            int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
                        ),
                    ]
                )

        if self.parent.get_config('imageSource') == 'BING':
            rules.append(
                [
                    'NOT DEFINED',
                    f""""bing_class" is NULL""",
                    QColor(0, 0, 255, 0),
                ]
            )
        else:
            rules.append(
                [
                    'NOT DEFINED',
                    f""""google_class" is NULL""",
                    QColor(0, 0, 255, 0),
                ]
            )

        def rule_based_symbology(layer, renderer, label, expression, symbol, color):
            root_rule = renderer.rootRule()
            rule = root_rule.children()[0].clone()
            rule.setLabel(label)
            rule.setFilterExpression(expression)
            rule.symbol().setColor(QColor(color))
            root_rule.appendChild(rule)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

        if self.parent.current_pixels_layer:
            for rule in rules:
                rule_based_symbology(
                    self.parent.current_pixels_layer,
                    renderer,
                    rule[0],
                    rule[1],
                    symbol,
                    rule[2],
                )

            renderer.rootRule().removeChildAt(0)
            self.parent.iface.layerTreeView().refreshLayerSymbology(
                self.parent.current_pixels_layer.id()
            )
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def date_is_valid(self, date_text):
        try:
            date = datetime.datetime.strptime(date_text, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    # @profile
    def get_feature(self, featureId):
        feature = None
        all_features = self.parent.current_pixels_layer.getFeatures()
        for feat in all_features:
            if feat.id() == featureId:
                feature = feat
        return feature

    def remove_points(self, selected_features):
        request = QgsFeatureRequest()
        request.setFilterFids(selected_features)
        all_features = list(self.livestock_layer.getFeatures(request))

        self.livestock_layer.startEditing()

        for feature in all_features:
            self.livestock_layer.deleteFeature(feature.id())

        self.livestock_layer.commitChanges()
        canvas = self.parent.iface.mapCanvas()
        tool = ToolPointer(self.parent.iface, self.livestock_layer, self)
        canvas.setMapTool(tool)

    def get_field_index(self, field_name):
        return self.parent.current_pixels_layer.fields().indexOf(field_name)

    def add_class_to_feature(self, selected_features):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        request = QgsFeatureRequest()
        request.setFilterFids(selected_features)

        if self.parent.selectedClass is None:
            self.parent.iface.mapCanvas().setSelectionColor(
                QColor(255, 255, 255, 0)
            )

        else:
            rgba = None
            if "rgba" not in self.selected_class_object:
                rgba = self.selected_class_object['rgb'].split(',')
            else:
                rgba = self.selected_class_object['rgba'].split(',')

            self.parent.iface.mapCanvas().setSelectionColor(
                QColor(int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
            )

        if self.parent.current_pixels_layer:

            all_features = list(
                self.parent.current_pixels_layer.getFeatures(request)
            )
            google_class_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'google_class'
                )
            )
            google_image_start_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'google_image_start_date'
                )
            )
            google_image_end_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'google_image_end_date'
                )
            )

            bing_class_idx = self.parent.current_pixels_layer.fields().indexOf(
                'bing_class'
            )
            bing_image_start_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'bing_image_start_date'
                )
            )
            bing_image_end_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'bing_image_end_date'
                )
            )

            image_date = self.parent.dock_widget.imageDate.date().toString(
                'yyyy-MM-dd'
            )

            image_bind_start_date = (
                self.parent.dock_widget.bingStartDate.date().toString(
                    'yyyy-MM-dd'
                )
            )
            image_bind_end_date = (
                self.parent.dock_widget.bingEndDate.date().toString(
                    'yyyy-MM-dd'
                )
            )

            if self.parent.get_config('imageSource') == 'BING':
                if not self.date_is_valid(
                        image_bind_start_date
                ) and not self.date_is_valid(image_bind_end_date):
                    image_date = None
                    self.parent.iface.messageBar().pushMessage(
                        '',
                        'The image date of Bing valid is required!',
                        level=Qgis.Critical,
                        duration=5,
                    )
                    return
            else:
                if not self.date_is_valid(image_date):
                    image_date = None
                    self.parent.iface.messageBar().pushMessage(
                        '',
                        'The image date of Google valid is required!',
                        level=Qgis.Critical,
                        duration=5,
                    )
                    return

            self.parent.current_pixels_layer.startEditing()

            layer = self.parent.current_pixels_layer
            provider = layer.dataProvider()

            if not self.parent.selectedClass:
                image_date = None

            image_source = self.parent.get_config('imageSource')

            attribute_map = {}

            for feature in all_features:
                feature_id = feature.id()

                if image_source == 'BING':
                    attributes = {
                        bing_class_idx: self.parent.selectedClass,
                        bing_image_start_date_idx: image_bind_start_date,
                        bing_image_end_date_idx: image_bind_end_date
                    }
                else:
                    attributes = {
                        google_class_idx: self.parent.selectedClass,
                        google_image_start_date_idx: image_date,
                        google_image_end_date_idx: image_date
                    }

                attribute_map[feature_id] = attributes

            provider.changeAttributeValues(attribute_map)

            self.set_feature_color()
            layer.commitChanges()
            layer.triggerRepaint()

            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
        else:
            self.parent.iface.messageBar().pushMessage(
                '',
                'Something went wrong with the pixels layer, Please close the plugin and try again',
                level=Qgis.Critical,
                duration=10,
            )

    # @profile
    def set_default_class(self, layer):
        image_date = self.parent.dock_widget.imageDate.date().toString(
            'yyyy-MM-dd'
        )
        if not self.date_is_valid(image_date):
            image_date = None

        layer.startEditing()
        all_features = layer.getFeatures()
        google_class_idx = layer.fields().indexOf('google_class')
        google_image_start_date_idx = layer.fields().indexOf(
            'google_image_start_date'
        )
        google_image_end_date_idx = layer.fields().indexOf(
            'google_image_end_date'
        )

        bing_class_idx = layer.fields().indexOf('bing_class')
        bing_image_start_date_idx = layer.fields().indexOf(
            'bing_image_start_date'
        )
        bing_image_end_date_idx = layer.fields().indexOf('bing_image_end_date')

        image_date = self.parent.dock_widget.imageDate.date().toString(
            'yyyy-MM-dd'
        )

        image_bind_start_date = (
            self.parent.dock_widget.bingStartDate.date().toString('yyyy-MM-dd')
        )
        image_bind_end_date = (
            self.parent.dock_widget.bingEndDate.date().toString('yyyy-MM-dd')
        )

        # Determine the image source outside the loop
        is_bing = self.parent.get_config('imageSource') == 'BING'

        # Create a dictionary for batch updates
        attribute_map = {}

        for feature in all_features:
            if is_bing:
                attributes = {
                    bing_class_idx: self.parent.selectedClass,
                    bing_image_start_date_idx: image_bind_start_date,
                    bing_image_end_date_idx: image_bind_end_date
                }
            else:
                attributes = {
                    google_class_idx: self.parent.selectedClass,
                    google_image_start_date_idx: image_date,
                    google_image_end_date_idx: image_date
                }
            attribute_map[feature.id()] = attributes

        # Use the data provider to update the features in batch
        layer.dataProvider().changeAttributeValues(attribute_map)
        #
        # for feature in all_features:
        #     if self.parent.get_config('imageSource') == 'BING':
        #         layer.changeAttributeValue(
        #             feature.id(), bing_class_idx, self.parent.selectedClass
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(),
        #             bing_image_start_date_idx,
        #             image_bind_start_date,
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(), bing_image_end_date_idx, image_bind_end_date
        #         )
        #     else:
        #
        #         layer.changeAttributeValue(
        #             feature.id(), google_class_idx, self.parent.selectedClass
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(), google_image_start_date_idx, image_date
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(), google_image_end_date_idx, image_date
        #         )

        layer.commitChanges()
        # Emit the selectionChanged signal
        layer.selectionChanged.emit([], [], False)
        # If you believe you still need a repaint, you can call:
        layer.triggerRepaint()

    def get_not_found_img(self):
        current_directory = path.dirname(
            path.abspath(__file__))  # This gets the directory where inspections.py is located
        project_root = path.dirname(current_directory)  # This moves one level up to the project root
        img_path = path.join(project_root, 'img', 'not_found.png')
        return QPixmap(img_path)

    # @profile
    def load_thumbnail_bing(self, url):
        try:
            if url is None:
                pixmap = self.get_not_found_img()
            else:
                data = urllib.request.urlopen(url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
        except urllib.error.URLError:
            pixmap = self.get_not_found_img()

        self.get_widget_object('thum').setPixmap(pixmap)

    # @profile
    def load_tile_metadata_from_bing(self, geom):
        source_crs = QgsCoordinateReferenceSystem(3857)
        dest_crs = QgsCoordinateReferenceSystem(4326)

        tr = QgsCoordinateTransform(
            source_crs, dest_crs, QgsProject.instance()
        )
        point = tr.transform(geom.centroid().asPoint()).toString().split(',')

        lat = point[1].replace(' ', '')
        lon = point[0].replace(' ', '')

        if "bing_maps_key" in self.parent.campaigns_config:
            bing_maps_key = self.parent.campaigns_config['bing_maps_key']
        else:
            if "origin" in self.parent.campaigns_config:
                if self.parent.campaigns_config['origin'] == 'LAPIG':
                    bing_maps_key = 'AlXOiUXLu-4TbJpayRnVBURzY6RNXLLlK-STT2JIzBrkbXe0-53aSfaQXfDA7rt6'
                else:
                    bing_maps_key = 'UomkpKbLwbM1R9IfxTll~NFnQkcDTeQaWvbc96cVmQw~AjK0oEujZwZrnsBdSmg5cM47Lu25vSf1Hhuqxvc_IzTvo-dC4AzGh8wVXCFLgGO4'
            else:
                bing_maps_key = 'UomkpKbLwbM1R9IfxTll~NFnQkcDTeQaWvbc96cVmQw~AjK0oEujZwZrnsBdSmg5cM47Lu25vSf1Hhuqxvc_IzTvo-dC4AzGh8wVXCFLgGO4'

        try:
            url = requote_uri(
                f'https://dev.virtualearth.net/REST/V1/Imagery/Metadata/Aerial/{lat},{lon}?centerPoint={lat},{lon}&zl'
                f'=15&o=xml&key={bing_maps_key}'
            )
            data = urllib.request.urlopen(url).read()

            root = ET.fromstring(data)

            # Define the namespace mapping
            ns = {'ns0': 'http://schemas.microsoft.com/search/local/ws/rest/v1'}

            # Navigate the XML tree using the namespace prefix
            imagery_metadata = root.find("ns0:ResourceSets/ns0:ResourceSet/ns0:Resources/ns0:ImageryMetadata",
                                         namespaces=ns)

            if imagery_metadata is not None:
                start_date = imagery_metadata.findtext("ns0:VintageStart", namespaces=ns)
                end_date = imagery_metadata.findtext("ns0:VintageEnd", namespaces=ns)
                image_url = imagery_metadata.findtext("ns0:ImageUrl", namespaces=ns)
            else:
                start_date, end_date, image_url = None, None, None

            if start_date is None or end_date is None:
                start_date = '2000-01-01'
                end_date = '2000-01-01'
                self.parent.iface.messageBar().pushMessage(
                    'BING',
                    f'No dates were found for the BING image of the tile under analysis.',
                    level=Qgis.Critical,
                    duration=5,
                )
        except Exception as e:
            self.parent.iface.messageBar().pushMessage(
                'BING',
                f'No dates were found for the BING image of the tile under analysis.',
                level=Qgis.Critical,
                duration=5,
            )
            start_date = '2000-01-01'
            end_date = '2000-01-01'
            image_url = None
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
            print(e)

        self.set_dates_bing(start_date, end_date)

    def set_dates_bing(self, start_date, end_date):
        if isinstance(start_date, QVariant):
            start_date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The start date of Bing image was not found.',
                level=Qgis.Critical,
                duration=4,
            )

        if isinstance(end_date, QVariant):
            end_date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The end date of Bing image was not found.',
                level=Qgis.Critical,
                duration=4,
            )

        date_start = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        date_end = datetime.datetime.strptime(end_date, '%Y-%m-%d')

        period = date_end - date_start

        qdate_start = QtCore.QDateTime(date_start.year, date_start.month, date_start.day, date_start.hour, date_start.minute, date_start.second)
        qdate_end = QtCore.QDateTime(date_start.year, date_start.month, date_start.day, date_start.hour, date_start.minute, date_start.second)

        self.parent.dock_widget.bingStartDate.setDateTime(qdate_start)
        self.parent.dock_widget.bingEndDate.setDateTime(qdate_end)

        self.parent.dock_widget.bingPeriod.setText(str(period.days))

    def set_date_google(self, date):
        if isinstance(date, QVariant):
            date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The date of the Google image was not found.',
                level=Qgis.Critical,
                duration=4,
            )
        dtime = datetime.datetime.strptime(date, '%Y-%m-%d')
        qdate = QtCore.QDateTime(dtime.year, dtime.month, dtime.day, dtime.hour, dtime.minute, dtime.second)
        self.parent.dock_widget.imageDate.setDateTime(qdate)

    def create_grid_pixels(self, tile):
        out = None

        # Helper function for path normalization and file removal
        def remove_path(*args):
            p = path.normpath(path.join(*args))
            if path.exists(p):
                remove(p)

        self.tile = tile;
        self.parent.update_progress(50)
        self.parent.current_pixels_layer = None
        self.inspection_start_datetime = datetime.datetime.now()
        name = self.parent.get_config('interpreterName') or self.parent.dock_widget.interpreterName.text()
        self.interpreterName = self.normalize(name)

        grid_output = path.normpath(f'{self.parent.work_dir}/{tile[0]}_grid.gpkg')
        prev_tile_path = path.normpath(
            f'{self.parent.work_dir}/{self.parent.tiles[self.parent.current_tile_index - 1][0]}')

        # Removing previous files
        try:
            remove_path(prev_tile_path, "_grid.gpkg")
            remove_path(prev_tile_path, "_grid.gpkg-shm")
            remove_path(self.parent.work_dir, f"{tile[0]}_grid.gpkg-wal")
        except Exception:
            pass

        self.parent.update_progress(60)

        request = QgsFeatureRequest().setFilterFids([tile[0]])
        tiles_features = list(self.parent.tiles_layer.getFeatures(request))
        geom = tiles_features[0].geometry()
        self.tile_geom = geom

        self.parent.update_progress(63)
        active_layer = self.parent.layer_bing if self.parent.get_config(
            'imageSource') == 'BING' else self.parent.layer_google
        QgsProject.instance().layerTreeRoot().findLayer(active_layer.id()).setItemVisibilityChecked(True)
        self.parent.update_progress(66)

        selected_mode = self.parent.dock_widget.comboMode.currentText()

        grid_path = None
        layer_name = None

        if selected_mode == 'INSPECT':

            cell_size = self.parent.campaigns_config.get('cell_size', 10)
            extent = geom.boundingBox()
            params = {
                'TYPE': 2, 'EXTENT': extent, 'HSPACING': cell_size,
                'VSPACING': cell_size, 'HOVERLAY': 0, 'VOVERLAY': 0,
                'CRS': 'EPSG:3857', 'OUTPUT': grid_output
            }
            self.parent.update_progress(68)
            out = processing.run('native:creategrid', params)
            grid_path = out['OUTPUT']
            layer_name = f'{tile[0]}_{self.interpreterName}'
            self.parent.update_progress(70)

        else:
            grid_path = tile[2]
            layer_name = f"{tile[1].split('.')[0]}_review"
            self.set_dates_bing(tile[3], tile[4])
            self.set_date_google(tile[5])
            self.parent.load_classes()

        if grid_path is not None:

            grid = QgsVectorLayer(grid_path, layer_name, 'ogr')
            data_provider = grid.dataProvider()
            grid.startEditing()

            data_provider.addAttributes([
                QgsField('bing_class', QVariant.String),
                QgsField('bing_image_start_date', QVariant.String),
                QgsField('bing_image_end_date', QVariant.String),
                QgsField('google_class', QVariant.String),
                QgsField('google_image_start_date', QVariant.String),
                QgsField('google_image_end_date', QVariant.String),
                QgsField('missing_image_date', QVariant.Bool),
                QgsField('same_image_bing_google', QVariant.Bool)
            ])

            grid.commitChanges()

            self.parent.update_progress(80)
            self.parent.current_pixels_layer = grid

            QgsProject().instance().addMapLayer(grid)
            self.parent.iface.setActiveLayer(grid)
            self.parent.iface.zoomToActiveLayer()

            symbol = QgsFillSymbol.createSimple({'color': '0,0,0,0', 'color_border': 'black', 'width_border': '0.1'})
            grid.renderer().setSymbol(symbol)
            grid.triggerRepaint()
            grid.selectionChanged.connect(self.add_class_to_feature)
            self.parent.add_layer(grid.id())
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

            if out is not None:
                del out

            del grid
            gc.collect()

    # @profile
    def clear_buttons(self, layout):
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    # @profile
    def remove_selection(self):
        self.parent.selectedClass = None
        self.parent.iface.actionSelectFreehand().trigger()
        self.get_widget_object('selectedClass').setText(f'Removing classes...')
        self.get_widget_object('selectedClass').setStyleSheet(
            f'background-color: transparent; border-radius: 5px; padding :5px; border: 2px solid red'
        )

    # @profile
    def on_click_class(self, item):
        """Write config in config file"""
        color = ''
        if item:
            if 'rgba' in item:
                color = self.rgba_string_to_hex(item['rgba'])
            elif 'rgb' in item:
                color = self.rgba_string_to_hex(item['rgb'])

        image_date = self.parent.dock_widget.imageDate.date().toString(
            'yyyy-MM-dd'
        )

        if self.date_is_valid(image_date):
            self.get_widget_object('selectedClass').setText(
                f"Selected class:  {item['class'].upper()}"
            )
            self.get_widget_object('selectedClass').setStyleSheet(
                f"background-color: {color}; border-radius: 5px; padding :5px; border: 2px solid black"
            )
            self.parent.selectedClass = item['class'].upper()
            self.selected_class_object = item
            self.parent.iface.actionSelectFreehand().trigger()

        else:
            self.parent.iface.messageBar().pushMessage(
                '',
                f'The image date valid is required!',
                level=Qgis.Critical,
                duration=5,
            )

    def clear_list(self, list_widget):
        list_widget.clear()
        for i in range(list_widget.count()):
            item = list_widget.takeItem(i)
            if item:
                item.deleteLater()

    def create_classes_buttons(self, no_image_date):
        for _class in self.parent.campaigns_config['classes']:
            if _class['selected']:
                self.on_click_class(_class)

            if not no_image_date:
                color = 'transparent'
                if _class:
                    if 'rgba' in _class:
                        color = self.rgba_string_to_hex(_class['rgba'])
                    elif 'rgb' in _class:
                        color = self.rgba_string_to_hex(_class['rgb'])

                button = QPushButton(_class['class'].upper(), checkable=True)
                button.setStyleSheet(f"background-color: {color}")
                button.setCursor(QCursor(QtCore.Qt.PointingHandCursor))
                button.clicked.connect(
                    lambda checked, value=_class: self.on_click_class(value)
                )

                item = QListWidgetItem()
                item.setSizeHint(button.sizeHint())
                self.get_widget_object('classes').addItem(item)
                self.get_widget_object('classes').setItemWidget(item, button)

    def init_inspection_tile(self, no_image_date=False):
        """Load all class of type inspection"""

        # self.clearButtons(self.getWidgetObject('layoutClasses'))
        list_classes = self.get_widget_object('classes')
        list_classes.setVisible(True)

        if list_classes:
            self.clear_list(list_classes)

        if not no_image_date:
            self.parent.dock_widget.btnNext.setEnabled(True)
        else:
            self.next_tile(no_image_date)
            return

        self.create_classes_buttons(no_image_date)

        self.get_widget_object('btnClearSelection').setVisible(True)

    def clear_container_classes(self, finished=False):

        if self.parent.dock_widget:
            self.inspecting = False
            self.get_widget_object('selectedClass').setVisible(False)
            self.parent.dock_widget.btnLoadClasses.setVisible(False)
            self.get_widget_object('btnClearSelection').setVisible(False)
            self.clear_list(self.get_widget_object('classes'))
            self.parent.dock_widget.importBingClassification.setVisible(False)
            self.parent.dock_widget.imageDate.setDateTime(
                datetime.datetime.strptime('2000-01-01', '%Y-%m-%d')
            )
            self.parent.dock_widget.sameImage.setChecked(False)

            if finished:
                self.parent.dock_widget.btnNext.setVisible(False)
                self.parent.dock_widget.btnPointDate.setVisible(False)
                self.parent.dock_widget.labelImageDate.setVisible(False)
                self.parent.dock_widget.imageDate.setVisible(False)
                self.parent.dock_widget.btnLoadClasses.setVisible(False)
            else:
                self.get_widget_object('labelClass').setVisible(False)

    def layer_has_tiles_without_date_and_class(self, layer):
        request = QgsFeatureRequest().setFilterExpression(
            '"google_class" is NULL AND "google_image_start_date" is NULL AND "google_image_start_date" is NULL AND "bing_class" is NULL AND "bing_image_start_date" is NULL AND "bing_image_end_date" is NULL'
        )
        result_features = layer.getFeatures(request)
        total = len(list(result_features))
        # if (layer.featureCount() == total):
        if total > 0:
            message = f'There are {total} pixels with no informed date.'
            self.parent.iface.messageBar().pushMessage(
                'PIXELS WITHOUT DATE', message, level=Qgis.Warning, duration=6
            )
            return True
        else:
            return False

    def tile_missing_date(self, tile):
        # Enter editing mode
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        self.parent.tiles_layer.startEditing()

        missing_image_date_idx = self.parent.tiles_layer.fields().indexOf('missing_image_date')

        # Use data provider to change the attribute for the feature
        self.parent.tiles_layer.dataProvider().changeAttributeValues({
            tile[0]: {missing_image_date_idx: 1}
        })
        self.parent.tiles_layer.commitChanges()
        # Refresh the layer to reflect changes
        self.parent.tiles_layer.selectionChanged.emit([], [], False)
        # If you believe you still need a repaint, you can call:
        self.parent.tiles_layer.triggerRepaint()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def no_data_in_tile(self, layer, index, tiles_length):
        self.parent.update_progress(20)
        self.tile_missing_date(
            self.parent.tiles[self.parent.current_tile_index]
        )
        self.parent.update_progress(50)
        self.generate_gpkg(layer)
        self.parent.update_progress(70)
        if index < tiles_length:
            self.parent.current_tile_index = index
            self.parent.set_config(key='currentTileIndex', value=index)
            QgsProject.instance().removeMapLayer(layer.id())
            self.parent.config_tiles()
            self.clear_container_classes()
            self.on_change_tab(1)

        if index == tiles_length:
            self.parent.iface.messageBar().pushMessage(
                '', 'Inspection FINISHED!', level=Qgis.Info, duration=15
            )
            self.get_widget_object('tileInfo').setText(f'INSPECTION FINISHED!')
            current_directory = path.dirname(
                path.abspath(__file__))
            project_root = path.dirname(current_directory)
            img_path = path.join(project_root, 'img', 'finished.jpg')
            pixmap = QPixmap(img_path)
            self.get_widget_object('tileInfo').setPixmap(pixmap)
            self.clear_container_classes(finished=True)
            self.parent.clear_config()
            self.parent.current_tile_index = 0
            time.sleep(1)
            self.parent.onClosePlugin()
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    # @profile
    def set_same_image(self, value):
        if self.inspecting:
            layer = self.parent.current_pixels_layer
            QApplication.instance().setOverrideCursor(Qt.BusyCursor)
            layer.startEditing()

            same_image_bing_google_idx = layer.fields().indexOf('same_image_bing_google')
            changes = {feature.id(): {same_image_bing_google_idx: value} for feature in layer.getFeatures()}

            # Apply the changes using the data provider
            layer.dataProvider().changeAttributeValues(changes)

            # Refresh the layer to reflect changes
            layer.triggerRepaint()

            layer.commitChanges()
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    # @profile
    def import_classes_bing(self):

        layer = self.parent.current_pixels_layer
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        layer.startEditing()
        all_features = layer.getFeatures()
        google_class_idx = self.parent.current_pixels_layer.fields().indexOf(
            'google_class'
        )
        google_image_start_date_idx = (
            self.parent.current_pixels_layer.fields().indexOf(
                'google_image_start_date'
            )
        )
        google_image_end_date_idx = (
            self.parent.current_pixels_layer.fields().indexOf(
                'google_image_end_date'
            )
        )

        image_date = self.parent.dock_widget.imageDate.date().toString(
            'yyyy-MM-dd'
        )

        # Create an attribute map for batch updates
        attribute_map = {}

        for feature in all_features:
            attributes = {
                google_class_idx: feature['bing_class'],
                google_image_start_date_idx: image_date,
                google_image_end_date_idx: image_date
            }
            attribute_map[feature.id()] = attributes

        # Use the data provider to update the features in batch
        layer.dataProvider().changeAttributeValues(attribute_map)
        layer.commitChanges()
        self.set_feature_color()

        # Emit the selectionChanged signal
        layer.selectionChanged.emit([], [], False)

        # If you believe you still need a repaint, you can call:
        layer.triggerRepaint()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    # @profile
    def generate_gpkg(self, layer):
        end_time = datetime.datetime.now()
        name = self.parent.get_config('interpreterName')

        if name is '':
            name = self.parent.dock_widget.interpreterName.text()

        metadata = [
            f'DESCRIPTION=start_time: {self.inspection_start_datetime.strftime("%Y-%m-%d %H:%M:%S")} | end_time: {end_time.strftime("%Y-%m-%d %H:%M:%S")} | time_in_seconds: {str((end_time - self.inspection_start_datetime).total_seconds())} | interpreter: {self.normalize(name)}'
        ]

        with Writer(self, layer, metadata) as w:
            return w.gpkg()


    def finish_inspection(self):
        self.parent.iface.messageBar().pushMessage(
            '', 'Inspection FINISHED!', level=Qgis.Info, duration=15
        )
        self.get_widget_object('tileInfo').setText(f'INSPECTION FINISHED!')
        current_directory = path.dirname(
            path.abspath(__file__))
        project_root = path.dirname(current_directory)
        img_path = path.join(project_root, 'img', 'finished.jpg')
        pixmap = QPixmap(img_path)
        self.get_widget_object('tileInfo').setPixmap(pixmap)
        if self.parent.dock_widget:
            self.get_widget_object('tileInfo').setText(
                f'INSPECTION FINISHED!'
            )
            self.parent.clear_config()
            self.clear_container_classes(finished=True)
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
        self.parent.current_tile_index = 0
        time.sleep(2)
        self.parent.onClosePlugin()

    # @profile
    def next_tile(self, no_image_date=False, tile_index=None):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        layer = None
        if tile_index:
            index = tile_index
        else:
            index = self.parent.current_tile_index + 1
        tiles_length = len(self.parent.tiles)
        dialog_response = None

        layer = self.parent.current_pixels_layer

        if layer:

            if not no_image_date:
                self.parent.dock_widget.btnNext.setVisible(False)
                if self.layer_has_tiles_without_date_and_class(layer):
                    QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
                    dialog_response = self.dialog(
                        title='INSPECTION TILES',
                        info='Are you sure you want to generate a GPKG for this tile, even though some pixels do not have an associated date?',
                        text='This tile has pixels with no informed date.',
                        type='Question',
                    )

                    if dialog_response == QMessageBox.No:
                        self.parent.dock_widget.btnNext.setVisible(True)
                        return

            if index <= tiles_length:
                if not no_image_date:
                    result = self.generate_gpkg(layer)
                    if result and (index < tiles_length):
                        self.parent.current_tile_index = index
                        self.parent.set_config(
                            key='currentTileIndex', value=index
                        )
                        self.parent.remove_layer(layer.id())
                        QgsProject.instance().removeMapLayer(layer.id())
                        self.parent.config_tiles()
                        result = None

                else:
                    self.no_data_in_tile(layer, index, tiles_length)
                    return

            self.clear_container_classes()

            if index == tiles_length:
                self.finish_inspection()
            else:
                self.on_change_tab(1)

        else:
            self.parent.iface.messageBar().pushMessage(
                '',
                'Something went wrong with the layer, Please close the plugin and try again',
                level=Qgis.Critical,
                duration=10,
            )

        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
        self.parent.iface.actionPan().trigger()

    # @profile
    def load_tile_from_file(self, tile):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        self.parent.current_pixels_layer = None
        self.livestock_layer = None

        self.init_inspection_tile()

        filename = path.normpath(
            f"{self.parent.dock_widget.fieldWorkingDirectory.text()}/{tile[0]}_{self.parent.campaigns_config['_id']}.gpkg"
        )
        layer = QgsVectorLayer(filename, f'{tile[0]}', 'ogr')

        symbol = QgsFillSymbol.createSimple(
            {
                'color': '0,0,0,0',
                'color_border': 'black',
                'width_border': '0.1',
            }
        )
        layer.renderer().setSymbol(symbol)
        self.parent.current_pixels_layer = layer
        self.set_feature_color()

        QgsProject().instance().addMapLayer(layer)
        self.parent.iface.setActiveLayer(layer)
        self.parent.iface.zoomToActiveLayer()
        self.clear_container_classes()
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def start_inspection_google(self):
        self.parent.set_config(key='imageSource', value='GOOGLE')
        self.set_feature_color()
        QgsProject.instance().layerTreeRoot().findLayer(
            self.parent.layer_google.id()
        ).setItemVisibilityChecked(True)
        QgsProject.instance().layerTreeRoot().findLayer(
            self.parent.layer_bing.id()
        ).setItemVisibilityChecked(False)
        self.parent.dock_widget.tabWidget.setCurrentIndex(2)
        self.parent.dock_widget.tabWidget.setTabEnabled(2, True)

    def on_change_tab(self, tab):
        selected_mode = self.parent.dock_widget.comboMode.currentText()

        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        if tab == 1:
            self.parent.iface.mapCanvas().setSelectionColor(
                QColor(255, 255, 255, 0)
            )
            self.parent.set_config(key='imageSource', value='BING')

            if selected_mode == 'INSPECT':
                self.load_tile_metadata_from_bing(self.tile_geom)

            self.set_feature_color()
            self.parent.load_classes()
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_google.id()
            ).setItemVisibilityChecked(False)
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_bing.id()
            ).setItemVisibilityChecked(True)
            self.parent.dock_widget.btnFinishBing.setVisible(True)
            self.parent.dock_widget.tabWidget.setCurrentIndex(1)
            self.parent.dock_widget.tabWidget.setTabEnabled(1, True)

        elif tab == 2:
            self.parent.set_config(key='imageSource', value='GOOGLE')
            self.parent.iface.mapCanvas().setSelectionColor(
                QColor(255, 255, 255, 0)
            )
            self.set_date_google(self.tile[5])
            # self.load_thumbnail_bing(self.bing_thumb_url)
            self.set_feature_color()
            if selected_mode == 'REVIEW':
                self.parent.load_classes()

            self.inspecting = True
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_google.id()
            ).setItemVisibilityChecked(True)
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_bing.id()
            ).setItemVisibilityChecked(False)
            self.parent.dock_widget.tabWidget.setCurrentIndex(2)
            self.parent.dock_widget.tabWidget.setTabEnabled(2, True)
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def get_tile_index(self, feature_id):
        for index, tile in enumerate(self.parent.tiles):
            if feature_id == tile[0]:
                return index
        return -1

    def search_tile(self):
        QApplication.instance().setOverrideCursor(Qt.BusyCursor)
        index = self.get_tile_index(feature_id=self.parent.dock_widget.spinSearch.value())

        if not index >= 0:
            self.parent.iface.messageBar().pushMessage(
                'TILE SEARCH',
                'Tile not found',
                level=Qgis.Critical,
                duration=5,
            )
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)
            return

        layer = self.parent.current_pixels_layer

        self.parent.set_config(key='currentTileIndex', value=index)
        self.parent.current_tile_index = index

        self.clear_container_classes()

        QgsProject.instance().removeMapLayer(layer.id())
        self.parent.config_tiles()
        self.on_change_tab(1)
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    def skip_tile(self):
        self.parent.start_processing()
        tiles_length = len(self.parent.tiles)
        layer = self.parent.current_pixels_layer
        index = self.parent.current_tile_index + 1

        self.parent.remove_layer(layer.id())
        QgsProject.instance().removeMapLayer(layer.id())

        if index == tiles_length:
            self.finish_inspection()
        else:
            self.parent.current_tile_index = index
            self.parent.set_config(
                key='currentTileIndex', value=index
            )
            self.parent.config_tiles()
            self.clear_container_classes()
            self.on_change_tab(1)
            self.parent.update_progress(100)
            self.parent.finish_progress()

        layer = None
        gc.collect()
