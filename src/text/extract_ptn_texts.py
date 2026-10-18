"""Extract strings and localize data-table text IDs from the supplied game files."""
import csv
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile
from ptn_text_format import Reader, unwrap, readable, literal_tables

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT/'com.zy.wqmt.cn'
OUT = ROOT/'游戏文本提取'
TRANSLATE = bytes.maketrans(bytes(range(256)), bytes(i ^ 0x65 for i in range(256)))
HAN = re.compile(r'[\u3400-\u9fff]')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def primitive(value):
    if isinstance(value, bytes):
        text = readable(value)
        return text if text is not None else {'binaryBytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        return {str(primitive(k)):primitive(v) for k,v in value.items()}
    if isinstance(value, list):
        return [primitive(v) for v in value]
    return value


def item(column, index, default=0):
    if isinstance(column,list):
        return column[index] if 0 <= index < len(column) else default
    if isinstance(column,dict):
        return column.get(index+1,default)
    return default


class Cancelled(BaseException):
    pass


def find_fs(game):
    if not game:
        return None
    game = Path(game)
    for candidate in [game/'files/fs',game/'fs',game]:
        if (candidate/'blocks').is_dir() or (candidate/'res_manifest').is_file():
            return candidate
    return None


def main(game=None, output=None, apk=None, on_progress=None, cancel=None):
    global GAME, OUT
    if game is not None:
        GAME = Path(game)
    if output is not None:
        OUT = Path(output)
    OUT.mkdir(parents=True,exist_ok=True)
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise Cancelled()
    def emit(message):
        if on_progress:
            on_progress(message)
        else:
            print(message,flush=True)
    source_rows = []
    errors = []
    texts = {}
    fs = find_fs(GAME)
    if apk is None and GAME.exists():
        found = list(GAME.glob('*.apk'))
        if len(found)==1:
            apk = found[0]
    archive = zipfile.ZipFile(apk) if apk else None
    zip_names = set(archive.namelist()) if archive else set()
    manifest = (fs/'res_manifest').read_bytes() if fs and (fs/'res_manifest').is_file() else archive.read('assets/res_manifest') if archive and 'assets/res_manifest' in zip_names else b''
    manifest_paths = {v.decode().lstrip('/') for v in re.findall(rb'/blocks/[0-9a-f]{2}/[0-9a-f]{16}\.bundle',manifest)}
    candidates = {str(p.relative_to(fs)).replace('\\','/') for p in (fs/'blocks').rglob('*.bundle')} if fs else set()
    candidates.update(n.removeprefix('assets/') for n in zip_names if n.startswith('assets/blocks/') and n.endswith('.bundle'))
    files = sorted(manifest_paths or candidates)
    input_block_count = len(files)
    if not files:
        raise ValueError('没有找到 blocks 资源。请选择含 files/fs 的游戏目录，或提供有效 APK。')
    emit(f'发现 {len(files)} 个文本资源块，开始解析。')
    extracted = []
    if '--reuse' in sys.argv and (OUT/'来源索引.json').exists():
        source_rows = json.loads((OUT/'来源索引.json').read_text(encoding='utf-8'))
        extracted = [r for r in source_rows if r.get('status') in ('parsed-main-prototype','parsed-all-prototypes')]
        files = []
    for number,relative in enumerate(files):
        check_cancel()
        path = fs/relative if fs else None
        try:
            if path and path.exists():
                raw = path.read_bytes()
                source = str(path.resolve())
            elif 'assets/'+relative in zip_names:
                raw = archive.read('assets/'+relative)
                source = str(Path(apk).resolve())+'!assets/'+relative
            else:
                raise FileNotFoundError(relative)
            data = raw.translate(TRANSLATE)
            for entry,offset,chunk in unwrap(data):
                check_cancel()
                if not chunk.startswith(b'\x1bXX\x07'):
                    source_rows.append({'source':source,'entry':entry,'status':'not-XX','bytes':len(chunk)})
                    continue
                sources = re.findall(rb'@[A-Za-z0-9_./-]+\.lua',chunk)
                internal = sources[-1].decode().lstrip('@') if sources else 'unknown/'+Path(relative).stem+'_'+str(entry)+'.lua'
                # Never use untrusted source paths outside the output folder.
                if any(part in ('..','') for part in internal.split('/')):
                    raise ValueError('Unsafe internal source path')
                target = OUT/'原始脚本字节码'/(internal+'c')
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists() and target.read_bytes()!=chunk:
                    target = target.with_name(target.stem+'_'+hashlib.sha256(chunk).hexdigest()[:10]+target.suffix)
                target.write_bytes(chunk)
                prototypes = Reader(chunk).functions()
                code,constants = prototypes[0]['code'],prototypes[0]['constants']
                string_path = OUT/'字符串常量'/target.relative_to(OUT/'原始脚本字节码').with_suffix('.strings.jsonl')
                string_path.parent.mkdir(parents=True,exist_ok=True)
                count = chinese = 0
                with string_path.open('w',encoding='utf-8') as stream:
                    for prototype in prototypes:
                        for constant in prototype['constants']:
                            text = readable(constant['value'])
                            if not text:
                                continue
                            count += 1
                            chinese += bool(HAN.search(text))
                            stream.write(json.dumps({'prototypeIndex':prototype['prototypeIndex'],'constantIndex':constant['index'],'offsetInChunk':constant['offset'],'text':text},ensure_ascii=False)+'\n')
                record = {'source':source,'entry':entry,'offsetInDecodedBlock':offset,'internalSource':internal,'chunk':str(target.relative_to(OUT)),
                          'strings':count,'chineseStrings':chinese,'prototypes':len(prototypes),'status':'parsed-all-prototypes','sha256':hashlib.sha256(chunk).hexdigest()}
                source_rows.append(record)
                extracted.append(record)
        except Exception as exc:
            errors.append({'source':relative,'error':str(exc)})
        if number % 150 == 0:
            emit(f'解析资源块 {number+1}/{len(files)}，当前错误 {len(errors)}。')
    if archive:
        archive.close()
    write_json(OUT/'来源索引.json',source_rows)
    write_json(OUT/'提取错误.json',errors)

    def parse(record):
        chunk = (OUT/record['chunk']).read_bytes()
        code, constants = Reader(chunk).main()
        tables,diagnostics = literal_tables(code,constants)
        return constants,tables,diagnostics

    language = next((r for r in extracted if r['internalSource']=='data/lang/zh-hans/configtexts.lua'),None)
    if language is None:
        raise ValueError('缺少可解析的简体中文 configtexts.lua。请补充同版本 APK，或查看提取错误.json。')
    check_cancel()
    emit('正在还原中文文本 ID 与原文…')
    constants,tables,_ = parse(language)
    arrays = [c['value'] for c in constants if isinstance(c['value'],bytes) and len(c['value'])>1000000]
    ids_bytes,index_bytes = arrays[:2]
    ids = [v[0] for v in struct.iter_unpack('<Q',ids_bytes)]
    indexes = [v[0] for v in struct.iter_unpack('<I',index_bytes)]
    dictionary = max(tables,key=len)
    assert len(ids)==len(indexes) and max(indexes)==len(dictionary)
    assert all(isinstance(dictionary[i],bytes) for i in range(1,len(dictionary)+1))
    decoded_dictionary = {key:value.decode('utf-8') for key,value in dictionary.items()}
    assert len(set(ids))==len(ids)
    texts = dict(zip(ids,(decoded_dictionary[i] for i in indexes)))
    with (OUT/'中文文本ID对照.jsonl').open('w',encoding='utf-8') as stream:
        for ident,text in texts.items():
            stream.write(json.dumps({'id':str(ident),'text':text},ensure_ascii=False)+'\n')
    with (OUT/'中文去重文本.txt').open('w',encoding='utf-8') as stream:
        for index,text in decoded_dictionary.items():
            stream.write(f'【字符串 {index}】\n{text}\n\n')

    ui_record = next(r for r in extracted if r['internalSource']=='data/lang/zh-hans/texts.lua')
    _,ui_tables,_ = parse(ui_record)
    ui_table = max((t for t in ui_tables if any(isinstance(k,bytes) for k in t)),key=len)
    ui = {k.decode('utf-8'):v.decode('utf-8') for k,v in ui_table.items() if isinstance(k,bytes) and isinstance(v,bytes)}
    write_json(OUT/'界面与系统文本.json',ui)

    unresolved = set()
    def localize(value):
        if value in (None,0):
            return ''
        if value in texts:
            return texts[value]
        unresolved.add(value)
        return '[未解析文本ID:'+str(value)+']'

    views = {}
    def column(columns,index):
        return columns.get(index) if isinstance(columns,dict) else item(columns,index-1,None)

    def value_at(values,row,count):
        if row < 0:
            return 0
        float_boundaries = None
        if isinstance(values,list) and len(values)!=count and len(values)%2==0 and values and isinstance(values[-2],float):
            for fmt,integer in [('f','I'),('d','Q')]:
                try:
                    if struct.unpack('<'+integer,struct.pack('<'+fmt,values[-2]))[0]==count:
                        float_boundaries = [struct.unpack('<'+integer,struct.pack('<'+fmt,v))[0] for v in values[::2]]
                        break
                except (OverflowError,struct.error):
                    pass
        if isinstance(values,list) and len(values)!=count and len(values)%2==0 and values and (values[-2]==count or float_boundaries is not None):
            key = (id(values),count)
            if key not in views:
                ends = float_boundaries if float_boundaries is not None else values[::2]
                if not all(isinstance(x,(int,float)) for x in ends) or not all(a<b for a,b in zip(ends,ends[1:])):
                    raise ValueError('Invalid run-length column')
                views[key] = ends
            return values[2*bisect.bisect_left(views[key],row+1)+1]
        return item(values,row)

    def decode_row(columns,meta,row_index,row_count,depth=0):
        if depth>5:
            raise ValueError('Nested table too deep')
        output = {}
        for key,desc in meta.items():
            field = key.decode('utf-8')
            index = desc[b'index']
            value = value_at(column(columns,index),row_index,row_count)
            if desc.get(b'isSubSheet'):
                end = int(value)
                begin = int(value_at(column(columns,index),row_index-1,row_count)) if row_index else 0
                child_count = int(value_at(column(columns,index),row_count-1,row_count))
                output[field] = [decode_row(column(columns,index+1),desc[b'meta'],i,child_count,depth+1) for i in range(begin,end)]
                continue
            if desc.get(b'isRepeated'):
                pointer = int(value)
                end = int(item(column(columns,index+1),pointer-1)) if pointer else 0
                begin = int(item(column(columns,index+1),pointer-2)) if pointer>1 else 0
                values = [item(column(columns,index+2),i) for i in range(begin,end)]
                if desc.get(b'isText'):
                    output[field+'__text_ids'] = [str(v) for v in values]
                    values = [localize(v) for v in values]
                output[field] = primitive(values)
            else:
                if desc.get(b'dictZip'):
                    value = item(column(columns,index+1),int(value)-1) if value else ''
                if desc.get(b'isText'):
                    output[field+'__text_id'] = str(value)
                    value = localize(value)
                output[field] = primitive(value)
        return output

    table_reports = []
    dialogue_count = 0
    # Decode tables containing explicit text metadata; preserve others as raw chunks/constants.
    for record in extracted:
        check_cancel()
        if not record['internalSource'].startswith('data/') or '/lang/' in record['internalSource']:
            continue
        output = None
        try:
            constants,tables,diagnostics = parse(record)
            roots = [t for t in tables if isinstance(t.get(1),dict) and isinstance(t.get(2),dict) and b'meta' in t[2]]
            if not roots:
                continue
            table = roots[-1]
            meta = table[2][b'meta']
            if 'isText' not in str(meta):
                continue
            columns = table[1]
            views.clear()
            count = len(column(columns,1) or [])
            if not count:
                continue
            output = OUT/'本地化配置表'/(record['internalSource']+'.jsonl')
            output.parent.mkdir(parents=True,exist_ok=True)
            is_dialog = record['internalSource']=='data/common_dialog.lua'
            if is_dialog:
                dialog_folder=OUT/'剧情对话';dialog_folder.mkdir(exist_ok=True)
            text_file = None
            with output.open('w',encoding='utf-8') as stream:
                for row_index in range(count):
                    if row_index%500==0:
                        check_cancel()
                    row = decode_row(columns,meta,row_index,count)
                    stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                    if is_dialog:
                        if row_index%1000==0:
                            if text_file:text_file.close()
                            text_file=(dialog_folder/f'对话分卷_{row_index//1000+1:03d}.txt').open('w',encoding='utf-8')
                        text_file.write(f'\n===== 对话ID {row.get("ID",row_index)} =====\n')
                        for step in row.get('Data',[]):
                            speaker=step.get('Name','')
                            content=step.get('Content','')
                            female=step.get('FemaleContent','')
                            options=step.get('OptionContent',[])
                            if content or female or any(options):
                                dialogue_count+=1
                                text_file.write(f'[{step.get("Step","")}] {speaker}\n')
                                if content:text_file.write(str(content)+'\n')
                                if female and female!=content:text_file.write('【FemaleContent】'+str(female)+'\n')
                                for option in options:
                                    if option:text_file.write('【选项】'+str(option)+'\n')
                                text_file.write('\n')
            if text_file:text_file.close()
            table_reports.append({'source':record['internalSource'],'rows':count,'output':str(output.relative_to(OUT)),'diagnostics':diagnostics})
            emit(f'已解析配置表 {record["internalSource"]}：{count} 条。')
        except Exception as exc:
            partial = None
            if output and output.exists():
                partial = output.with_suffix('.partial.jsonl')
                output.replace(partial)
            errors.append({'source':record['internalSource'],'stage':'localized table','error':str(exc),'partial':str(partial.relative_to(OUT)) if partial else None})

    write_json(OUT/'提取错误.json',errors)
    write_json(OUT/'配置表索引.json',table_reports)
    write_json(OUT/'未解析文本ID.json',[str(v) for v in sorted(unresolved)])
    report={'manifestBlockFiles':input_block_count,'parsedChunks':len(extracted),'textIds':len(texts),'uniqueConfigStrings':len(decoded_dictionary),'uiTextKeys':len(ui),
            'localizedTables':len(table_reports),'dialogueStepsWithText':dialogue_count,'unresolvedTextIds':len(unresolved),'errors':len(errors),
            'note':'按本地清单选取块，缺少的块从 APK 补齐。字符串常量包含嵌套函数；剧情配置表按原始 ID 和步骤还原，不等同于剧情阅读顺序。'}
    write_json(OUT/'提取报告.json',report)
    emit(f'文本解析完成：{len(texts)} 个文本 ID，{len(table_reports)} 张配置表。')
    return report


if __name__=='__main__':
    main()
