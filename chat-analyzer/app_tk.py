"""
客服对话AI分析工具 (tkinter版)
双击即用，无需浏览器。使用DeepSeek分析客服聊天记录。
"""

import os
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
from openai import OpenAI

API_KEY = "sk-0f718d37ab5947c0ab087c628c8c3a09"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是戴尔客服对话分析师。分析聊天内容，输出严格固定14个字段的JSON。

判断依据：
- 客户选"1"=个人购买，选"2"=企业购买，选"3"=个人购买（外星人）
- 如果对话提到公司、单位、批量采购=企业购买
- 如果只是个人咨询电脑=个人购买
- 采购意向：客户明确要买/问价格/要报价=高；在犹豫对比=中；只是随便问问/售后问题=低；完全无购买意图=无
- 预算：对话中提到的具体金额或价格范围，没提到填none
- 采购时间：对话中提到的时间计划，如"这两天""下周""月底前"，没提到填none
- 需求产品：具体产品型号如"灵越16Pro""R450"，或类型如"游戏本""服务器"，没提到填none
- 客户顾虑：客户表达的担忧，如价格贵、质量问题、售后、配置不够等，没有填none
- 销售方案：员工给出的建议/推荐/报价/解决办法，没有填none

输出JSON格式（严格14个字段，不多不少）：
{"会话时间":"","客户名":"","员工名":"","是否为企业购买":"","是否为个人购买":"","聊天大意":"","采购意向":"","预算":"","采购时间":"","需求产品":"","客户顾虑":"","销售方案":"","客户情绪":"","员工态度":""}

