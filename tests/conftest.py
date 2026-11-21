"""Shared test setup.

app.storage creates its data folder at import time, so point APPDATA (and HOME,
for non-Windows) at a throwaway directory before anything from `app` is imported.
"""

import os
import tempfile

_SANDBOX = tempfile.mkdtemp(prefix="ak820-tests-")
os.environ["APPDATA"] = _SANDBOX
os.environ["HOME"] = _SANDBOX
os.environ["USERPROFILE"] = _SANDBOX
