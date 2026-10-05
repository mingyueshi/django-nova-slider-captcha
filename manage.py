#!/usr/bin/env python
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
