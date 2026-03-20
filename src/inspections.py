import gc
import datetime
import json
import time
import unicodedata
import urllib
from os import path, remove
import urllib.error
import urllib.request

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
    QgsGeometry,
    QgsProject,
    QgsRuleBasedRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QCursor, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QListWidgetItem, QMessageBox
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
        self.esri_thumb_url = None
        self.inspecting = False
        self.esri_imagery_sensor = None
        self.esri_imagery_source = None
        self.esri_imagery_resolution = None
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

        if self.parent.get_config('imageSource') == 'ESRI':
            widget_object = getattr(self.parent.dock_widget, f'{widget}Esri')
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
            if self.parent.get_config('imageSource') == 'ESRI':
                rules.append(
                    [
                        type['class'].upper(),
                        f""""esri_class" = '{type['class'].upper()}'""",
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

        if self.parent.get_config('imageSource') == 'ESRI':
            rules.append(
                [
                    'NOT DEFINED',
                    f""""esri_class" is NULL""",
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

            esri_class_idx = self.parent.current_pixels_layer.fields().indexOf(
                'esri_class'
            )
            esri_image_start_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'esri_image_start_date'
                )
            )
            esri_image_end_date_idx = (
                self.parent.current_pixels_layer.fields().indexOf(
                    'esri_image_end_date'
                )
            )

            image_date = self.parent.dock_widget.imageDate.date().toString(
                'yyyy-MM-dd'
            )

            image_esri_start_date = (
                self.parent.dock_widget.esriStartDate.date().toString(
                    'yyyy-MM-dd'
                )
            )
            image_esri_end_date = (
                self.parent.dock_widget.esriEndDate.date().toString(
                    'yyyy-MM-dd'
                )
            )

            if self.parent.get_config('imageSource') == 'ESRI':
                if not self.date_is_valid(
                        image_esri_start_date
                ) and not self.date_is_valid(image_esri_end_date):
                    image_date = None
                    self.parent.iface.messageBar().pushMessage(
                        '',
                        'The image date of Esri valid is required!',
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

                if image_source == 'ESRI':
                    attributes = {
                        esri_class_idx: self.parent.selectedClass,
                        esri_image_start_date_idx: image_esri_start_date,
                        esri_image_end_date_idx: image_esri_end_date
                    }
                else:
                    attributes = {
                        google_class_idx: self.parent.selectedClass,
                        google_image_start_date_idx: image_date,
                        google_image_end_date_idx: image_date
                    }

                attribute_map[feature_id] = attributes
                print('attributes: ', attributes)
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

        esri_class_idx = layer.fields().indexOf('esri_class')
        esri_image_start_date_idx = layer.fields().indexOf(
            'esri_image_start_date'
        )
        esri_image_end_date_idx = layer.fields().indexOf('esri_image_end_date')

        image_date = self.parent.dock_widget.imageDate.date().toString(
            'yyyy-MM-dd'
        )

        image_esri_start_date = (
            self.parent.dock_widget.esriStartDate.date().toString('yyyy-MM-dd')
        )
        image_esri_end_date = (
            self.parent.dock_widget.esriEndDate.date().toString('yyyy-MM-dd')
        )

        # Determine the image source outside the loop
        is_esri = self.parent.get_config('imageSource') == 'ESRI'

        # Create a dictionary for batch updates
        attribute_map = {}

        for feature in all_features:
            if is_esri:
                attributes = {
                    esri_class_idx: self.parent.selectedClass,
                    esri_image_start_date_idx: image_esri_start_date,
                    esri_image_end_date_idx: image_esri_end_date
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
        #     if self.parent.get_config('imageSource') == 'ESRI':
        #         layer.changeAttributeValue(
        #             feature.id(), esri_class_idx, self.parent.selectedClass
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(),
        #             esri_image_start_date_idx,
        #             image_esri_start_date,
        #         )
        #         layer.changeAttributeValue(
        #             feature.id(), esri_image_end_date_idx, image_esri_end_date
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
    def load_thumbnail_esri(self, url):
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

    def _get_centroid_latlon(self, geom):
        source_crs = self.parent.tiles_layer.crs()
        dest_crs = QgsCoordinateReferenceSystem(4326)
        tr = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
        wgs84_point = tr.transform(geom.centroid().asPoint())
        return wgs84_point.y(), wgs84_point.x()

    def _fetch_esri_imagery_metadata(self, lat, lon):
        """Fetch imagery metadata from Esri World Imagery MapServer.

        Uses the public ArcGIS REST API (no API key required).
        Returns dict with keys: date, sensor, source (or None values).
        """
        url = (
            'https://services.arcgisonline.com/arcgis/rest/services/'
            'World_Imagery/MapServer/0/query'
            f'?where=1%3D1'
            f'&geometry={lon},{lat}'
            f'&geometryType=esriGeometryPoint'
            f'&spatialRel=esriSpatialRelIntersects'
            f'&inSR=4326'
            f'&outFields=SRC_DATE,SRC_DESC,NICE_NAME,SRC_RES'
            f'&returnGeometry=false'
            f'&f=json'
        )
        result = {'date': None, 'sensor': None, 'source': None, 'resolution': None}
        try:
            response = urllib.request.urlopen(url, timeout=15)
            data = json.loads(response.read().decode('utf-8'))
            features = data.get('features', [])
            if features:
                attrs = features[0].get('attributes', {})
                src_date = attrs.get('SRC_DATE')
                if src_date:
                    dt = datetime.datetime.strptime(str(src_date), '%Y%m%d')
                    result['date'] = dt.strftime('%Y-%m-%d')
                result['sensor'] = attrs.get('SRC_DESC') or None
                result['source'] = attrs.get('NICE_NAME') or None
                src_res = attrs.get('SRC_RES')
                if src_res is not None:
                    result['resolution'] = str(src_res)
        except Exception as e:
            print(f'Esri imagery metadata lookup failed: {e}')
        return result

    def load_tile_metadata_from_esri(self, geom):
        """Fetch imagery capture date and source for the tile centroid.

        Uses the Esri World Imagery public API (free, no key required).
        Stores metadata (sensor, source, resolution) on the controller
        for later inclusion in the exported GPKG.
        """
        lat, lon = self._get_centroid_latlon(geom)

        meta = self._fetch_esri_imagery_metadata(lat, lon)

        self.esri_imagery_sensor = meta['sensor']
        self.esri_imagery_source = meta['source']
        self.esri_imagery_resolution = meta['resolution']

        start_date = meta['date'] or '2000-01-01'
        end_date = start_date

        if start_date == '2000-01-01':
            self.parent.iface.messageBar().pushMessage(
                'IMAGE DATE',
                'Could not retrieve imagery date from Esri World Imagery.',
                level=Qgis.Warning,
                duration=5,
            )

        self.set_dates_esri(start_date, end_date)

    def set_dates_esri(self, start_date, end_date):
        if isinstance(start_date, QVariant):
            start_date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The start date of Esri image was not found.',
                level=Qgis.Critical,
                duration=4,
            )

        if isinstance(end_date, QVariant):
            end_date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The end date of Esri image was not found.',
                level=Qgis.Critical,
                duration=4,
            )

        date_start = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        date_end = datetime.datetime.strptime(end_date, '%Y-%m-%d')

        period = date_end - date_start

        qdate_start = QtCore.QDateTime(date_start.year, date_start.month, date_start.day, date_start.hour, date_start.minute, date_start.second)
        qdate_end = QtCore.QDateTime(date_start.year, date_start.month, date_start.day, date_start.hour, date_start.minute, date_start.second)

        self.parent.dock_widget.esriStartDate.setDateTime(qdate_start)
        self.parent.dock_widget.esriEndDate.setDateTime(qdate_end)

        self.parent.dock_widget.esriPeriod.setText(str(period.days))

    def set_date_google(self, date):
        if isinstance(date, QVariant):
            date = '2000-01-01'
            self.parent.iface.messageBar().pushMessage(
                'REVIEW TILE',
                'The date of the Google image was not found.',
                level=Qgis.Critical,
                duration=4,
            )
        print('set_date_google', date)
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

        # Fetch Esri imagery metadata (date, sensor, source, resolution) early
        # so it's available when the grid fields are populated below
        self.load_tile_metadata_from_esri(geom)

        self.parent.update_progress(63)
        active_layer = self.parent.layer_esri if self.parent.get_config(
            'imageSource') == 'ESRI' else self.parent.layer_google
        QgsProject.instance().layerTreeRoot().findLayer(active_layer.id()).setItemVisibilityChecked(True)
        self.parent.update_progress(66)

        selected_mode = self.parent.dock_widget.comboMode.currentText()

        grid_path = None
        layer_name = None

        if selected_mode == 'INSPECT':

            cell_size = self.parent.campaigns_config.get('cell_size', 10)
            grid_crs = self.parent.get_config('gridCrs') or 'EPSG:3857'

            tiles_crs = self.parent.tiles_layer.crs()
            target_crs = QgsCoordinateReferenceSystem(grid_crs)

            if tiles_crs != target_crs:
                transform = QgsCoordinateTransform(
                    tiles_crs, target_crs, QgsProject.instance()
                )
                reprojected_geom = QgsGeometry(geom)
                reprojected_geom.transform(transform)
                extent = reprojected_geom.boundingBox()
            else:
                extent = geom.boundingBox()

            params = {
                'TYPE': 2, 'EXTENT': extent, 'HSPACING': cell_size,
                'VSPACING': cell_size, 'HOVERLAY': 0, 'VOVERLAY': 0,
                'CRS': grid_crs, 'OUTPUT': grid_output
            }
            self.parent.update_progress(68)
            out = processing.run('native:creategrid', params)
            grid_path = out['OUTPUT']
            layer_name = f'{tile[0]}_{self.interpreterName}'
            self.parent.update_progress(70)

        else:
            grid_path = tile[2]
            layer_name = f"{tile[1].split('.')[0]}_review"
            self.set_dates_esri(tile[3], tile[4])
            self.set_date_google(tile[5])
            self.parent.load_classes()

        if grid_path is not None:

            grid = QgsVectorLayer(grid_path, layer_name, 'ogr')
            data_provider = grid.dataProvider()
            grid.startEditing()

            data_provider.addAttributes([
                QgsField('esri_class', QVariant.String),
                QgsField('esri_image_start_date', QVariant.String),
                QgsField('esri_image_end_date', QVariant.String),
                QgsField('google_class', QVariant.String),
                QgsField('google_image_start_date', QVariant.String),
                QgsField('google_image_end_date', QVariant.String),
                QgsField('missing_image_date', QVariant.Bool),
                QgsField('same_image_esri_google', QVariant.Bool),
                QgsField('esri_image_sensor', QVariant.String),
                QgsField('esri_image_source', QVariant.String),
                QgsField('esri_image_resolution', QVariant.String)
            ])

            grid.commitChanges()

            # Populate Esri imagery metadata for all features in the grid
            if self.esri_imagery_sensor or self.esri_imagery_source or self.esri_imagery_resolution:
                grid.startEditing()
                sensor_idx = grid.fields().indexOf('esri_image_sensor')
                source_idx = grid.fields().indexOf('esri_image_source')
                resolution_idx = grid.fields().indexOf('esri_image_resolution')
                attr_map = {}
                for feat in grid.getFeatures():
                    attrs = {}
                    if self.esri_imagery_sensor:
                        attrs[sensor_idx] = self.esri_imagery_sensor
                    if self.esri_imagery_source:
                        attrs[source_idx] = self.esri_imagery_source
                    if self.esri_imagery_resolution:
                        attrs[resolution_idx] = self.esri_imagery_resolution
                    if attrs:
                        attr_map[feat.id()] = attrs
                if attr_map:
                    grid.dataProvider().changeAttributeValues(attr_map)
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
            self.parent.dock_widget.importEsriClassification.setVisible(False)
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
            '"google_class" is NULL AND "google_image_start_date" is NULL AND "google_image_start_date" is NULL AND "esri_class" is NULL AND "esri_image_start_date" is NULL AND "esri_image_end_date" is NULL'
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

            same_image_esri_google_idx = layer.fields().indexOf('same_image_esri_google')
            changes = {feature.id(): {same_image_esri_google_idx: value} for feature in layer.getFeatures()}

            # Apply the changes using the data provider
            layer.dataProvider().changeAttributeValues(changes)

            # Refresh the layer to reflect changes
            layer.triggerRepaint()

            layer.commitChanges()
            QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

    # @profile
    def import_classes_esri(self):

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
                google_class_idx: feature['esri_class'],
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
            self.parent.layer_esri.id()
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
            self.parent.set_config(key='imageSource', value='ESRI')

            self.set_feature_color()
            self.parent.load_classes()
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_google.id()
            ).setItemVisibilityChecked(False)
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_esri.id()
            ).setItemVisibilityChecked(True)
            self.parent.dock_widget.btnFinishEsri.setVisible(True)
            self.parent.dock_widget.tabWidget.setCurrentIndex(1)
            self.parent.dock_widget.tabWidget.setTabEnabled(1, True)

        elif tab == 2:
            self.parent.set_config(key='imageSource', value='GOOGLE')
            self.parent.iface.mapCanvas().setSelectionColor(
                QColor(255, 255, 255, 0)
            )
            # self.load_thumbnail_esri(self.esri_thumb_url)
            self.set_feature_color()
            if selected_mode == 'REVIEW':
                self.set_date_google(self.tile[5])
                self.parent.load_classes()

            self.inspecting = True
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_google.id()
            ).setItemVisibilityChecked(True)
            QgsProject.instance().layerTreeRoot().findLayer(
                self.parent.layer_esri.id()
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
