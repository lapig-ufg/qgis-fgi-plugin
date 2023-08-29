from qgis import processing
from osgeo import gdal
from ..dependencies.satsearch.satsearch.search import Search
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from PyQt5.QtCore import QThread
from qgis.core import QgsRasterLayer, QgsProject, QgsMultiBandColorRenderer, QgsContrastEnhancement, \
    QgsCoordinateReferenceSystem

# Set the STAC API URL
STAC_API_URL = 'https://earth-search.aws.element84.com/v0'

# Define the coordinates of the point (Brasília)
collection = 'sentinel-s2-l2a-cogs'
monthly_composites = []

class Sentinel(QThread):
    def __init__(self, geojson):
        super().__init__()
        self.geojson = geojson

    def run(self):
        # This is executed in a separate thread
        show_monthly_composites(self.geojson)

def create_composite(b04_url, b8a_url, b11_url, output_name):
    # Check if URLs can be loaded as raster layers
    for url in [b04_url, b8a_url, b11_url]:
        test_layer = QgsRasterLayer(url, "Test Layer")
        if not test_layer.isValid():
            print(f"Error loading layer from {url}")
            return None

    # Create a VRT (Virtual Raster) with the projection to EPSG:3857
    output_file_3857 = f"/tmp/{output_name}_3857.vrt"

    # Define transformation options
    warp_options = gdal.WarpOptions(format='VRT', dstSRS='EPSG:3857', resampleAlg=gdal.GRA_NearestNeighbour, srcNodata=0)

    gdal.Warp(output_file_3857, [b04_url, b8a_url, b11_url], options=warp_options)

    # Load the reprojected VRT
    composite_layer_3857 = QgsRasterLayer(output_file_3857, f"{output_name}")
    if not composite_layer_3857.isValid():
        print("Error: Composite layer is not valid.")
        return None

    # Set up a multi-band color renderer
    renderer = QgsMultiBandColorRenderer(composite_layer_3857.dataProvider(), 3, 2, 1)

    # Adjust rendering properties for red, green, and blue bands
    for band, max_value in [(renderer.redContrastEnhancement(), 3000),
                            (renderer.greenContrastEnhancement(), 5000),
                            (renderer.blueContrastEnhancement(), 7000)]:
        if band:
            enhancement = QgsContrastEnhancement(band.dataType())
            enhancement.setMinimumValue(0)
            enhancement.setMaximumValue(max_value)
            enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)
            band.setContrastEnhancement(enhancement)

    composite_layer_3857.setRenderer(renderer)
    return composite_layer_3857
def show_monthly_composites(geometry, year=2022):
    for month in range(1, 2):
        start_date = f"{year}-{month:02}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month = month + 1
            end_date = f"{year}-{next_month:02}-01"

        date_range = f"{start_date}/{end_date}"

        # Search for the images
        search = Search(url=STAC_API_URL, intersects=geometry, datetime=date_range, collections=[collection],
                        query={'eo:cloud_cover': {'lt': 5}}, limit=1)
        items = search.items()
        print('date_range', geometry)
        items_list = list(items)
        items_list.sort(key=lambda item: item.properties['eo:cloud_cover'])

        if items_list:
            # Get the item with the least cloud cover for the month
            item = items_list[0]
            b04_url = item.assets['B04']['href']
            b8a_url = item.assets['B8A']['href']
            b11_url = item.assets['B11']['href']

            composite_name = f"Sentinel-{year}-{month:02}"
            print(composite_name, item, b04_url, b8a_url, b11_url)
            composite_layer = create_composite(b04_url, b8a_url, b11_url, composite_name)
            monthly_composites.append(composite_layer)

    for layer in monthly_composites:
        QgsProject.instance().addMapLayer(layer)
