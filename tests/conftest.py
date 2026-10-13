import os
import tempfile

# Testlar foydalanuvchining haqiqiy sozlamalarini (QSettings) o'zgartirmasin
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="ttysi_test_cfg_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
