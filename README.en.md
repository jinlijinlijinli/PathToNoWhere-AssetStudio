# PathToNoWhere AssetStudio

[简体中文](README.md) | English

An unofficial Windows toolkit for Path to Nowhere CN Android resources: Unity asset export, video downloads, game text export, and Live2D extraction.

This guide covers the **2026-11-11 update (client 2.5.2, resource version 10)**. You can use your own downloaded game data without an APK.

## Download and setup

Download the updated ZIP from [GitHub Releases](https://github.com/jinlijinlijinli/PathToNoWhere-AssetStudio/releases), extract it completely, and run the appropriate EXE. Keep DLLs and subfolders such as `_internal` next to it. GitHub's automatically generated source ZIP is not a runnable release.

Windows 10/11 x64 is supported. The AssetStudio desktop app requires the **.NET 6 Desktop Runtime (x64)**. The other standalone tools bundle their runtime dependencies.

## Video tutorial

[Watch the author's Bilibili tutorial (part 7)](https://www.bilibili.com/video/BV16nvQBYEZp/?p=7) (in Chinese).

## Prepare game data

Copy the downloaded game data from your phone or emulator. The usual root is `Android/data/com.zy.wqmt.cn/files`. Keep directories such as `fs`, `fstier1`, and `fschunk` together. In particular, the current Simplified Chinese text blocks are under `fstier1/blocks`. Use a separate output directory. A matching APK is optional; an APK by itself may omit updated or on-demand resources.

## Use the tools

- **AssetStudio** (`AssetStudioModGUI-PtN.exe`): Choose **File → Load folder**, select the game resource root, then filter and export assets. Use the updated build if you see `Invalid chunk header`; it handles the new 64-byte alignment padding.
- **Video downloader** (`无期迷途视频下载工具.exe`): Select `fs/res_media.json`, choose an output folder, and start downloading. Internet access is required. If you get repeated 404s, check the media base URL; the old 2.4 path may not match the manifest. Use your own playback log and the bundled advanced guide to identify the matching URL.
- **Text extractor** (`无期迷途文本提取工具.exe`): Select the root containing both `fs` and `fstier1` and leave the APK field blank. Choose story only, selected chapters, or all game text. Load the chapter list before selecting chapters. For all text, open the categorized reading folder and use the CSV index to search. The updated reader supports DPK1/DBC1. This data set yielded 606,920 text IDs and 63 chapter exports without an APK. Branches and options are retained; any unresolved fields are listed in the reports.
- **Live2D** (`无期迷途Live2D提取工具.exe`): Open the standalone app or the AssetStudio Live2D menu. Select the game resource root and an output location, load the character list, then select and extract characters. If an older extraction stopped at a chunk header error, use the Live2D build with the updated unpacker and select a fresh output folder.

For bug reports, include tool version, game version, input directory layout, and a sanitized error. Do not include private logs or game dumps.

## Source and licensing

`src/text` contains text tool source; `src/components` contains available scan and unpack components. Some older GUI builds are distributed as binaries only. Third-party licenses are retained in `licenses` and the release archives. The toolkit does not include game APKs or extracted game assets.
