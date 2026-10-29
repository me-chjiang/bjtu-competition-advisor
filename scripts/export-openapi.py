"""Write the backend OpenAPI schema to stdout for frontend type generation."""

import json
import sys

from backend.main import app

json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
sys.stdout.write("\n")