规则：
1. 客户情绪只能填：积极有意向/犹豫/冷淡/不耐烦/质疑/无明显情绪
2. 员工态度只能填：专业耐心/热情主动/敷衍/急躁/无明显表现
3. 是否为企业购买、是否为个人购买只能填：是/否/不确定
4. 采购意向只能填：高/中/低/无
5. 空值一律填none
6. 聊天大意用一句话概括，不超过30字
7. 只输出一个JSON对象，不要标题、解释、markdown
"""

OUTPUT_COLUMNS = [
    '会话时间', '客户名', '员工名', '是否为企业购买', '是否为个人购买',
    '聊天大意', '采购意向', '预算', '采购时间', '需求产品',
    '客户顾虑', '销售方案', '客户情绪', '员工态度',
]


def analyze_conversation(client, conversation_text, customer_name, staff_name, session_time):
    user_msg = f"请分析以下客服对话：\n\n会话时间：{session_time}\n客户名：{customer_name}\n员工名：{staff_name}\n\n对话内容：\n{conversation_text}"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": f"JSON parse fail: {content[:100]}"}
    except Exception as e:
        return {"error": str(e)}


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("客服对话 AI 分析工具")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)
        self.df = None
        self.file_path = None
        self.is_session = False
        self.is_message = False
        self.running = False

        self._build_ui()

    def _build_ui(self):
        # Top frame: file selection
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Excel文件:").pack(side=tk.LEFT)
        self.file_label = ttk.Label(top, text="未选择", width=60, relief="sunken", anchor="w")
        self.file_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top, text="选择文件", command=self.select_file).pack(side=tk.LEFT)

        # Row range frame
        range_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        range_frame.pack(fill=tk.X)

        ttk.Label(range_frame, text="起始行:").pack(side=tk.LEFT)
        self.start_var = tk.StringVar(value="0")
        ttk.Entry(range_frame, textvariable=self.start_var, width=8).pack(side=tk.LEFT, padx=(2, 15))

        ttk.Label(range_frame, text="结束行:").pack(side=tk.LEFT)
        self.end_var = tk.StringVar(value="20")
        ttk.Entry(range_frame, textvariable=self.end_var, width=8).pack(side=tk.LEFT, padx=(2, 15))

        self.btn_start = ttk.Button(range_frame, text="开始分析", command=self.start_analysis)
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_save = ttk.Button(range_frame, text="保存结果", command=self.save_results, state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT)

        # Status
        status_frame = ttk.Frame(self.root, padding=(10, 0))
        status_frame.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="请先选择Excel文件")
        ttk.Label(status_frame, textvariable=self.status_var, foreground="blue").pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(status_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.RIGHT, padx=5)

        # Result table
        table_frame = ttk.Frame(self.root, padding=10)
        table_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbars
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)

        self.tree = ttk.Treeview(
            table_frame, columns=OUTPUT_COLUMNS, show='headings',
            xscrollcommand=xscroll.set, yscrollcommand=yscroll.set
        )
        xscroll.config(command=self.tree.xview)
        yscroll.config(command=self.tree.yview)

        for col in OUTPUT_COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, minwidth=60)

        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.result_df = None

    def select_file(self):
        path = filedialog.askopenfilename(
            title="选择聊天记录Excel",
            filetypes=[("Excel", "*.xlsx *.xls")]
        )
        if not path:
            return

        self.file_path = path
        self.file_label.config(text=os.path.basename(path))
        self.status_var.set("正在读取文件...")
        self.root.update()

        try:
            self.df = pd.read_excel(path, engine='openpyxl')
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        cols = set(self.df.columns)
        self.is_session = '会话内容' in cols or '有效对话' in cols
        self.is_message = '消息内容' in cols and '发送人' in cols

        if self.is_session:
            fmt = "会话级"
        elif self.is_message:
            fmt = "消息级"
        else:
            messagebox.showerror("格式错误", "无法识别文件格式")
            return

        self.end_var.set(str(min(len(self.df), 20)))
        self.status_var.set(f"已读取 {len(self.df)} 行 ({fmt}格式)")

    def start_analysis(self):
        if self.df is None:
            messagebox.showwarning("提示", "请先选择文件")
            return
        if self.running:
            return

        start = int(self.start_var.get())
        end = int(self.end_var.get())
        if end <= start:
            messagebox.showwarning("提示", "结束行必须大于起始行")
            return

        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_save.config(state=tk.DISABLED)
        # Clear old results
        for item in self.tree.get_children():
            self.tree.delete(item)

        threading.Thread(target=self._run_analysis, args=(start, end), daemon=True).start()

    def _run_analysis(self, start, end):
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        subset = self.df.iloc[start:end].copy().reset_index(drop=True)

        if self.is_session:
            tasks = self._prepare_session_tasks(subset)
        else:
            tasks = self._prepare_message_tasks(subset)

        total = len(tasks)
        if total == 0:
            self.status_var.set("没有有效对话可分析")
            self.running = False
            self.btn_start.config(state=tk.NORMAL)
            return

        self.progress['maximum'] = total
        self.progress['value'] = 0
        results = [None] * total
        done = [0]
        errors = [0]
        lock = threading.Lock()

        def do_one(idx, customer, staff, session_time, conversation):
            for attempt in range(3):
                result = analyze_conversation(client, conversation, customer, staff, session_time)
                if 'error' not in result or attempt == 2:
                    return idx, result
                time.sleep(1 * (attempt + 1))
            return idx, result

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {}
            for i, task in enumerate(tasks):
                f = pool.submit(do_one, i, task['customer'], task['staff'], task['time'], task['conversation'])
                futures[f] = i

            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                    # Add to table on main thread
                    row_vals = tuple(result.get(c, 'none') for c in OUTPUT_COLUMNS)
                    self.root.after(0, lambda rv=row_vals: self.tree.insert('', tk.END, values=rv))
                except Exception:
                    with lock:
                        errors[0] += 1

                with lock:
                    done[0] += 1
                    n = done[0]
                    e = errors[0]
                msg = f"已完成 {n}/{total}" + (f" ({e}个错误)" if e > 0 else "")
                self.root.after(0, lambda m=msg, v=n: self._update_progress(m, v))

        # Build result DataFrame
        valid = [r for r in results if r is not None]
        rows = []
        for r in valid:
            row = {}
            for col in OUTPUT_COLUMNS:
                row[col] = r.get(col, 'none')
            if 'error' in r:
                row['聊天大意'] = f"[错误] {r['error']}"
            rows.append(row)

        self.result_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
        self.root.after(0, self._analysis_done)

    def _update_progress(self, msg, val):
        self.status_var.set(msg)
        self.progress['value'] = val

    def _analysis_done(self):
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.NORMAL)
        self.status_var.set(f"分析完成! 共 {len(self.result_df)} 条结果，点击[保存结果]导出Excel")

    def _prepare_session_tasks(self, df):
        tasks = []
        for _, row in df.iterrows():
            customer = str(row.get('咨询客户', '')).split('@')[0].strip()
            staff = str(row.get('接待人员', ''))
            session_time = str(row.get('接待时间', ''))
            conversation = str(row.get('有效对话', '') or row.get('会话内容', ''))

            if not conversation or conversation == 'nan' or len(conversation.strip()) < 10:
                continue
            if len(conversation) > 4000:
                conversation = conversation[:4000] + "\n...(截断)"

            tasks.append({'customer': customer, 'staff': staff, 'time': session_time, 'conversation': conversation})
        return tasks

    def _prepare_message_tasks(self, df):
        df = df.copy()
        df['_key'] = df['日期'].astype(str) + '|' + df.apply(
            lambda r: r['发送人'] if r['是否员工'] != '是' else r['接收人'], axis=1
        )
        tasks = []
        for key, group in df.groupby('_key'):
            date_str, customer = key.split('|', 1)
            staff_rows = group[group['是否员工'] == '是']
            staff = staff_rows['发送人'].iloc[0] if len(staff_rows) > 0 else 'unknown'

            lines = []
            for _, msg in group.iterrows():
                if msg['消息类型'] == '文本':
                    lines.append(f"{msg['发送人']} {msg['时间']}: {msg['消息内容']}")
            conversation = '\n'.join(lines)

            if len(conversation.strip()) < 10:
                continue
            if len(conversation) > 4000:
                conversation = conversation[:4000] + "\n...(截断)"

            tasks.append({'customer': customer, 'staff': staff, 'time': date_str, 'conversation': conversation})
        return tasks

    def save_results(self):
        if self.result_df is None or len(self.result_df) == 0:
            messagebox.showwarning("提示", "没有结果可保存")
            return

        base = os.path.splitext(os.path.basename(self.file_path))[0] if self.file_path else "output"
        default_name = f"{base}_分析结果.xlsx"

        path = filedialog.asksaveasfilename(
            title="保存分析结果",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return

        self.result_df.to_excel(path, index=False, sheet_name='分析结果', engine='openpyxl')
        self.status_var.set(f"已保存到: {path}")
        messagebox.showinfo("完成", f"结果已保存到:\n{path}")


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
