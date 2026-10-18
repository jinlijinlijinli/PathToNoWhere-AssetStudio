"""Point-and-click Windows UI for local PtN text extraction."""
from pathlib import Path
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import text_backend as backend
from extract_ptn_texts import Cancelled


class App:
    def __init__(self,root):
        self.root=root
        self.events=queue.Queue()
        self.cancel_event=threading.Event()
        self.busy=False
        self.analysis=None
        self.selected=set()
        self.last_export=None
        self.log_lines=[]
        self.folder=tk.StringVar()
        self.apk=tk.StringVar()
        self.output=tk.StringVar(value=str(backend.HOME/'文本输出'))
        self.mode=tk.StringVar(value='all')
        self.query=tk.StringVar()
        self.status=tk.StringVar(value='先选择游戏数据目录或 APK，再选择导出方式。')
        self.selection_status=tk.StringVar(value='章节尚未读取')
        root.title('无期迷途文本提取工具')
        root.geometry('1000x850')
        root.minsize(850,740)
        root.option_add('*Font',('Microsoft YaHei UI',10))
        style=ttk.Style()
        style.configure('TButton',padding=(10,6))
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',20,'bold'))
        style.configure('Treeview',rowheight=28)
        style.configure('Hint.TLabel',foreground='#606975')
        frame=ttk.Frame(root,padding=22)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='无期迷途 · 文本提取',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='导出剧情、审查、情绪检测、监管终端及其他游戏文字。',style='Hint.TLabel').pack(anchor='w',pady=(6,14))
        source=ttk.LabelFrame(frame,text='① 选择游戏文件',padding=12)
        source.pack(fill='x')
        self.controls=[]
        self.path_row(source,'游戏数据目录',self.folder,self.browse_folder)
        self.path_row(source,'同版本 APK',self.apk,self.browse_apk)
        ttk.Label(source,text='目录可选 com.zy.wqmt.cn、files 或 fs。APK 用于补齐安装包内资源，也可单独选择 APK。',style='Hint.TLabel',wraplength=890).grid(row=2,column=0,columnspan=3,sticky='w',pady=(5,0))
        dest=ttk.Frame(frame)
        dest.pack(fill='x',pady=12)
        ttk.Label(dest,text='② 保存位置',width=13).pack(side='left')
        entry=ttk.Entry(dest,textvariable=self.output)
        entry.pack(side='left',fill='x',expand=True,padx=8)
        button=ttk.Button(dest,text='选择文件夹',command=self.browse_output)
        button.pack(side='right')
        self.controls.extend([entry,button])
        modes=ttk.LabelFrame(frame,text='③ 选择导出内容',padding=10)
        modes.pack(fill='x')
        for value,title,desc in [('all','所有游戏文本（推荐）','审查 / 情绪检测 / 监管终端 / 剧情 / 其他文字'),('plot','仅剧情对话','章节版 + 全部对话分卷'),('chapters','按章节选择','只导出下方勾选的章节')]:
            panel=ttk.Frame(modes,padding=(8,0))
            panel.pack(side='left',fill='x',expand=True)
            radio=ttk.Radiobutton(panel,text=title,value=value,variable=self.mode,command=self.mode_changed)
            radio.pack(anchor='w')
            self.controls.append(radio)
            ttk.Label(panel,text=desc,style='Hint.TLabel').pack(anchor='w',pady=(4,0))
        chapter_frame=ttk.LabelFrame(frame,text='章节列表',padding=10)
        chapter_frame.pack(fill='both',expand=True,pady=12)
        top=ttk.Frame(chapter_frame)
        top.pack(fill='x')
        read_button=ttk.Button(top,text='读取 / 刷新章节',command=lambda:self.launch('read'))
        read_button.pack(side='left')
        ttk.Label(top,text='搜索').pack(side='left',padx=(16,5))
        search=ttk.Entry(top,textvariable=self.query)
        search.pack(side='left',fill='x',expand=True)
        all_button=ttk.Button(top,text='全选当前列表',command=self.select_visible)
        all_button.pack(side='left',padx=5)
        none_button=ttk.Button(top,text='清空选择',command=self.clear_selection)
        none_button.pack(side='left')
        self.controls.extend([read_button,search,all_button,none_button])
        table_frame=ttk.Frame(chapter_frame)
        table_frame.pack(fill='both',expand=True,pady=(9,5))
        self.tree=ttk.Treeview(table_frame,columns=('check','name','category','id','count'),show='headings',selectmode='none',height=7)
        for column,label,width in [('check','选择',55),('name','章节名称',360),('category','类别编号',85),('id','回顾 ID',100),('count','文字步骤',100)]:
            self.tree.heading(column,text=label)
            self.tree.column(column,width=width,stretch=column=='name',anchor='w' if column=='name' else 'center')
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Button-1>',self.toggle)
        ttk.Label(chapter_frame,textvariable=self.selection_status,style='Hint.TLabel').pack(anchor='w')
        ttk.Label(frame,text='首次读取会生成“工作缓存”；以后可直接复用。仅提供 APK 时，结果可能少于已更新的游戏数据。',style='Hint.TLabel',wraplength=930).pack(anchor='w')
        self.progress=ttk.Progressbar(frame,mode='indeterminate')
        self.progress.pack(fill='x',pady=(12,6))
        ttk.Label(frame,textvariable=self.status,wraplength=930).pack(anchor='w')
        actions=ttk.Frame(frame)
        actions.pack(fill='x',pady=(12,0))
        start=ttk.Button(actions,text='开始导出',command=lambda:self.launch('export'))
        start.pack(side='left')
        self.controls.append(start)
        self.stop_button=ttk.Button(actions,text='停止',command=self.stop,state='disabled')
        self.stop_button.pack(side='left',padx=8)
        ttk.Button(actions,text='查看运行日志',command=self.show_log).pack(side='left')
        ttk.Button(actions,text='使用指引',command=self.help).pack(side='right')
        ttk.Button(actions,text='打开导出结果',command=self.open_result).pack(side='right',padx=8)
        self.query.trace_add('write',lambda *_:self.refresh_rows())
        for variable in [self.folder,self.apk,self.output]:
            variable.trace_add('write',self.invalidate)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def path_row(self,parent,title,variable,command):
        row=0 if title=='游戏数据目录' else 1
        ttk.Label(parent,text=title,width=13).grid(row=row,column=0,sticky='w',pady=4)
        entry=ttk.Entry(parent,textvariable=variable)
        entry.grid(row=row,column=1,sticky='ew',padx=8,pady=4)
        button=ttk.Button(parent,text='选择目录' if row==0 else '选择 APK',command=command)
        button.grid(row=row,column=2,pady=4)
        parent.columnconfigure(1,weight=1)
        self.controls.extend([entry,button])

    def browse_folder(self):
        path=filedialog.askdirectory(title='选择 com.zy.wqmt.cn / files / fs 目录')
        if path:
            self.folder.set(path)
            candidates=list(Path(path).glob('*.apk'))
            if len(candidates)==1 and not self.apk.get():
                self.apk.set(str(candidates[0]))

    def browse_apk(self):
        path=filedialog.askopenfilename(title='选择同版本游戏 APK',filetypes=[('Android APK','*.apk')])
        if path:self.apk.set(path)

    def browse_output(self):
        path=filedialog.askdirectory(title='选择文本导出位置')
        if path:self.output.set(path)

    def invalidate(self,*_):
        if not self.busy:
            self.analysis=None
            self.selected.clear()
            self.refresh_rows()

    def mode_changed(self):
        if not self.busy:
            self.status.set('按章节导出：请先读取章节，再点击列表勾选。' if self.mode.get()=='chapters' else '全部文本模式会额外扫描 Unity 文件，耗时比剧情模式更长。' if self.mode.get()=='all' else '点击开始导出，将整理全部可解析的剧情。')

    def visible(self):
        if not self.analysis:return []
        query=self.query.get().strip().casefold()
        return [r for r in self.analysis['chapters'] if not query or query in (' '.join([r['名称'],r['回顾ID'],r['类别']])).casefold()]

    def refresh_rows(self):
        for item in self.tree.get_children():self.tree.delete(item)
        for row in self.visible():
            ident=row['回顾ID']
            self.tree.insert('', 'end',iid=ident,values=('☑' if ident in self.selected else '☐',row['名称'],row['类别'],ident,row['文本步骤数']))
        if self.analysis:
            self.selection_status.set(f'共 {len(self.analysis["chapters"])} 个章节，显示 {len(self.visible())} 个，已勾选 {len(self.selected)} 个。点击行即可勾选。')
        else:self.selection_status.set('章节尚未读取。按章节导出时，请先点击“读取 / 刷新章节”。')

    def toggle(self,event):
        if self.busy:return
        ident=self.tree.identify_row(event.y)
        if not ident:return
        if ident in self.selected:self.selected.remove(ident)
        else:self.selected.add(ident)
        self.refresh_rows()

    def select_visible(self):
        self.selected.update(r['回顾ID'] for r in self.visible())
        self.refresh_rows()

    def clear_selection(self):
        self.selected.clear()
        self.refresh_rows()

    def set_busy(self,busy):
        self.busy=busy
        for widget in self.controls:widget.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')
        if busy:self.progress.start(12)
        else:self.progress.stop()

    def launch(self,action):
        if self.busy:return
        if not self.output.get().strip():
            messagebox.showinfo('先选择保存位置','请先选择文本保存位置。');return
        try:backend.inputs(self.folder.get(),self.apk.get())
        except Exception as exc:messagebox.showerror('请检查游戏文件',str(exc));return
        if action=='export' and self.mode.get()=='chapters' and (not self.analysis or not self.selected):
            messagebox.showinfo('先选择章节','请点击“读取 / 刷新章节”，再勾选需要导出的章节。');return
        self.cancel_event.clear()
        self.set_busy(True)
        self.status.set('正在准备…')
        folder,apk,output=self.folder.get(),self.apk.get(),self.output.get()
        mode=self.mode.get()
        selected=set(self.selected)
        def emit(message):self.events.put(('progress',message))
        def work():
            try:
                analysis=backend.analyze(folder,apk,output,self.cancel_event,emit)
                self.events.put(('analysis',analysis))
                if action=='read':self.events.put(('ready',analysis));return
                result=backend.export(analysis,output,mode,selected,self.cancel_event,emit)
                self.events.put(('done',result))
            except Cancelled:self.events.put(('cancelled',None))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def stop(self):
        self.cancel_event.set()
        self.stop_button.configure(state='disabled')
        self.status.set('正在停止，请等待当前解析步骤结束。未完成的缓存不会标记为可用。')

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    self.log_lines.append(value)
                    if len(self.log_lines)>3000:self.log_lines=self.log_lines[-3000:]
                    if not self.cancel_event.is_set():self.status.set(value)
                elif kind=='analysis':
                    self.analysis=value
                    self.refresh_rows()
                elif kind=='ready':
                    self.set_busy(False)
                    self.status.set(f'已读取 {len(value["chapters"])} 个章节。可搜索并勾选，然后选择“按章节选择”导出。')
                elif kind=='done':
                    self.set_busy(False)
                    self.last_export=Path(value['directory'])
                    issues=sum(value['issues'].values())
                    label='导出完成（有缺失或未解析项）' if issues else '导出完成'
                    self.status.set(label+'：'+value['directory'])
                    self.log_lines.append(self.status.get())
                    messagebox.showinfo(label,f'已导出 {value["chapters"]} 个章节。\n\n{value["directory"]}\n\n'+('部分配置表或引用未完整解析，详见导出摘要与提取报告。' if issues else '可点击“打开导出结果”阅读。'))
                elif kind=='cancelled':
                    self.set_busy(False)
                    self.status.set('已停止。再次操作可复用已完整完成的解析缓存；未完成的导出目录仅含部分结果。')
                elif kind=='error':
                    self.set_busy(False)
                    self.status.set('处理失败：'+value)
                    self.log_lines.append(self.status.get())
                    messagebox.showerror('处理失败',value+'\n\n可通过“查看运行日志”检查详细信息。')
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def open_result(self):
        path=self.last_export or Path(self.output.get())
        if not path.is_dir():
            messagebox.showinfo('尚无结果','请先完成导出。');return
        os.startfile(path)

    def show_log(self):
        dialog=tk.Toplevel(self.root)
        dialog.title('运行日志')
        dialog.geometry('860x500')
        text=tk.Text(dialog,wrap='word',padx=12,pady=12)
        scroll=ttk.Scrollbar(dialog,command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0','\n'.join(self.log_lines) or '尚无运行记录。')
        text.configure(state='disabled')
        def save():
            path=filedialog.asksaveasfilename(parent=dialog,title='保存日志',defaultextension='.txt',filetypes=[('文本文件','*.txt')])
            if path:Path(path).write_text('\n'.join(self.log_lines),encoding='utf-8')
        ttk.Button(dialog,text='保存日志',command=save).pack(anchor='e',padx=12,pady=8)

    def help(self):
        dialog=tk.Toplevel(self.root)
        dialog.title('使用指引')
        dialog.geometry('750x620')
        text=tk.Text(dialog,wrap='word',padx=16,pady=16)
        scroll=ttk.Scrollbar(dialog,command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0','''三步导出
① 选择游戏数据目录；建议再选同版本 APK，补齐安装包内资源。
② 选择保存位置。
③ 选择导出方式，点击“开始导出”。

按章节导出
先点击“读取 / 刷新章节”。读取结束后可搜索章节名或回顾 ID，点击行勾选。选择“按章节选择”，再点击开始导出。
“全选当前列表”只勾选当前搜索结果；清空搜索不会清掉已有勾选。

三种模式
全部剧情：章节文件 + 回顾目录之外的全部对话分卷 + 已识别的剧情相关配置表。
按章节选择：只导出勾选的章节，适合日常阅读。
所有游戏文本（默认）：生成“全部文本阅读版”，审查、情绪检测、监管终端有独立目录；所有配置表转为 TXT，并提供可搜索的文本索引.csv。还会导出中文字符串池、系统/界面文案、含嵌套函数的脚本字符串、原始字节码、已支持的配置表，并额外扫描 Unity TextAsset 与界面字段。耗时更长，磁盘占用也更大。

怎么找游戏数据
通常从模拟器或手机导出 Android/data/com.zy.wqmt.cn 目录。也可以选择其中的 files 或 fs。若只有 APK，可留空数据目录，只选 APK；APK 通常不包含最新热更新或按需下载内容。
XAPK/APKS 请先解压，选择其中含 assets/res_manifest 和 blocks 资源的 APK。

缓存与停止
首次读取会在保存位置创建“工作缓存”，供后续章节导出复用。每次正式导出都创建新目录，不覆盖旧结果。停止后未完成的导出目录仅含部分文件。
更换游戏版本、输入文件发生变化后会使用新的缓存。工作缓存可以在工具关闭后自行删除，之后会重新解析。

范围与限制
支持本次验证的国服 Android 文本格式。所谓“所有文本”是所提供文件中已支持格式的文本，不包含未下载内容、其他区服、历史版本或服务器私有内容。
少数复杂配置表尚未完全适配，结果中用 .partial.jsonl 和错误报告标明。文本 ID 不自动当作普通整数交给 Excel，以免精度丢失。
本工具只在本机读取文件，不需要游戏账号、ADB 或 root，也不向外上传日志。''')
        text.configure(state='disabled')

    def close(self):
        if self.busy:
            self.stop()
            return
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()
