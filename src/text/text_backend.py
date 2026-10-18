"""Local input preparation, cache and export orchestration for the desktop UI."""
import csv
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

import extract_ptn_texts as extractor
import organize_ptn_dialogues as organizer
import readable_texts

VERSION='1.0.0-full-prototypes'
HOME=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))


def inputs(folder,apk):
    folder=Path(folder).expanduser().resolve() if folder else None
    apk=Path(apk).expanduser().resolve() if apk else None
    if folder and not folder.is_dir():
        raise ValueError('游戏数据目录不存在。')
    if apk and not apk.is_file():
        raise ValueError('APK 文件不存在。')
    if not apk and folder:
        candidates=list(folder.glob('*.apk'))
        if len(candidates)==1:
            apk=candidates[0]
    fs=extractor.find_fs(folder)
    if not fs and not apk:
        raise ValueError('未找到 files/fs/blocks。请选择 com.zy.wqmt.cn、files 或 fs 目录，或单独选择 APK。')
    return folder,fs,apk


def signature(folder,fs,apk):
    digest=hashlib.sha256(VERSION.encode())
    for path in [p for p in [fs/'res_manifest' if fs else None,apk] if p]:
        stat=path.stat()
        digest.update(str(path).encode('utf-8'))
        digest.update(str((stat.st_size,stat.st_mtime_ns)).encode())
        if path.name=='res_manifest':
            digest.update(path.read_bytes())
    if fs:
        tracked=[]
        for directory in [fs,fs.parent/'fsclassify',fs.parent/'fstier1',fs.parent/'fstier2',fs.parent/'fschunk']:
            if directory.exists():
                tracked.extend(p for p in directory.rglob('*') if p.is_file() and (p.suffix in ('.bundle','.bin') or 'bin/Data' in str(p).replace('\\','/')))
        for path in sorted(tracked):
            stat=path.stat()
            digest.update(str((str(path),stat.st_size,stat.st_mtime_ns)).encode('utf-8'))
    return digest.hexdigest()[:20]


def read_json(path,default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def chapters(cache):
    with (cache/'剧情目录.csv').open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def check(cancel):
    if cancel.is_set():
        raise extractor.Cancelled()


def analyze(folder,apk,output,cancel,emit):
    folder,fs,apk=inputs(folder,apk)
    output=Path(output).expanduser().resolve()
    output.mkdir(parents=True,exist_ok=True)
    cache=output/'工作缓存'/signature(folder,fs,apk)
    cache.mkdir(parents=True,exist_ok=True)
    marker=cache/'cache-ready.json'
    if read_json(marker,{}).get('version')==VERSION and (cache/'剧情目录.csv').is_file():
        emit('已读取此前解析结果，无需重复解析。')
    else:
        emit('正在解析游戏文本；首次解析可能需要几分钟。')
        game=folder if folder else apk.parent/'__apk_only_input__'
        extractor.main(game=game,output=cache,apk=apk,on_progress=emit,cancel=cancel)
        check(cancel)
        emit('正在按游戏回顾目录整理章节…')
        organizer.main(output=cache,on_progress=emit,cancel=cancel)
        marker.write_text(json.dumps({'version':VERSION,'input':str(folder or ''),'apk':str(apk or '')},ensure_ascii=False),encoding='utf-8')
    check(cancel)
    return {'cache':cache,'folder':folder,'fs':fs,'apk':apk,'chapters':chapters(cache),'report':read_json(cache/'提取报告.json',{})}


def native_scan(analysis,cancel,emit):
    cache=analysis['cache']
    folder=cache/'Unity文本'
    marker=folder/'扫描完成.json'
    if marker.is_file():
        emit('Unity 文本已扫描，使用已有结果。')
        return read_json(folder/'Unity扫描报告.json',{})
    native=next((p for p in [BUNDLE/'native/PtnTextScan.dll',HOME/'_internal/native/PtnTextScan.dll',HOME.parent/'_internal/native/PtnTextScan.dll',HOME.parent/'tools/PtnTextScan/build/PtnTextScan.dll'] if p.is_file()),BUNDLE/'native/PtnTextScan.dll')
    runtime=next((p for p in [BUNDLE/'runtime/dotnet.exe',HOME/'_internal/runtime/dotnet.exe',HOME.parent/'_internal/runtime/dotnet.exe',HOME.parent/'.tools/portable-dotnet/dotnet.exe'] if p.is_file()),BUNDLE/'runtime/dotnet.exe')
    if not runtime.is_file() or not native.is_file():
        raise ValueError('缺少内置扫描组件。请完整解压工具包，不要只复制 EXE。')
    command=[str(runtime),str(native),str(analysis['fs'].parent) if analysis['fs'] else '-',str(folder)]
    if analysis['apk']:
        command.append(str(analysis['apk']))
    emit('正在扫描 Unity TextAsset 与界面文本；此步骤可能较慢，可随时停止。')
    folder.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env['DOTNET_ROOT']=str(runtime.parent)
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    pending=queue.Queue()
    def read():
        for line in proc.stdout:
            pending.put(line.strip())
    reader=threading.Thread(target=read,daemon=True)
    reader.start()
    try:
        with (folder/'扫描执行日志.txt').open('w',encoding='utf-8') as log:
            while proc.poll() is None or not pending.empty():
                check(cancel)
                try:
                    line=pending.get(timeout=.2)
                    log.write(line+'\n');log.flush()
                    if line:emit(line)
                except queue.Empty:
                    pass
        reader.join(timeout=2)
        report=read_json(folder/'Unity扫描报告.json')
        if proc.returncode not in (0,2) or report is None:
            raise ValueError('Unity 扫描未完成，请查看工作缓存中的扫描执行日志。')
        marker.write_text(json.dumps({'version':VERSION}),encoding='utf-8')
        return report
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill()


def copy_tree(source,target,cancel,exclude=()):
    if not source.exists():
        return
    for path in source.rglob('*'):
        check(cancel)
        relative=path.relative_to(source)
        if any(part in exclude for part in relative.parts):
            continue
        if path.is_file():
            dest=target/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest)


