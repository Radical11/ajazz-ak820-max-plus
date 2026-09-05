import zipfile
import os

with zipfile.ZipFile("repo.zip", "r") as z:
    for name in z.namelist():
        if ":" in name:
            print(f"Skipping {name}")
            continue
        z.extract(name, ".")
