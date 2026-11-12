# PathToNoWhere AssetStudio

《无期迷途》国服 Android 资源工具合集，支持 Unity 资源浏览与导出、视频下载、游戏文本导出和 Live2D 提取。本项目为非官方工具。

## 下载与安装

前往 [GitHub Releases](https://github.com/jinlijinlijinli/PathToNoWhere-AssetStudio/releases)，下载所需工具的 ZIP 压缩包，完整解压后双击对应的 EXE。

| 工具 | 启动文件 |
| --- | --- |
| AssetStudio PtN Fix | `AssetStudioModGUI_PtN_fix_2026-11-11.exe` |
| 视频下载工具 | `无期迷途视频下载工具.exe` |
| 文本提取工具 | `无期迷途文本提取工具.exe` |
| Live2D 提取工具 | `无期迷途Live2D提取工具.exe` |

AssetStudio 主程序需要 **.NET 6 Desktop Runtime（x64）**。请确认安装的是带有 **Desktop** 字样的版本。其余独立工具已随附运行环境。

## 准备游戏数据和 APK

1. 在游戏内下载所需资源，然后将手机或模拟器里的 `Android/data/com.zy.wqmt.cn/files` 文件夹完整复制到电脑。
2. 打开[《无期迷途》官网](https://wqmt.aisnogames.com/)，点击「安卓下载」，下载与游戏数据对应版本的 APK 安装包。
3. 在电脑上新建一个文件夹，把 `files` 文件夹和 APK 放进去。APK 保留原文件即可。

   ```text
   无期迷途游戏资源/
   ├─ files/
   │  ├─ fs/
   │  └─ fschunk/
   └─ offcialweb.apk
   ```

## 工具使用方法

### AssetStudio｜浏览和导出 Unity 资源

1. 打开 AssetStudio，选择 **File → Load folder**。
2. 选择上面新建的文件夹，等待资源加载完成。
3. 在资源列表中按类型筛选，或搜索资源名称，再导出所需资源。

### 视频下载工具

1. 从 `files/fs/` 找到 `res_media.json`，可与 APK 放在同一个文件夹里，方便选择。
2. 打开视频下载工具，点击 **「选择 APK / 清单文件」**，选择 `res_media.json` 或 APK，再选择视频保存位置。
3. 如果需要从游戏播放日志获取视频地址，在「地址设置」中点击 **「如何获取日志」**，按提示操作。
4. 点击 **「从播放日志识别」**，载入生成的日志文件。
5. 点击 **「开始下载」**。

### Live2D 提取工具

1. 双击 `无期迷途Live2D提取工具.exe`，也可以从 AssetStudio 的 **「Live2D 工具」** 菜单进入。
2. 在「游戏文件夹」中选择前面新建的目录，也就是同时包含 `files` 和 APK 的那一层。然后选择保存位置。
3. 点击 **「读取角色列表」**，等待读取完成。
4. 搜索并勾选所需模型，点击 **「提取所选角色」**。

首次读取需要整理游戏资源，耗时取决于文件大小。「工作数据」用于存放缓存，导出的模型位于「提取好的模型」。如果之前已经读取过同一份游戏数据，后来才补放 APK，请选择一个新的保存位置，再读取角色列表，让工具重新建立包含 APK 的索引。
