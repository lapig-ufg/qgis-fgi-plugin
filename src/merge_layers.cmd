echo off
set dst_datasource_name=inspections_merged.gpkg
del %dst_datasource_name%
for %%f in (*.gpkg) do (
    echo Merging %%~nf
    ogr2ogr -f gpkg -update -append -unsetFid %dst_datasource_name% %%~nf.gpkg -nln inspections_merged
)