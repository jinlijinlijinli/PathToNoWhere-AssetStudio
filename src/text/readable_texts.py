"""Readable views of every decoded table; preserve field paths and branch order."""
import csv
import json
from pathlib import Path


def rows(path):
    if path.is_file():
        with path.open(encoding='utf-8-sig') as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def fields(value, path=''):
    if isinstance(value, dict):
        for key, item in value.items():
            if '__text_id' not in key:
                yield from fields(item, f'{path}.{key}' if path else key)
    elif isinstance(value, list):
        for i, item in enumerate(value, 1):
            yield from fields(item, f'{path}[{i}]')
    elif isinstance(value, str) and value:
        yield path, value


def describe(row):
    # JSON retains numeric context, IDs, jumps and options without guessing a route.
    return json.dumps(row, ensure_ascii=False, indent=2)


def category(path):
    name=path.name
    if name=='trial.lua.jsonl': return '审查'
    if name=='month_sign_hero.lua.jsonl': return '情绪检测'
    if name.startswith('supervision_'): return '监管终端'
    if any(word in name for word in ('dialog','story','plot','chat')): return '剧情与对话'
    return '其他游戏文本'


def build(cache, destination, cancel, emit):
    from extract_ptn_texts import Cancelled
    def check():
        if cancel.is_set(): raise Cancelled()
    cache=Path(cache); destination=Path(destination)
    data=cache/'本地化配置表/data'
    root=destination/'全部文本阅读版';root.mkdir(parents=True,exist_ok=True)
    index=[];stats={};missing=[]
    emit('正在整理审查、情绪检测、监管终端及全部配置文本阅读版…')
    # Collect actual trial references first, then retain only the required dialogue rows.
    trials=list(rows(data/'trial.lua.jsonl'))
    wanted={step.get('EventCourseParam1') for row in trials for step in row.get('Steps',[])}
    dialogues={}
    for row in rows(data/'common_dialog.lua.jsonl'):
        check()
        if row.get('ID') in wanted: dialogues[row['ID']]=row
    with (root/'文本索引.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['分类','来源表','记录ID','字段路径','文本'])
        for path in sorted(data.rglob('*.jsonl')):
            check();relative=path.relative_to(data);cat=category(path)
            target=root/cat/relative.with_suffix('.txt')
            target.parent.mkdir(parents=True,exist_ok=True)
            count=0;records=0
            with target.open('w',encoding='utf-8-sig') as out:
                out.write(f'来源：data/{relative.as_posix()}\n按原始记录和字段顺序列出全部非空字符串；保留字段路径便于核对原表。\n')
                if '.partial.' in path.name:out.write('【此表未完整解析，请同时查看原始字符串与提取错误报告】\n')
                for row in rows(path):
                    check();records+=1;ident=row.get('ID',records)
                    out.write(f'\n===== 记录 {ident} =====\n')
                    for field,text in fields(row):
                        count+=1;out.write(f'[{field}]\n{text}\n')
                        writer.writerow([cat,relative.as_posix(),ident,field,text])
            index.append({'分类':cat,'来源表':relative.as_posix(),'记录数':records,'字符串字段数':count,'文件':target.relative_to(root).as_posix()})
            stats[cat]=stats.get(cat,0)+count
    # Standalone records retain all context; trial views additionally resolve dialogue IDs.
    for name,cat in [('trial','审查'),('month_sign_hero','情绪检测'),('supervision_event','监管终端')]:
        folder=root/cat/'逐条阅读';folder.mkdir(parents=True,exist_ok=True)
        for row in rows(data/(name+'.lua.jsonl')):
            check();ident=row['ID']
            with (folder/f'{ident}.txt').open('w',encoding='utf-8-sig') as out:
                out.write(f'{cat} / ID {ident}\n来源：data/{name}.lua\n保留全部选项、分支和字段。数字角色 ID 不猜测为角色名。\n\n')
                if name!='trial':
                    out.write(describe(row));continue
                out.write(describe({k:v for k,v in row.items() if k!='Steps'}))
                for step in row.get('Steps',[]):
                    out.write(f'\n\n===== 审查步骤 {step.get("StepID")} =====\n'+describe(step)+'\n')
                    ref=step.get('EventCourseParam1')
                    if ref in dialogues:
                        out.write(f'\n【关联 common_dialog ID {ref}】\n')
                        for d in dialogues[ref].get('Data',[]):
                            keep={k:d[k] for k in ['Step','Name','Content','FemaleContent','OptionContent','Jump','IsFalseOption'] if k in d}
                            if any(d.get(k) for k in ['Content','FemaleContent','OptionContent']):out.write(describe(keep)+'\n')
                    elif step.get('EventCourse') in (1,2,3) and ref:
                        missing.append({'trialId':ident,'step':step.get('StepID'),'eventCourse':step.get('EventCourse'),'reference':ref})
    # Provide a readable UI dictionary too; no category is restricted to a keyword filter.
    ui=cache/'界面与系统文本.json'
    if ui.is_file():
        obj=json.loads(ui.read_text(encoding='utf-8-sig'))
        with (root/'界面与系统文本.txt').open('w',encoding='utf-8-sig') as out:
            for field,text in fields(obj):out.write(f'[{field}]\n{text}\n\n')
    with (root/'分类目录.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['分类','来源表','记录数','字符串字段数','文件'])
        writer.writeheader();writer.writerows(index)
    report={'tables':len(index),'stringFieldsByCategory':stats,'trialRecords':len(trials),'linkedTrialDialogues':len(dialogues),'unmatchedTrialParametersForReview':missing}
    (root/'阅读版整理报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'先读我.txt').write_text('审查、情绪检测、监管终端可分别打开同名目录中的“逐条阅读”。\n其他所有已解码配置表均有 TXT 阅读版，不按关键词丢弃文本。\n“文本索引.csv”可搜索所有表的字符串字段；“分类目录.csv”列出来源和条数。\n审查关联保留 Step、选项和 Jump，不替玩家选择路线。EventCourseParam1 命中对话表时展开；数字参数也可能用于其他事件，原始步骤同时保留供核对。\n未完整解码配置的文字还应查看导出根目录“字符串常量”及“中文去重文本.txt”。\n原始表、脚本常量与 Unity 文本仍保留在导出根目录；本阅读版不替代原始资源。\n',encoding='utf-8-sig')
    return report
