import os
import json
import sqlite3

from ...config.params import init_config

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Navigate up two directories to the project root
project_root = os.path.join(current_dir, '..', '..')

# Specify the new location for the database
database_path = os.path.join(project_root, 'datasource', 'database.db')

def unescape_to_object(escaped_str):
    while isinstance(escaped_str, str):
        try:
            # Try to deserialize the string
            escaped_str = json.loads(escaped_str)
        except json.JSONDecodeError:
            # If it fails, we've likely fully unescaped the string
            break
    return escaped_str


def init_db():
    try:
        conn = sqlite3.connect(database_path)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interpreterName TEXT,
                currentTileIndex INTEGER,
                filePath TEXT,
                workingDirectory TEXT,
                imageSource TEXT,
                showImportsButtons BOOLEAN,
                loadConfigFrom TEXT,
                configURL TEXT,
                inspectionConfig TEXT
            );
        ''')

        conn.commit()

        c.execute('SELECT * FROM config WHERE id = 1')
        config = c.fetchone()

        if config is None:
            config_data = init_config()
            keys = ', '.join(config_data.keys())
            values = ', '.join(['?' for _ in config_data])

            c.execute(f"INSERT INTO config ({keys}) VALUES ({values})", tuple(config_data.values()))
            conn.commit()

            print('Configuration created!')

        conn.close()
        return config

    except sqlite3.OperationalError as e:
        print(e)


def reset_config():
    try:
        conn = sqlite3.connect(database_path)
        c = conn.cursor()
        updated_values = init_config(empty=True)
        keys_and_values = ', '.join([f"{key} = ?" for key in updated_values])
        c.execute(f"UPDATE config SET {keys_and_values} WHERE id = 1", tuple(updated_values.values()))
        conn.commit()
        conn.close()
        return updated_values
    except sqlite3.OperationalError as e:
        print(f"Operational Error: {e}")
    except sqlite3.InterfaceError as e:
        print(f"Interface Error: {e} | type: {type(updated_values['inspectionConfig'])}")

def get_config(key):
    try:
        conn = sqlite3.connect(database_path)
        c = conn.cursor()
        c.execute(f'SELECT {key} FROM config WHERE id = 1')
        value = c.fetchone()
        if value is not None:
            value = value[0]
        conn.close()
        if key == 'inspectionConfig':
            return unescape_to_object(json.loads(value))
        return value
    except sqlite3.OperationalError as e:
        print(f"Operational Error: {e}")
        init_db()
        get_config(key)
    except sqlite3.InterfaceError as e:
        print(f"Interface Error: {e}")

def set_config(key, value):
    conn = sqlite3.connect(database_path)
    c = conn.cursor()
    try:
        if key == 'inspectionConfig':
            value = json.dumps(value)
        c.execute(f'UPDATE config SET {key} = ? WHERE id = 1', (value,))
        conn.commit()
    except Exception as e:
        print(f"Error setting config for key: {key}, value: {value}. Error: {e}")
        conn.rollback()
    finally:
        conn.close()

