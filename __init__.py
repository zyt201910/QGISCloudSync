# -*- coding: utf-8 -*-
"""
QGIS Cloud Sync Plugin
Copyright (C) 2024 Your Name

This plugin allows you to save QGIS project snapshots and data layers to MinIO storage bucket.
"""

import os
import sys
import inspect
from qgis.core import QgsApplication
from .qgis_cloud_sync import QGISCloudSync

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

class QGISCloudSyncPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.cloud_sync = None
    
    def initGui(self):
        self.cloud_sync = QGISCloudSync(self.iface)
        self.cloud_sync.init_gui()
    
    def unload(self):
        if self.cloud_sync:
            self.cloud_sync.unload()

def classFactory(iface):
    return QGISCloudSyncPlugin(iface)
