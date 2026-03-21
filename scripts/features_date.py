from qgis.core import (
    QgsProject,
    QgsFeatureRequest,
    Qgis
)
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

def update_google_dates(layer_name_suffix, new_date):
    # Define o cursor de espera
    QApplication.instance().setOverrideCursor(Qt.BusyCursor)

    try:
        # Localiza a camada que termina com _review
        layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name().endswith(layer_name_suffix):
                layer = lyr
                break

        if not layer:
            raise Exception(f"Nenhuma camada encontrada com o sufixo '{layer_name_suffix}'")

        # Obtém os índices dos campos desejados
        google_image_start_date_idx = layer.fields().indexOf('google_image_start_date')
        google_image_end_date_idx = layer.fields().indexOf('google_image_end_date')

        if google_image_start_date_idx == -1 or google_image_end_date_idx == -1:
            raise Exception("Os campos 'google_image_start_date' ou 'google_image_end_date' não foram encontrados na camada")

        # Prepara a camada para edição
        layer.startEditing()
        provider = layer.dataProvider()

        # Cria o mapeamento de atributos para atualização
        attribute_map = {}
        for feature in layer.getFeatures():
            feature_id = feature.id()
            attributes = {
                google_image_start_date_idx: new_date,
                google_image_end_date_idx: new_date
            }
            attribute_map[feature_id] = attributes

        # Aplica as alterações
        provider.changeAttributeValues(attribute_map)

        # Confirma as alterações e atualiza a camada
        layer.commitChanges()
        layer.triggerRepaint()

        # Mensagem de sucesso
        QgsProject.instance().messageLog().logMessage(
            f"Datas atualizadas para a camada '{layer.name()}' com sucesso.",
            level=Qgis.Info
        )

    except Exception as e:
        QgsProject.instance().messageLog().logMessage(
            f"Erro ao atualizar datas: {str(e)}",
            level=Qgis.Critical
        )

    finally:
        # Restaura o cursor padrão
        QApplication.instance().setOverrideCursor(Qt.ArrowCursor)

# Exemplo de uso
layer_name_suffix = "_review"
new_date = "2021-01-02"
update_google_dates(layer_name_suffix, new_date)
