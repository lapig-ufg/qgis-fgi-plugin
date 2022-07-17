import numpy as np
import unicodedata

def splitFeatures(layer, size):
    listFeatures = [feature.GetFID() for feature in layer]
    return np.array_split(listFeatures, size)


def normalize(text):
    text = (
        unicodedata.normalize('NFD', text)
        .encode('ascii', 'ignore')
        .decode('utf-8')
    )
    return str(text).lower()
