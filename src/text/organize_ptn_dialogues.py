"""Organize decoded dialogue by the game's story-review index."""
import csv
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'游戏文本提取'
DATA=OUT/'本地化配置表/data'


def lines(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def main(output=None,on_progress=None,cancel=None):
    global OUT, DATA
    if output is not None:
        OUT=Path(output)
        DATA=OUT/'本地化配置表/data'
    def check():
        if cancel is not None and cancel.is_set():
            from extract_ptn_texts import Cancelled
            raise Cancelled()
    dialogues={}
    count=0
    for row in lines(DATA/'common_dialog.lua.jsonl'):
        check()
        short=[]
        for step in row.get('Data',[]):
            if step.get('Content') or step.get('FemaleContent') or any(step.get('OptionContent',[])):
                short.append({k:step.get(k) for k in ['Step','Name','Content','FemaleContent','OptionContent','Jump','IsFalseOption']})
                count+=1
        dialogues[row['ID']]=short
    folder=OUT/'剧情按章节';folder.mkdir(exist_ok=True)
    index=[];missing=[]
    reviews=list(lines(DATA/'story_review.lua.jsonl'))
    reviews.sort(key=lambda r:(r.get('Type',0),r.get('Sort',0),r['ID']))
    for chapter in reviews:
        check()
        name=chapter.get('Name') or '未命名'
        safe=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',name)[:80].rstrip('. ')
        filename=f'类别{chapter.get("Type",0)}_{chapter.get("Sort",0):03d}_{chapter["ID"]}_{safe}.txt'
        total=0;talks=0
        with (folder/filename).open('w',encoding='utf-8') as stream:
            stream.write(f'{name}\n回顾ID：{chapter["ID"]}\n\n说明：按游戏回顾目录的节点、TalkList 和 Step 顺序整理。保留不同文本分支；不自动选择选项路线。\n')
            for node in chapter.get('Node',[]):
                stream.write(f'\n\n===== 节点 {node.get("NodeId","")}：{node.get("CodeName","")} {node.get("Name","")} =====\n')
                if node.get('Outs'):stream.write('后继节点：'+str(node['Outs'])+'\n')
                for talk in node.get('TalkList',[]):
                    ident=talk.get('TalkId',0)
                    if not ident:continue
                    talks+=1
                    stream.write(f'\n--- 对话 {ident} {talk.get("Title","")} ---\n')
                    if ident not in dialogues:
                        stream.write('【未找到对应对话表记录】\n');missing.append({'reviewId':chapter['ID'],'talkId':ident});continue
                    for step in dialogues[ident]:
                        total+=1
                        speaker=step.get('Name') or '旁白 / 未标注说话人'
                        stream.write(f'\n[{step["Step"]}] {speaker}\n')
                        if step['Content']:stream.write(step['Content']+'\n')
                        if step['FemaleContent'] and step['FemaleContent']!=step['Content']:stream.write('【FemaleContent 分支】'+step['FemaleContent']+'\n')
                        for i,option in enumerate(step['OptionContent'] or []):
                            if option:stream.write(f'【选项 {i+1}】{option}\n')
                        if step['Jump']:stream.write('【原始 Jump】'+str(step['Jump'])+'\n')
        index.append({'回顾ID':chapter['ID'],'类别':chapter.get('Type',0),'顺序':chapter.get('Sort',0),'名称':name,'对话引用数':talks,'文本步骤数':total,'文件':filename})
    with (OUT/'剧情目录.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(index[0]));writer.writeheader();writer.writerows(index)
    report={'reviewFiles':len(index),'dialogueGroups':len(dialogues),'dialogueStepsWithText':count,'missingReviewTalkReferences':missing}
    (OUT/'剧情整理报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    message=f'已整理 {len(index)} 份章节，{len(dialogues)} 组对话，缺失引用 {len(missing)}。'
    if on_progress:on_progress(message)
    else:print(message)
    return report


if __name__=='__main__':main()
