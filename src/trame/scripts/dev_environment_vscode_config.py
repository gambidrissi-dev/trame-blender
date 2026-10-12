import json
from pathlib import Path

import bpy

import trame

repo_path = Path(trame.__file__).resolve().parent
install_path = Path(trame.__file__).absolute().parent
assert repo_path != install_path, "Run `dev_environment.py` to setup the development environment symlinks first."

repo_root = repo_path.parent.parent.parent
settings_path = repo_root / ".vscode" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
settings.update(
    {
        "trame.localRoot": repo_path.as_posix(),
        "trame.remoteRoot": install_path.as_posix(),
        "trame.blenderPath": Path(bpy.app.binary_path).parent.as_posix(),
    }
)
json_data = json.dumps(settings, indent=2)

settings_path.write_text(json_data)

print("\n\nBonsai/VSCode development environment configured successfully!\n\n")
