# -*- coding: utf-8 -*-
from osgeo import ogr
from collections import OrderedDict
import glob
import os
import sys
from features import splitFeatures, normalize

# Input settings
inputFile = sys.argv[1]
outputFolder = sys.argv[2]
interpreters =  sys.argv[3].split(',')

# Source layer
extension = r".gpkg"
driver = ogr.GetDriverByName('GPKG')
dataSource = driver.Open(inputFile)
layer = dataSource.GetLayer()
spatialReference = layer.GetSpatialRef()

for idx, group in enumerate(splitFeatures(layer, len(interpreters))):

    newDataSource = driver.CreateDataSource(f"{outputFolder}/{idx + 1}_tiles_{normalize(interpreters[idx])}_{group[0]}_{group[-1]}.gpkg")
    newLayer = newDataSource.CreateLayer(
        f"tiles_{normalize(interpreters[idx])}_{group[0]}_{group[-1]}",
        spatialReference, ogr.wkbPolygon,
        options=['FID=fid', 'GEOMETRY_NAME=geom'],
    ) 

    layerDefn = layer.GetLayerDefn()

    for i in range(layerDefn.GetFieldCount()):
        input_field = layerDefn.GetFieldDefn(i)
        newLayer.CreateField(input_field)

    missing_image_date_field = ogr.FieldDefn('missing_image_date', ogr.OFTInteger)
    missing_image_date_field.SetWidth(1)

    interpreter_field = ogr.FieldDefn('interpreter', ogr.OFTString)
    interpreter_field.SetWidth(24)
    
    newLayer.CreateField(interpreter_field)
    newLayer.CreateField(missing_image_date_field)

    for fid in group:
        feat = layer.GetFeature(fid)
        geom = feat.GetGeometryRef()
        dfn = newLayer.GetLayerDefn()
        # Create a new feature
        newFeature = ogr.Feature(dfn)
        field_names = [
            dfn.GetFieldDefn(i).GetName() for i in range(dfn.GetFieldCount())
        ]

        # Insert values
        for field_name in field_names:
            if field_name in ['missing_image_date', 'interpreter']:
                pass
            else:
                newFeature.SetField(field_name, str(feat.GetField(field_name)))

        newFeature.SetField("interpreter", normalize(interpreters[idx]))
        newFeature.SetField("missing_image_date", 0)
        newFeature.SetGeometry(geom)        
        newLayer.CreateFeature(newFeature)

        newFeature = None
    
    newDataSource = None
    newLayer = None