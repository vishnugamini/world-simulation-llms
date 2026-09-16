import json
import subprocess
from pathlib import Path

from virtual_world.api import create_app

Path("work").mkdir(exist_ok=True)
Path("work/openapi.json").write_text(
    json.dumps(create_app(".data/schema.sqlite3").openapi())
)
subprocess.run(["npm", "--prefix", "web", "run", "types"], check=True)
