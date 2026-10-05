from tests.settings import *
INSTALLED_APPS = ["nova_admin", *INSTALLED_APPS]
TEMPLATES[0]["OPTIONS"]["context_processors"].append("nova_admin.context_processors.theme")
NOVA_ADMIN = {"ENABLED": True}
