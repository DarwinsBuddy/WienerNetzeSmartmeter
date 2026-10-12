"""Update the manifest file."""
import sys
import json
import os


def update_manifest():
    """Update the manifest file."""
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in ["--version", "-V"]:
            version = sys.argv[index + 1]

    with open(
        f"{os.getcwd()}/custom_components/wnsm/manifest.json", encoding="utf-8"
    ) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    # hassfest requires "domain" and "name" first, then all other keys sorted
    ordered = {key: manifest[key] for key in ("domain", "name")}
    ordered.update(
        sorted((key, value) for key, value in manifest.items() if key not in ordered)
    )

    with open(
        f"{os.getcwd()}/custom_components/wnsm/manifest.json", "w", encoding="utf-8"
    ) as manifestfile:
        manifestfile.write(json.dumps(ordered, indent=4) + "\n")


update_manifest()
