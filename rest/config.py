import os
import tempfile


MAX_CHUNK = int(os.environ.get('MAX_CHUNK', 16384))
MAX_MEMORY = int(os.environ.get('MAX_MEMORY', 1024 ** 2 * 10))
TEMP_DIR = os.environ.get('TEMP_DIR', tempfile.gettempdir())

# NOTE: 1 is strongly encouraged, to restrict client connections to 1 at a
# time.
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", 1))