def export(analysis,output,mode,selected,cancel,emit):
    check(cancel)
    cache=analysis['cache']
    native_report=native_scan(analysis,cancel,emit) if mode=='all' else None
    prefix={'plot':'全部剧情','chapters':'所选章节','all':'全部文本'}[mode]
    destination=Path(output)/f'{prefix}_{time.strftime("%Y%m%d_%H%M%S")}'
    number=1
    while destination.exists():
        destination=Path(output)/f'{prefix}_{time.strftime("%Y%m%d_%H%M%S")}_{number}'
        number+=1
    destination.mkdir(parents=True)
    chapter_rows=[r for r in analysis['chapters'] if mode!='chapters' or r['回顾ID'] in selected]
    if mode=='chapters' and not chapter_rows:
        raise ValueError('请至少勾选一个章节。')
    emit(f'正在导出 {len(chapter_rows)} 个章节…')
    chapter_folder=destination/'剧情按章节'
    chapter_folder.mkdir()
    for row in chapter_rows:
        check(cancel)
        source=(cache/'剧情按章节'/row['文件']).resolve()
        if source.parent!=(cache/'剧情按章节').resolve():
            raise ValueError('章节路径无效')
        shutil.copy2(source,chapter_folder/source.name)
    with (destination/'剧情目录.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(analysis['chapters'][0]))
        writer.writeheader();writer.writerows(chapter_rows)
    readable_report=None
    if mode=='all':
        readable_report=readable_texts.build(cache,destination,cancel,emit)
        for directory in ['剧情对话','本地化配置表','字符串常量','原始脚本字节码','Unity文本']:
            emit('正在保存：'+directory)
            copy_tree(cache/directory,destination/directory,cancel,exclude=('_工作文件',))
        for file in ['中文文本ID对照.jsonl','中文去重文本.txt','界面与系统文本.json','来源索引.json','配置表索引.json']:
            shutil.copy2(cache/file,destination/file)
    elif mode=='plot':
        copy_tree(cache/'剧情对话',destination/'全部对话分卷',cancel)
        for path in (cache/'本地化配置表/data').rglob('*.jsonl'):
            if any(part in path.name.lower() for part in ['dialog','story','plot','talk','chat']):
                check(cancel)
                dest=destination/'剧情相关配置表'/path.relative_to(cache/'本地化配置表/data')
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    for file in ['提取报告.json','提取错误.json','未解析文本ID.json','剧情整理报告.json']:
        if (cache/file).exists():shutil.copy2(cache/file,destination/file)
    missing=read_json(cache/'剧情整理报告.json',{}).get('missingReviewTalkReferences',[])
    relevant_missing=[m for m in missing if str(m['reviewId']) in {r['回顾ID'] for r in chapter_rows}]
    issues={'configurationErrors':analysis['report'].get('errors',0),'unresolvedTextIds':analysis['report'].get('unresolvedTextIds',0),'missingChapterTalkReferences':len(relevant_missing),'unityErrors':(native_report or {}).get('errors',0)}
    result={'mode':mode,'chapters':len(chapter_rows),'directory':str(destination.resolve()),'inputReport':analysis['report'],'unityReport':native_report,'readableReport':readable_report,'issues':issues,
            'scope':'导出所提供游戏文件中已支持格式的文本，不保证覆盖未下载、其他语言或历史版本资源。'}
    (destination/'导出摘要.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'从这里开始.txt').write_text('全量导出请优先打开“全部文本阅读版”：审查、情绪检测、监管终端有独立目录，其他配置表也有 TXT。通过文本索引.csv 搜索所有表的文字。\n剧情可打开“剧情按章节”或“剧情目录.csv”。\n剧情保留说话人、原文、FemaleContent 分支和选项。游戏富文本标签不擅自修改。\n“全部剧情”还包含回顾目录以外的对话分卷和剧情相关配置表。\n“全部文本”包含字符串池、嵌套函数字符串、原始脚本字节码、已支持的本地化配置表，以及 Unity TextAsset / 界面文本。\n原始脚本 .luac 和 TextAsset .bytes 可能是二进制，不是可直接阅读的文本。\n本次存在的缺失、未解析项见“导出摘要.json”和提取报告；.partial.jsonl 是未完整解码的配置表。\n部分非文字配置字段尚未完全适配，不能将这些 JSON 当作游戏全部逻辑的准确复原。\n',encoding='utf-8')
    emit('导出结束：'+str(destination))
    return result
