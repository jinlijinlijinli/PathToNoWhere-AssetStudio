# PathToNoWhere AssetStudio

English | [简体中文](README.md)

Unofficial Windows tools for Path to Nowhere CN Android resources: a patched AssetStudio, video downloader, game text exporter, and Live2D extraction/processing tools. Not affiliated with the game publisher.

## Download

Open **Releases**, download the ZIP you need, extract the entire archive, then run its EXE. Keep all DLLs and `_internal` folders. The repository source ZIP is not an application release. Windows 10/11 x64 only.

| Archive | Purpose | Entry point |
| --- | --- | --- |
| AssetStudioModGUI_PtN_fix.zip | Browse/export supported Unity resources; integrated Live2D menu | AssetStudioModGUI-PtN.exe |
| PtN-Video-Downloader.zip | Download videos using your APK/media manifest | 无期迷途视频下载工具.exe |
| PtN-Text-Extractor.zip | Stories, interrogations, emotion checks, supervision and other text | 无期迷途文本提取工具.exe |
| PtN-Live2D-Tools.zip | Extract/process Live2D models by character | 无期迷途Live2D提取工具.exe |

The AssetStudio main application requires .NET 6 Desktop Runtime for Windows x64. Standalone tools bundle their runtime dependencies. The current interfaces are primarily Chinese.

## Input files

Provide your own matching APK and downloaded game data. The usual data location is `Android/data/com.zy.wqmt.cn/files`, containing `fs`, `fsclassify`, `fschunk`, etc. No APK, game models, textures, text or videos are included. An APK alone may lack downloaded content and updates.

## Quick start

**AssetStudio:** Load files/folders from the File menu, wait for parsing, filter assets and export them. Use the Live2D menu for the integrated extractor. Choose a separate output directory.

**Videos:** Select an APK or `res_media.json`, choose an output directory, then start downloading. Internet is required. The default CDN path may stop working after updates; configure a matching address or identify it from your own playback log. See the bundled advanced guide for log collection. Remove account/device/connection information before sharing logs. A manifest does not necessarily include every historical video.

**Text:** Select the data folder, add the matching APK, choose the recommended all-text mode, and export. Open `全部文本阅读版` for categorized readable text. Interrogation files in `审查/逐条阅读` include linked character story dialogue, options and diaries; filenames may use numeric IDs. `文本索引.csv` indexes decoded configuration strings. For selected chapters, load the chapter list first, search and select chapters, then export. Raw tables, script strings and Unity text are also retained. Some tables are partially decoded; consult reports. Missing downloads and server-only text cannot be recovered. Branches and jump information are preserved without choosing a route.

**Live2D:** Select the folder containing `fs` and related directories, choose output, load the character list, select characters and extract. An extract-all option is available. Initial indexing may take time. Read the bundled quick-start instructions for processing. Compatibility with every external player is not guaranteed.

## Troubleshooting

- Missing resources: finish in-game downloads and use matching APK/data versions.
- Missing dependencies: extract the whole ZIP; check the AssetStudio desktop runtime.
- Missing text: inspect error, unresolved-ID and organization reports; partial tables are incomplete.
- Bug reports: include tool version, steps and sanitized errors. Do not upload private logs, account data or full game dumps.

## Source and licensing

`src/text` contains the text tool source. `src/components` contains custom components available in this workspace. Source for some older GUIs was not found; their binaries are supplied through Releases. This is not a fully rebuildable mirror of every upstream component.

Third-party components retain their original licenses; see `licenses` and the release archives. Live2D/Cubism components remain subject to their original terms. Game assets belong to their respective rights holders. This repository does not distribute game assets or bypass account access controls.
