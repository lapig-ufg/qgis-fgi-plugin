from .dependencies.peewee import peewee

work_dir = str.split(__file__, "entities.py")[0]

# Criamos o banco de dados
db = peewee.SqliteDatabase(f'{work_dir}database.db')

class Config(db.Model):
    interpreterName = peewee.CharField()
    currentTileIndex = peewee.IntegerField()
    filePath = peewee.CharField()
    workingDirectory = peewee.TextField()
    imageSource = peewee.TextField()


def initDb():
    try:
        Config.create_table()
        config = Config.get_or_none(Config.id == 1)
        if config is None:
            config = Config.create(interpreterName='', currentTileIndex=0, filePath='', workingDirectory='', imageSource='BING')
            print("Configuration was created!")
        return config  
        print("Table 'Config' created!")
    except peewee.OperationalError as e:
        print(e)