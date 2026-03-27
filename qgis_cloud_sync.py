# -*- coding: utf-8 -*-
"""
QGIS Cloud Sync Plugin
Core functionality for the plugin
"""

import os
import json
import time
import datetime
from PyQt5.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QSplitter, QGroupBox, 
    QProgressBar, QCheckBox, QComboBox, QSpinBox, QMessageBox, QFileDialog, QRadioButton
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
import boto3
from botocore.exceptions import ClientError
from qgis.core import QgsProject, QgsMapLayer, QgsVectorLayer, QgsRasterLayer
from qgis.gui import QgsMessageBar

class QGISCloudSync:
    def __init__(self, iface):
        self.iface = iface
        self.s3_client = None
        self.config_file = os.path.join(os.path.dirname(__file__), "minio_config.json")
        self.sync_history_file = os.path.join(os.path.dirname(__file__), "sync_history.json")
        self.snapshot_dir = "qgis_snapshots"
        self.timer = None
        self.auto_save_interval = 5  # 默认5分钟
        self.auto_save_enabled = False
        self.actions = []
        self.menu = "&QGIS云端同步"
        self.sync_history = []
    
    def init_gui(self):
        # 创建插件菜单项
        self.action_connect = QAction(
            QIcon(), "连接到MinIO", self.iface.mainWindow()
        )
        self.action_connect.triggered.connect(self.show_connection_dialog)
        
        self.action_save_snapshot = QAction(
            QIcon(), "保存工程快照", self.iface.mainWindow()
        )
        self.action_save_snapshot.triggered.connect(self.save_snapshot)
        self.action_save_snapshot.setEnabled(False)
        
        self.action_settings = QAction(
            QIcon(), "设置", self.iface.mainWindow()
        )
        self.action_settings.triggered.connect(self.show_settings_dialog)
        
        self.action_sync_history = QAction(
            QIcon(), "同步历史", self.iface.mainWindow()
        )
        self.action_sync_history.triggered.connect(self.show_sync_history)
        
        self.action_sync_from_minio = QAction(
            QIcon(), "从MinIO同步工程", self.iface.mainWindow()
        )
        self.action_sync_from_minio.triggered.connect(self.sync_from_minio)
        self.action_sync_from_minio.setEnabled(False)
        
        self.action_sync_to_cloud = QAction(
            QIcon(), "同步到云端", self.iface.mainWindow()
        )
        self.action_sync_to_cloud.triggered.connect(self.sync_to_cloud)
        self.action_sync_to_cloud.setEnabled(False)
        
        # 添加到QGIS菜单
        self.iface.addPluginToMenu(self.menu, self.action_connect)
        self.iface.addPluginToMenu(self.menu, self.action_save_snapshot)
        self.iface.addPluginToMenu(self.menu, self.action_sync_to_cloud)
        self.iface.addPluginToMenu(self.menu, self.action_sync_from_minio)
        self.iface.addPluginToMenu(self.menu, self.action_sync_history)
        self.iface.addPluginToMenu(self.menu, self.action_settings)
        
        # 添加到工具栏
        self.toolbar = self.iface.addToolBar("QGIS云端同步")
        self.toolbar.addAction(self.action_connect)
        self.toolbar.addAction(self.action_save_snapshot)
        self.toolbar.addAction(self.action_sync_to_cloud)
        self.toolbar.addAction(self.action_sync_from_minio)
        self.toolbar.addAction(self.action_settings)
        
        # 加载配置
        self.load_config()
        # 加载同步历史
        self.load_sync_history()
    
    def unload(self):
        # 清理定时器
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
        
        # 移除菜单项和工具栏
        for action in self.actions:
            self.iface.removePluginMenu("&QGIS Cloud Sync", action)
            self.iface.removeToolBarIcon(action)
        
        if hasattr(self, 'toolbar'):
            del self.toolbar
    
    def show_connection_dialog(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("MinIO连接设置")
        dialog.setGeometry(100, 100, 600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 连接配置组
        config_group = QGroupBox("MinIO连接设置")
        config_layout = QVBoxLayout(config_group)
        
        # Endpoint
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("服务器地址:"))
        self.endpoint_edit = QLineEdit("http://你的服务器IP:9000")
        h1.addWidget(self.endpoint_edit)
        config_layout.addLayout(h1)
        
        # AccessKey
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("访问密钥:"))
        self.access_edit = QLineEdit("你的AccessKey")
        h2.addWidget(self.access_edit)
        config_layout.addLayout(h2)
        
        # SecretKey
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("密钥:"))
        self.secret_edit = QLineEdit("你的SecretKey")
        h3.addWidget(self.secret_edit)
        config_layout.addLayout(h3)
        
        # BucketName
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("存储桶名称:"))
        self.bucket_edit = QLineEdit("你的存储桶名")
        h4.addWidget(self.bucket_edit)
        config_layout.addLayout(h4)
        
        # 连接按钮
        self.connect_btn = QPushButton("测试连接")
        self.connect_btn.clicked.connect(lambda: self.connect_minio(dialog))
        config_layout.addWidget(self.connect_btn)
        
        # 导入导出配置按钮
        config_btn_layout = QHBoxLayout()
        import_btn = QPushButton("导入配置")
        import_btn.clicked.connect(lambda: self.import_config(dialog))
        export_btn = QPushButton("导出配置")
        export_btn.clicked.connect(lambda: self.export_config(dialog))
        config_btn_layout.addWidget(import_btn)
        config_btn_layout.addWidget(export_btn)
        config_layout.addLayout(config_btn_layout)
        
        layout.addWidget(config_group)
        
        # 日志输出
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        # 加载配置
        self.load_config()
        
        dialog.exec_()
    
    def connect_minio(self, dialog):
        endpoint = self.endpoint_edit.text().strip()
        access_key = self.access_edit.text().strip()
        secret_key = self.secret_edit.text().strip()
        bucket = self.bucket_edit.text().strip()
        
        if not all([endpoint, access_key, secret_key, bucket]):
            QMessageBox.warning(dialog, "警告", "请填写完整的连接信息！")
            return
        
        try:
            # 初始化S3客户端
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                verify=False,
                region_name="us-east-1"
            )
            # 测试连接
            self.s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)
            QMessageBox.information(dialog, "成功", "MinIO连接成功！")
            self.log_text.append("=== 连接成功！ ===")
            # 启用保存快照按钮
            self.action_save_snapshot.setEnabled(True)
            # 启用从MinIO同步工程按钮
            self.action_sync_from_minio.setEnabled(True)
            # 启用同步到云端按钮
            self.action_sync_to_cloud.setEnabled(True)
            # 保存配置
            self.save_config()
            # 确保快照目录存在
            self.ensure_snapshot_directory()
        except Exception as e:
            QMessageBox.critical(dialog, "连接失败", f"错误：{str(e)}")
            self.log_text.append(f"连接失败：{str(e)}")
    
    def show_settings_dialog(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("云端同步设置")
        dialog.setGeometry(100, 100, 400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 自动保存设置
        auto_save_group = QGroupBox("自动保存设置")
        auto_save_layout = QVBoxLayout(auto_save_group)
        
        self.auto_save_checkbox = QCheckBox("启用自动保存")
        self.auto_save_checkbox.setChecked(self.auto_save_enabled)
        auto_save_layout.addWidget(self.auto_save_checkbox)
        
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("保存间隔（分钟）:"))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimum(1)
        self.interval_spinbox.setMaximum(60)
        self.interval_spinbox.setValue(self.auto_save_interval)
        h1.addWidget(self.interval_spinbox)
        auto_save_layout.addLayout(h1)
        
        layout.addWidget(auto_save_group)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(lambda: self.save_settings(dialog))
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def save_settings(self, dialog):
        self.auto_save_enabled = self.auto_save_checkbox.isChecked()
        self.auto_save_interval = self.interval_spinbox.value()
        
        # 保存配置
        config = self.load_config()
        config['auto_save_enabled'] = self.auto_save_enabled
        config['auto_save_interval'] = self.auto_save_interval
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 配置定时器
        self.configure_timer()
        
        QMessageBox.information(dialog, "成功", "设置保存成功！")
        dialog.accept()
    
    def configure_timer(self):
        if self.auto_save_enabled:
            if self.timer:
                self.timer.stop()
                self.timer.deleteLater()
            
            self.timer = QTimer()
            self.timer.timeout.connect(self.auto_save_snapshot)
            self.timer.start(self.auto_save_interval * 60 * 1000)  # 转换为毫秒
            self.iface.messageBar().pushInfo("QGIS云端同步", f"自动保存已启用。将每 {self.auto_save_interval} 分钟保存一次。")
        else:
            if self.timer:
                self.timer.stop()
                self.timer.deleteLater()
                self.timer = None
            self.iface.messageBar().pushInfo("QGIS云端同步", "自动保存已禁用。")
    
    def save_snapshot(self):
        if not self.s3_client:
            QMessageBox.warning(self.iface.mainWindow(), "警告", "请先连接到MinIO！")
            return
        
        # 获取当前工程
        project = QgsProject.instance()
        project_path = project.fileName()
        
        if not project_path:
            QMessageBox.warning(self.iface.mainWindow(), "警告", "请先保存工程！")
            return
        
        # 创建快照名称
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = os.path.basename(project_path).replace('.qgz', '').replace('.qgs', '')
        snapshot_name = f"{project_name}_{timestamp}"
        
        # 显示保存选项对话框
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("保存快照")
        dialog.setGeometry(100, 100, 500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 快照信息
        info_group = QGroupBox("快照信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(f"快照名称: {snapshot_name}"))
        info_layout.addWidget(QLabel(f"工程: {project_name}"))
        info_layout.addWidget(QLabel(f"时间戳: {timestamp}"))
        layout.addWidget(info_group)
        
        # 图层选择
        layers_group = QGroupBox("要包含的图层")
        layers_layout = QVBoxLayout(layers_group)
        
        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QListWidget.MultiSelection)
        
        # 填充图层列表
        for layer in project.mapLayers().values():
            item = QListWidgetItem(layer.name())
            item.setData(Qt.UserRole, layer)
            self.layer_list.addItem(item)
        
        layers_layout.addWidget(self.layer_list)
        layout.addWidget(layers_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(lambda: self.perform_save_snapshot(dialog, snapshot_name, project_path))
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def perform_save_snapshot(self, dialog, snapshot_name, project_path):
        try:
            # 确保快照目录存在
            self.ensure_snapshot_directory()
            
            # 上传工程文件
            project_key = f"{self.snapshot_dir}/{snapshot_name}/{os.path.basename(project_path)}"
            self.upload_file(project_path, project_key)
            
            # 上传选中的图层文件
            selected_items = self.layer_list.selectedItems()
            for i, item in enumerate(selected_items):
                layer = item.data(Qt.UserRole)
                if hasattr(layer, 'dataProvider') and hasattr(layer.dataProvider(), 'dataSourceUri'):
                    data_source = layer.dataProvider().dataSourceUri()
                    # 提取文件路径
                    if layer.type() == QgsMapLayer.VectorLayer:
                        # 矢量图层
                        if '|' in data_source:
                            file_path = data_source.split('|')[0]
                        else:
                            file_path = data_source
                    elif layer.type() == QgsMapLayer.RasterLayer:
                        # 栅格图层
                        file_path = data_source
                    else:
                        continue
                    
                    if os.path.exists(file_path):
                        layer_key = f"{self.snapshot_dir}/{snapshot_name}/layers/{os.path.basename(file_path)}"
                        self.upload_file(file_path, layer_key)
                        
                # 更新进度
                progress = int((i + 1) / (len(selected_items) + 1) * 100)
                self.progress_bar.setValue(progress)
            
            self.progress_bar.setValue(100)
            QMessageBox.information(dialog, "成功", "快照保存成功！")
            self.iface.messageBar().pushSuccess("QGIS云端同步", "快照保存成功！")
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(dialog, "错误", f"保存快照失败：{str(e)}")
            self.iface.messageBar().pushCritical("QGIS云端同步", f"保存快照失败：{str(e)}")
    
    def auto_save_snapshot(self):
        if not self.s3_client:
            return
        
        # 获取当前工程
        project = QgsProject.instance()
        project_path = project.fileName()
        
        if not project_path:
            return
        
        # 创建快照名称
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = os.path.basename(project_path).replace('.qgz', '').replace('.qgs', '')
        snapshot_name = f"{project_name}_auto_{timestamp}"
        
        try:
            # 确保快照目录存在
            self.ensure_snapshot_directory()
            
            # 上传工程文件
            project_key = f"{self.snapshot_dir}/{snapshot_name}/{os.path.basename(project_path)}"
            self.upload_file(project_path, project_key)
            
            self.iface.messageBar().pushInfo("QGIS云端同步", f"自动快照已保存：{snapshot_name}")
        except Exception as e:
            self.iface.messageBar().pushCritical("QGIS云端同步", f"自动保存快照失败：{str(e)}")
    
    def upload_file(self, file_path, key):
        bucket = self.bucket_edit.text().strip()
        try:
            self.s3_client.upload_file(file_path, bucket, key)
        except Exception as e:
            raise e
    
    def ensure_snapshot_directory(self):
        bucket = self.bucket_edit.text().strip()
        try:
            # 检查快照目录是否存在
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=self.snapshot_dir,
                MaxKeys=1
            )
            
            if 'Contents' not in response:
                # 创建快照目录（通过上传空对象）
                self.s3_client.put_object(
                    Bucket=bucket,
                    Key=f"{self.snapshot_dir}/"
                )
        except Exception as e:
            raise e
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 加载连接配置
                if hasattr(self, 'endpoint_edit'):
                    self.endpoint_edit.setText(config.get('endpoint', "http://your-server-ip:9000"))
                if hasattr(self, 'access_edit'):
                    self.access_edit.setText(config.get('access_key', "your-access-key"))
                if hasattr(self, 'secret_edit'):
                    self.secret_edit.setText(config.get('secret_key', "your-secret-key"))
                if hasattr(self, 'bucket_edit'):
                    self.bucket_edit.setText(config.get('bucket', "your-bucket-name"))
                
                # 加载自动保存配置
                self.auto_save_enabled = config.get('auto_save_enabled', False)
                self.auto_save_interval = config.get('auto_save_interval', 5)
                
                return config
            except Exception as e:
                print(f"Failed to load config: {str(e)}")
        
        # 默认配置
        return {
            'endpoint': "http://your-server-ip:9000",
            'access_key': "your-access-key",
            'secret_key': "your-secret-key",
            'bucket': "your-bucket-name",
            'auto_save_enabled': False,
            'auto_save_interval': 5
        }
    
    def import_config(self, dialog):
        file_path, _ = QFileDialog.getOpenFileName(dialog, "导入配置", "", "JSON文件 (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 加载配置到界面
            if 'endpoint' in config:
                self.endpoint_edit.setText(config['endpoint'])
            if 'access_key' in config:
                self.access_edit.setText(config['access_key'])
            if 'secret_key' in config:
                self.secret_edit.setText(config['secret_key'])
            if 'bucket' in config:
                self.bucket_edit.setText(config['bucket'])
            if 'auto_save_enabled' in config:
                self.auto_save_enabled = config['auto_save_enabled']
            if 'auto_save_interval' in config:
                self.auto_save_interval = config['auto_save_interval']
            
            self.log_text.append("=== 配置导入成功 ===")
            QMessageBox.information(dialog, "成功", "配置导入成功！")
        except Exception as e:
            QMessageBox.critical(dialog, "导入失败", f"错误：{str(e)}")
            self.log_text.append(f"导入配置失败：{str(e)}")
    
    def export_config(self, dialog):
        file_path, _ = QFileDialog.getSaveFileName(dialog, "导出配置", "minio_config.json", "JSON文件 (*.json)")
        if not file_path:
            return
        try:
            config = {
                'endpoint': self.endpoint_edit.text().strip(),
                'access_key': self.access_edit.text().strip(),
                'secret_key': self.secret_edit.text().strip(),
                'bucket': self.bucket_edit.text().strip(),
                'auto_save_enabled': self.auto_save_enabled,
                'auto_save_interval': self.auto_save_interval
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log_text.append(f"=== 配置导出成功：{file_path} ===")
            QMessageBox.information(dialog, "成功", f"配置导出成功：{file_path}")
        except Exception as e:
            QMessageBox.critical(dialog, "导出失败", f"错误：{str(e)}")
            self.log_text.append(f"导出配置失败：{str(e)}")
    
    def sync_from_minio(self):
        if not self.s3_client:
            QMessageBox.warning(self.iface.mainWindow(), "警告", "请先连接到MinIO！")
            return
        
        # 显示同步对话框
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("从MinIO同步工程")
        dialog.setGeometry(100, 100, 600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 快照列表
        snapshot_group = QGroupBox("可用的快照")
        snapshot_layout = QVBoxLayout(snapshot_group)
        
        self.snapshot_list = QListWidget()
        self.snapshot_list.setSelectionMode(QListWidget.SingleSelection)
        
        # 填充快照列表
        self.list_snapshots()
        
        snapshot_layout.addWidget(self.snapshot_list)
        layout.addWidget(snapshot_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        sync_btn = QPushButton("同步")
        sync_btn.clicked.connect(lambda: self.perform_sync_from_minio(dialog))
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(sync_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def list_snapshots(self):
        if not self.s3_client:
            return
        
        bucket = self.bucket_edit.text().strip()
        self.snapshot_list.clear()
        
        try:
            # 首先检查快照目录是否存在
            self.ensure_snapshot_directory()
            
            # 列出所有对象，包括子目录
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=self.snapshot_dir
            )
            
            # 收集所有快照目录
            snapshot_dirs = set()
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    # 提取快照目录路径
                    if key.startswith(self.snapshot_dir + '/'):
                        # 找到第一个子目录（快照目录）
                        parts = key.split('/')
                        if len(parts) > 2:
                            snapshot_dir = '/'.join(parts[:2]) + '/'
                            snapshot_dirs.add(snapshot_dir)
            
            # 添加快照目录到列表
            for snapshot_dir in sorted(snapshot_dirs):
                # 提取快照名称
                snapshot_name = snapshot_dir.replace(self.snapshot_dir + '/', '').rstrip('/')
                if snapshot_name:
                    item = QListWidgetItem(snapshot_name)
                    item.setData(Qt.UserRole, snapshot_dir)
                    self.snapshot_list.addItem(item)
            
            # 如果没有快照，显示提示
            if not snapshot_dirs:
                self.snapshot_list.addItem("没有可用的快照")
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "错误", f"获取快照列表失败：{str(e)}")
    
    def download_progress_callback(self, *args):
        # 处理不同类型的参数
        if len(args) == 1:
            # 可能是字典或整数
            if isinstance(args[0], dict):
                progress = args[0]
                bytes_downloaded = progress.get('BytesTransferred', 0)
                total_bytes = progress.get('TotalBytes', 1)
            else:
                # 假设是已下载的字节数
                bytes_downloaded = args[0]
                total_bytes = 1  # 默认为1避免除零错误
        elif len(args) == 2:
            # 直接是字节数和总字节数
            bytes_downloaded, total_bytes = args
        else:
            return
        
        if total_bytes > 0:
            progress_percent = int((bytes_downloaded / total_bytes) * 100)
            self.progress_bar.setValue(progress_percent)
    
    def perform_sync_from_minio(self, dialog):
        selected_items = self.snapshot_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(dialog, "警告", "请选择要同步的快照！")
            return
        
        selected_item = selected_items[0]
        snapshot_path = selected_item.data(Qt.UserRole)
        snapshot_name = selected_item.text()
        
        # 选择保存目录
        save_dir = QFileDialog.getExistingDirectory(dialog, "选择保存目录")
        if not save_dir:
            return
        
        # 构建完整的本地快照目录路径
        local_snapshot_dir = os.path.join(save_dir, snapshot_name)
        
        try:
            bucket = self.bucket_edit.text().strip()
            
            # 列出快照中的文件
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=snapshot_path
            )
            
            if 'Contents' in response:
                files = response['Contents']
                total_files = len(files)
                current_file = 0
                
                for file_obj in files:
                    file_key = file_obj['Key']
                    # 构建本地文件路径（保持完整的目录结构）
                    relative_path = file_key.replace(snapshot_path, '')
                    local_file_path = os.path.join(local_snapshot_dir, relative_path.lstrip('/'))
                    
                    # 确保目录存在
                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                    
                    # 下载文件
                    self.s3_client.download_file(
                        bucket, file_key, local_file_path,
                        Callback=self.download_progress_callback
                    )
                    
                    # 更新进度
                    current_file += 1
                    overall_progress = int((current_file / total_files) * 100)
                    self.progress_bar.setValue(overall_progress)
                
                # 找到工程文件
                project_file = None
                for file_obj in files:
                    file_key = file_obj['Key']
                    if file_key.endswith('.qgz') or file_key.endswith('.qgs'):
                        relative_path = file_key.replace(snapshot_path, '')
                        project_file = os.path.join(local_snapshot_dir, relative_path.lstrip('/'))
                        break
                
                if project_file:
                    # 打开工程文件（不需要修改路径，因为目录结构保持一致）
                    self.iface.addProject(project_file)
                    QMessageBox.information(dialog, "成功", f"工程同步成功！已打开：{project_file}")
                else:
                    QMessageBox.warning(dialog, "警告", "未找到工程文件！")
            else:
                QMessageBox.warning(dialog, "警告", "快照中没有文件！")
            
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(dialog, "错误", f"同步失败：{str(e)}")
    
    def sync_to_cloud(self):
        if not self.s3_client:
            QMessageBox.warning(self.iface.mainWindow(), "警告", "请先连接到MinIO！")
            return
        
        # 获取当前工程
        project = QgsProject.instance()
        project_path = project.fileName()
        
        if not project_path:
            # 如果项目未保存，提示用户保存
            reply = QMessageBox.question(
                self.iface.mainWindow(), 
                "提示", 
                "项目尚未保存，是否先保存项目？",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 调用QGIS的保存对话框
                if not self.iface.mainWindow().findChild(QAction, 'mActionSaveProject').trigger():
                    return
                project_path = project.fileName()
                if not project_path:
                    return
            else:
                return
        else:
            # 保存当前项目
            project.write()
        
        # 显示同步对话框
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("同步到云端")
        dialog.setGeometry(100, 100, 500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 同步选项
        sync_group = QGroupBox("同步选项")
        sync_layout = QVBoxLayout(sync_group)
        
        # 新建快照选项
        self.new_snapshot_radio = QRadioButton("创建新快照")
        self.new_snapshot_radio.setChecked(True)
        sync_layout.addWidget(self.new_snapshot_radio)
        
        # 覆盖现有快照选项
        self.overwrite_radio = QRadioButton("覆盖现有快照")
        sync_layout.addWidget(self.overwrite_radio)
        
        # 现有快照列表
        self.snapshot_list = QListWidget()
        self.snapshot_list.setSelectionMode(QListWidget.SingleSelection)
        sync_layout.addWidget(QLabel("选择要覆盖的快照："))
        sync_layout.addWidget(self.snapshot_list)
        
        # 填充快照列表
        self.list_snapshots_for_sync()
        
        layout.addWidget(sync_group)
        
        # 图层选择
        layers_group = QGroupBox("要同步的图层")
        layers_layout = QVBoxLayout(layers_group)
        
        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QListWidget.MultiSelection)
        
        # 填充图层列表
        for layer in project.mapLayers().values():
            item = QListWidgetItem(layer.name())
            item.setData(Qt.UserRole, layer)
            self.layer_list.addItem(item)
        
        layers_layout.addWidget(self.layer_list)
        layout.addWidget(layers_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        sync_btn = QPushButton("同步")
        sync_btn.clicked.connect(lambda: self.perform_sync_to_cloud(dialog, project_path))
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(sync_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def list_snapshots_for_sync(self):
        if not self.s3_client:
            return
        
        bucket = self.bucket_edit.text().strip()
        self.snapshot_list.clear()
        
        try:
            # 列出所有对象，包括子目录
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=self.snapshot_dir
            )
            
            # 收集所有快照目录
            snapshot_dirs = set()
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    # 提取快照目录路径
                    if key.startswith(self.snapshot_dir + '/'):
                        # 找到第一个子目录（快照目录）
                        parts = key.split('/')
                        if len(parts) > 2:
                            snapshot_dir = '/'.join(parts[:2]) + '/'
                            snapshot_dirs.add(snapshot_dir)
            
            # 添加快照目录到列表
            for snapshot_dir in sorted(snapshot_dirs):
                # 提取快照名称
                snapshot_name = snapshot_dir.replace(self.snapshot_dir + '/', '').rstrip('/')
                if snapshot_name:
                    item = QListWidgetItem(snapshot_name)
                    item.setData(Qt.UserRole, snapshot_dir)
                    self.snapshot_list.addItem(item)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "错误", f"获取快照列表失败：{str(e)}")
    
    def perform_sync_to_cloud(self, dialog, project_path):
        try:
            # 确保快照目录存在
            self.ensure_snapshot_directory()
            
            # 确定快照路径
            if self.new_snapshot_radio.isChecked():
                # 创建新快照
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                project_name = os.path.basename(project_path).replace('.qgz', '').replace('.qgs', '')
                snapshot_name = f"{project_name}_{timestamp}"
                snapshot_path = f"{self.snapshot_dir}/{snapshot_name}/"
            else:
                # 覆盖现有快照
                selected_items = self.snapshot_list.selectedItems()
                if not selected_items:
                    QMessageBox.warning(dialog, "警告", "请选择要覆盖的快照！")
                    return
                selected_item = selected_items[0]
                snapshot_path = selected_item.data(Qt.UserRole)
                snapshot_name = selected_item.text()
            
            # 收集要同步的文件
            files_to_sync = []
            
            # 检查工程文件
            project_key = f"{snapshot_path}{os.path.basename(project_path)}"
            if self.needs_sync(project_path, project_key):
                files_to_sync.append((project_path, project_key, "工程文件"))
            
            # 检查选中的图层文件
            selected_items = self.layer_list.selectedItems()
            for item in selected_items:
                layer = item.data(Qt.UserRole)
                if hasattr(layer, 'dataProvider') and hasattr(layer.dataProvider(), 'dataSourceUri'):
                    data_source = layer.dataProvider().dataSourceUri()
                    # 提取文件路径
                    if layer.type() == QgsMapLayer.VectorLayer:
                        # 矢量图层
                        if '|' in data_source:
                            file_path = data_source.split('|')[0]
                        else:
                            file_path = data_source
                    elif layer.type() == QgsMapLayer.RasterLayer:
                        # 栅格图层
                        file_path = data_source
                    else:
                        continue
                    
                    if os.path.exists(file_path):
                        # 检查是否是SHP文件
                        if file_path.lower().endswith('.shp'):
                            # 检查SHP文件及其所有相关子文件是否需要同步
                            shp_files = self.check_shp_files_needs_sync(file_path, snapshot_path)
                            files_to_sync.extend(shp_files)
                        else:
                            # 检查普通文件是否需要同步
                            layer_key = f"{snapshot_path}layers/{os.path.basename(file_path)}"
                            if self.needs_sync(file_path, layer_key):
                                files_to_sync.append((file_path, layer_key, "图层文件"))
            
            # 显示同步预览
            if not files_to_sync:
                QMessageBox.information(dialog, "提示", "没有文件需要同步！")
                dialog.accept()
                return
            
            # 显示同步预览对话框
            preview_dialog = QDialog(self.iface.mainWindow())
            preview_dialog.setWindowTitle("同步预览")
            preview_dialog.setGeometry(100, 100, 500, 400)
            
            preview_layout = QVBoxLayout(preview_dialog)
            
            # 文件列表
            preview_list = QListWidget()
            for file_path, file_key, file_type in files_to_sync:
                item = QListWidgetItem(f"{file_type}: {os.path.basename(file_path)}")
                preview_list.addItem(item)
            
            preview_layout.addWidget(QLabel("以下文件将被同步："))
            preview_layout.addWidget(preview_list)
            
            # 按钮布局
            preview_btn_layout = QHBoxLayout()
            proceed_btn = QPushButton("开始同步")
            cancel_btn = QPushButton("取消")
            preview_btn_layout.addWidget(proceed_btn)
            preview_btn_layout.addWidget(cancel_btn)
            preview_layout.addLayout(preview_btn_layout)
            
            # 连接信号
            proceed = False
            def on_proceed():
                nonlocal proceed
                proceed = True
                preview_dialog.accept()
            
            proceed_btn.clicked.connect(on_proceed)
            cancel_btn.clicked.connect(preview_dialog.reject)
            
            if preview_dialog.exec_() != QDialog.Accepted or not proceed:
                return
            
            # 执行同步
            total_files = len(files_to_sync)
            for i, (file_path, file_key, file_type) in enumerate(files_to_sync):
                self.upload_file_with_progress(file_path, file_key)
                # 更新进度
                progress = int((i + 1) / total_files * 100)
                self.progress_bar.setValue(progress)
            
            self.progress_bar.setValue(100)
            QMessageBox.information(dialog, "成功", "项目同步到云端成功！")
            self.iface.messageBar().pushSuccess("QGIS云端同步", "项目同步到云端成功！")
            # 添加同步历史记录
            self.add_sync_history("同步到云端", "成功", f"项目：{os.path.basename(project_path)}")
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(dialog, "错误", f"同步失败：{str(e)}")
            self.iface.messageBar().pushCritical("QGIS云端同步", f"同步失败：{str(e)}")
            # 添加同步历史记录
            self.add_sync_history("同步到云端", "失败", f"项目：{os.path.basename(project_path)}，错误：{str(e)}")
    
    def needs_sync(self, local_path, remote_key):
        """检查文件是否需要同步"""
        bucket = self.bucket_edit.text().strip()
        
        # 检查本地文件是否存在
        if not os.path.exists(local_path):
            return False
        
        # 获取本地文件的修改时间和大小
        local_mtime = os.path.getmtime(local_path)
        local_size = os.path.getsize(local_path)
        
        try:
            # 获取云端文件的信息
            response = self.s3_client.head_object(Bucket=bucket, Key=remote_key)
            # 获取云端文件的修改时间和大小
            remote_mtime = response['LastModified'].timestamp()
            remote_size = response['ContentLength']
            
            # 比较修改时间和大小
            if abs(local_mtime - remote_mtime) > 1 or local_size != remote_size:
                return True
            else:
                return False
        except ClientError as e:
            # 如果文件不存在，需要同步
            if e.response['Error']['Code'] == '404':
                return True
            else:
                raise e
    
    def check_shp_files_needs_sync(self, shp_file, snapshot_path):
        """检查SHP文件及其所有相关子文件是否需要同步"""
        files_to_sync = []
        # SHP相关文件扩展名
        shp_extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.fbn', '.fbx', '.ain', '.aih']
        
        # 获取SHP文件的基本路径（不含扩展名）
        base_path = os.path.splitext(shp_file)[0]
        
        # 检查所有相关文件
        for ext in shp_extensions:
            current_file = base_path + ext
            if os.path.exists(current_file):
                file_name = os.path.basename(current_file)
                layer_key = f"{snapshot_path}layers/{file_name}"
                if self.needs_sync(current_file, layer_key):
                    files_to_sync.append((current_file, layer_key, "SHP图层文件"))
        
        return files_to_sync
    
    def upload_shp_files(self, shp_file, snapshot_path):
        """上传SHP文件及其所有相关子文件"""
        files_to_sync = []
        # SHP相关文件扩展名
        shp_extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.fbn', '.fbx', '.ain', '.aih']
        
        # 获取SHP文件的基本路径（不含扩展名）
        base_path = os.path.splitext(shp_file)[0]
        
        # 上传所有相关文件
        for ext in shp_extensions:
            current_file = base_path + ext
            if os.path.exists(current_file):
                file_name = os.path.basename(current_file)
                layer_key = f"{snapshot_path}layers/{file_name}"
                self.upload_file_with_progress(current_file, layer_key)
                files_to_sync.append((current_file, layer_key, "SHP图层文件"))
        
        return files_to_sync
    
    def upload_file_with_progress(self, file_path, key):
        bucket = self.bucket_edit.text().strip()
        try:
            self.s3_client.upload_file(
                file_path, bucket, key,
                Callback=self.upload_progress_callback
            )
        except Exception as e:
            raise e
    
    def fix_project_layer_paths(self, project_file, save_dir):
        """修改工程文件中的图层路径为相对路径"""
        import xml.etree.ElementTree as ET
        
        try:
            # 解析工程文件
            tree = ET.parse(project_file)
            root = tree.getroot()
            
            # 命名空间
            namespaces = {
                'qgs': 'http://www.qgis.org/qgis'
            }
            
            # 找到所有图层元素
            layers = root.findall('.//qgs:maplayer', namespaces)
            
            for layer in layers:
                # 找到数据源元素
                datasource = layer.find('./qgs:datasource', namespaces)
                if datasource is not None and datasource.text:
                    # 获取原始数据源路径
                    original_path = datasource.text
                    file_path = original_path
                    
                    # 检查是否是file:///开头的路径
                    if original_path.startswith('file:///'):
                        # 移除file:///前缀
                        file_path = original_path[8:]
                        # 处理Windows路径（将/转换为\）
                        if ':' in file_path:
                            file_path = file_path.replace('/', '\\')
                    
                    # 检查是否是直接的本地路径
                    elif os.path.isabs(file_path) or (':' in file_path and '\\' in file_path):
                        # 这是一个本地路径
                        pass
                    
                    # 提取文件名
                    file_name = os.path.basename(file_path)
                    # 构建相对路径
                    relative_path = f"./layers/{file_name}"
                    # 更新数据源路径
                    datasource.text = relative_path
            
            # 保存修改后的工程文件
            tree.write(project_file, encoding='UTF-8', xml_declaration=True)
        except Exception as e:
            print(f"Failed to fix project layer paths: {str(e)}")
    
    def upload_progress_callback(self, *args):
        # 处理不同类型的参数
        if len(args) == 1:
            # 可能是字典或整数
            if isinstance(args[0], dict):
                progress = args[0]
                bytes_sent = progress.get('BytesTransferred', 0)
                total_bytes = progress.get('TotalBytes', 1)
            else:
                # 假设是已传输的字节数
                bytes_sent = args[0]
                total_bytes = 1  # 默认为1避免除零错误
        elif len(args) == 2:
            # 直接是字节数和总字节数
            bytes_sent, total_bytes = args
        else:
            return
        
        if total_bytes > 0:
            progress_percent = int((bytes_sent / total_bytes) * 100)
            self.progress_bar.setValue(progress_percent)
    
    def load_sync_history(self):
        """加载同步历史记录"""
        if os.path.exists(self.sync_history_file):
            try:
                with open(self.sync_history_file, 'r', encoding='utf-8') as f:
                    self.sync_history = json.load(f)
            except Exception as e:
                print(f"Failed to load sync history: {str(e)}")
                self.sync_history = []
    
    def save_sync_history(self):
        """保存同步历史记录"""
        try:
            with open(self.sync_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.sync_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save sync history: {str(e)}")
    
    def add_sync_history(self, operation, status, details):
        """添加同步历史记录"""
        history_item = {
            'timestamp': datetime.datetime.now().isoformat(),
            'operation': operation,
            'status': status,
            'details': details
        }
        self.sync_history.insert(0, history_item)  # 添加到开头
        # 只保留最近50条记录
        if len(self.sync_history) > 50:
            self.sync_history = self.sync_history[:50]
        self.save_sync_history()
    
    def show_sync_history(self):
        """显示同步历史记录"""
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("同步历史")
        dialog.setGeometry(100, 100, 600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 历史记录列表
        history_list = QListWidget()
        for item in self.sync_history:
            timestamp = item['timestamp']
            operation = item['operation']
            status = item['status']
            details = item['details']
            list_item = QListWidgetItem(f"{timestamp} - {operation} - {status}")
            list_item.setToolTip(details)
            history_list.addItem(list_item)
        
        layout.addWidget(history_list)
        
        # 按钮
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("清空历史")
        clear_btn.clicked.connect(lambda: self.clear_sync_history(dialog, history_list))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def clear_sync_history(self, dialog, history_list):
        """清空同步历史记录"""
        reply = QMessageBox.question(
            dialog, 
            "确认", 
            "确定要清空同步历史吗？",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.sync_history = []
            self.save_sync_history()
            history_list.clear()
    
    def save_config(self):
        if hasattr(self, 'endpoint_edit'):
            config = {
                'endpoint': self.endpoint_edit.text().strip(),
                'access_key': self.access_edit.text().strip(),
                'secret_key': self.secret_edit.text().strip(),
                'bucket': self.bucket_edit.text().strip(),
                'auto_save_enabled': self.auto_save_enabled,
                'auto_save_interval': self.auto_save_interval
            }
            
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Failed to save config: {str(e)}")
