import os
import tempfile


MAX_CHUNK = int(os.environ.get('MAX_CHUNK', 16384))
MAX_MEMORY = int(os.environ.get('MAX_MEMORY', 1024 ** 2 * 10))
TEMP_DIR = os.environ.get('TEMP_DIR', tempfile.gettempdir())
