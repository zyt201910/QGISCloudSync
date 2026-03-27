# QGIS Cloud Sync Plugin

QGIS云端同步插件，支持保存工程文件快照和数据图层文件到MinIO存储桶。

## 功能特性

- 连接到MinIO存储服务
- 手动保存QGIS工程文件快照
- 可选保存数据图层文件
- 自动保存功能（可设置保存间隔）
- 在MinIO存储桶中自动创建快照目录结构

## 安装方法

1. 确保已安装Python依赖：
   - boto3
   - botocore
2. 复制插件目录到QGIS插件目录：
   - Windows: `C:\Users\<用户名>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`
3. 在QGIS中启用插件：
   - 打开QGIS
   - 进入「插件」→「管理并安装插件...」
   - 在「已安装」标签页中找到「QGIS Cloud Sync」并勾选启用

## 使用方法

1. **连接到MinIO**：
   - 点击工具栏中的「Connect to MinIO」按钮
   - 填写MinIO服务器的Endpoint、AccessKey、SecretKey和Bucket名称
   - 点击「Test Connection」测试连接
   - 连接成功后，「Save Project Snapshot」按钮将被启用
2. **手动保存快照**：
   - 确保QGIS工程已保存
   - 点击工具栏中的「Save Project Snapshot」按钮
   - 在弹出的对话框中，选择要包含的图层文件
   - 点击「Save」按钮保存快照
3. **配置自动保存**：
   - 点击工具栏中的「Settings」按钮
   - 勾选「Enable Auto Save」启用自动保存
   - 设置保存间隔（分钟）
   - 点击「OK」保存设置

## 快照存储结构

在MinIO存储桶中，快照将按照以下结构存储：

```
qgis_snapshots/
  └── <工程名>_<时间戳>/
      ├── <工程文件名>
      └── layers/
          └── <图层文件名>
```

## 注意事项

- 确保MinIO服务器可访问
- 确保存储桶存在且具有写入权限
- 首次使用时，插件会自动在存储桶中创建`snapshots`目录
- 自动保存仅在QGIS工程已保存的情况下工作
- 图层文件必须是本地文件，远程图层（如WMS/WFS）不会被保存

## 依赖项

- Python 3.6+
- QGIS 3.0+
- boto3
- botocore

## 故障排除

- **连接失败**：检查MinIO服务器地址、端口、AccessKey和SecretKey是否正确
- **保存失败**：检查存储桶权限和网络连接
- **自动保存不工作**：确保QGIS工程已保存，且自动保存功能已启用

## 许可证

CC0 License
