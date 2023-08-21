import json
from .dependencies.peewee import peewee
from ...config.params import get_config

work_dir = str.split(__file__, 'entities.py')[0]

# Criamos o banco de dados
db = peewee.SqliteDatabase(f'{work_dir}database.db')
def unescape_to_object(escaped_str):
    while isinstance(escaped_str, str):
        try:
            # Try to deserialize the string
            escaped_str = json.loads(escaped_str)
        except json.JSONDecodeError:
            # If it fails, we've likely fully unescaped the string
            break
    return escaped_str


class Config(db.Model):
    interpreterName = peewee.TextField()
    currentTileIndex = peewee.IntegerField()
    filePath = peewee.TextField()
    workingDirectory = peewee.TextField()
    imageSource = peewee.TextField()
    showImportsButtons = peewee.BooleanField()
    loadConfigFrom = peewee.TextField()
    configURL = peewee.TextField()
    inspectionConfig = peewee.TextField()

    # Serialization before saving
    def save(self, *args, **kwargs):
        self.inspectionConfig = json.dumps(self.inspectionConfig)
        super(Config, self).save(*args, **kwargs)

    # Deserialization after retrieving
    def get_inspection_config(self):
        return unescape_to_object(json.loads(self.inspectionConfig))

    class Meta:
        database = db


def init_db():
    try:
        Config.create_table()
        config = Config.get_or_none(Config.id == 1)
        if config is None:
            config = Config.create(**get_config())
            print('Configuration was created!')
        return config
    except peewee.OperationalError as e:
        print(e)


def reset_config():
    try:
        config_to_update = Config.get_by_id(1)

        # Get the updated values
        updated_values = get_config(empty=True)

        # Update the object with the new values
        config_to_update.interpreterName = updated_values['interpreterName']
        config_to_update.currentTileIndex = updated_values['currentTileIndex']
        config_to_update.filePath = updated_values['filePath']
        config_to_update.workingDirectory = updated_values['workingDirectory']
        config_to_update.imageSource = updated_values['imageSource']
        config_to_update.showImportsButtons = updated_values['showImportsButtons']
        config_to_update.loadConfigFrom = updated_values['loadConfigFrom']
        config_to_update.configURL = updated_values['configURL']
        # The 'inspectionConfig' field in the `Config` model is a TextField.
        # So, we need to convert the dictionary to a string representation.
        # One common way to do this is using JSON.
        config_to_update.inspectionConfig = json.dumps(updated_values['inspectionConfig'])

        # Save the changes back to the database
        config_to_update.save()
        return config_to_update
    except peewee.OperationalError as e:
        print(e)
