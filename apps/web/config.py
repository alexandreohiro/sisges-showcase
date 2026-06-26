from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]
APP_NAME = "SisGeS"
APP_VERSION = "0.1.0"

HOST = os.getenv("SISGES_HOST", "127.0.0.1")
PORT = int(os.getenv("SISGES_PORT", "8000"))
DEBUG = os.getenv("SISGES_DEBUG", "false").lower() == "true"

STATIC_DIR = BASE_DIR / "apps" / "web" / "static"
TEMPLATES_DIR = BASE_DIR / "apps" / "web" / "templates"

DATA_DIR = BASE_DIR / "data"
INPUTS_DIR = DATA_DIR / "inputs"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEMP_DIR = DATA_DIR / "temp"
TEMPLATES_DATA_DIR = DATA_DIR / "templates"