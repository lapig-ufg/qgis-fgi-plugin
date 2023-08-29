import os
import json
def init_config(default_tiles_path=None, results_path=None, empty=False):
    """
    Returns the configuration object as specified.

    Parameters:
    - default_tiles_path: Path to the default tiles. If None, a default value will be used.
    - results_path: Path to the results directory. If None, a default value will be used.
    - empty: If True, some fields will be empty strings.

    Returns:
    - Configuration object.
    """

    if empty:
        interpreter_name = ''
        file_path = ''
        working_directory = ''
    else:
        if default_tiles_path is None or results_path is None:
            current_path = os.path.dirname(os.path.abspath(__file__))
            base_path = os.path.dirname(current_path)
            if default_tiles_path is None:
                default_tiles_path = os.path.join(base_path, "datasource", "default_tiles.gpkg")
            if results_path is None:
                results_path = os.path.join(base_path, "results")
        interpreter_name = 'test_user'
        file_path = default_tiles_path
        working_directory = results_path

    config = {
        'interpreterName': interpreter_name,
        'currentTileIndex': 0,
        'filePath': file_path,
        'workingDirectory': working_directory,
        'imageSource': 'BING',
        'showImportsButtons': True,
        'loadConfigFrom': 'local',
        'configURL': '',
        'inspectionConfig': json.dumps({
            'bing_maps_key': 'UomkpKbLwbM1R9IfxTll~NFnQkcDTeQaWvbc96cVmQw~AjK0oEujZwZrnsBdSmg5cM47Lu25vSf1Hhuqxvc_IzTvo-dC4AzGh8wVXCFLgGO4',
            'cell_size': 10,
            'classes': [
                {
                    'class': 'SEEDED GRASS',
                    'selected': False,
                    'rgba': '255,255,0,77'
                },
                {
                    'class': 'NATURAL OR SEMI-NATURAL GRASS',
                    'selected': False,
                    'rgba': '255,165,0,77'
                },
                {
                    'class': 'OTHERS',
                    'selected': True,
                    'rgba': '255,51,0,77'
                }
            ],
        })
    }
    return config
