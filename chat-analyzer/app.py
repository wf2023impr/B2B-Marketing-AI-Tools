"""
戴尔客服对话AI分析工具
使用DeepSeek API分析客服聊天记录，提取采购意向、客户情绪等结构化数据。
"""

import os
import io
import re
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import streamlit as st
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
    """调用DeepSeek分析单个对话"""
    user_msg = f"""请分析以下客服对话：

会话时间：{session_time}
客户名：{customer_name}
员工名：{staff_name}

对话内容：
{conversation_text}
"""
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
        return {"error": f"JSON解析失败: {content[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def process_session_file(client, df, progress_bar, status_text):
    """处理会话级Excel文件 — 10线程并发，带错误处理和限流重试"""
    total = len(df)
    results = [None] * total
    done_count = [0]
    error_count = [0]
    lock = threading.Lock()

    def do_one(idx, row):
        customer = str(row.get('咨询客户', '')).split('@')[0].strip()
        staff = str(row.get('接待人员', ''))
        session_time = str(row.get('接待时间', ''))
        conversation = str(row.get('有效对话', '') or row.get('会话内容', ''))

        if not conversation or conversation == 'nan' or len(conversation.strip()) < 10:
            return idx, {"会话时间": session_time, "客户名": customer, "员工名": staff, "error": "对话内容过短"}

        if len(conversation) > 4000:
            conversation = conversation[:4000] + "\n...(对话过长已截断)"

        # Retry up to 3 times on failure
        for attempt in range(3):
            result = analyze_conversation(client, conversation, customer, staff, session_time)
            if 'error' not in result or attempt == 2:
                return idx, result
            time.sleep(1 * (attempt + 1))
        return idx, result

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(do_one, idx, row): idx for idx, row in df.iterrows()}
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                results[idx] = result
            except Exception as e:
                with lock:
                    error_count[0] += 1
            with lock:
                done_count[0] += 1
                n = done_count[0]
                errs = error_count[0]
            progress_bar.progress(n / total)
            if errs > 0:
                status_text.text(f"🔍 已完成 {n}/{total}（{errs} 个错误）")
            else:
                status_text.text(f"🔍 已完成 {n}/{total}")

    return [r for r in results if r is not None]


def process_message_file(client, df, progress_bar, status_text):
    """处理消息级Excel文件 — 10线程并发，带错误处理和限流重试"""
    status_text.text("📦 正在按会话分组消息...")
    df['会话标识'] = df['日期'].astype(str) + '|' + df.apply(
        lambda r: r['发送人'] if r['是否员工'] != '是' else r['接收人'], axis=1
    )

    groups = list(df.groupby('会话标识'))
    total = len(groups)
    status_text.text(f"📦 共分出 {total} 个会话，开始并发分析...")

    results = [None] * total
    done_count = [0]
    error_count = [0]
    lock = threading.Lock()

    def do_one(idx, session_key, group):
        date_str, customer = session_key.split('|', 1)
        staff_rows = group[group['是否员工'] == '是']
        staff = staff_rows['发送人'].iloc[0] if len(staff_rows) > 0 else 'unknown'

        lines = []
        for _, msg in group.iterrows():
            sender = str(msg['发送人'])
            content = str(msg['消息内容'])
            time_str = str(msg['时间'])
            if msg['消息类型'] == '文本':
                lines.append(f"{sender} {time_str}: {content}")
        conversation = '\n'.join(lines)

        if len(conversation.strip()) < 10:
            return idx, None

        if len(conversation) > 4000:
            conversation = conversation[:4000] + "\n...(对话过长已截断)"

        for attempt in range(3):
            result = analyze_conversation(client, conversation, customer, staff, date_str)
            if 'error' not in result or attempt == 2:
                return idx, result
            time.sleep(1 * (attempt + 1))
        return idx, result

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(do_one, idx, key, grp): idx for idx, (key, grp) in enumerate(groups)}
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                results[idx] = result
            except Exception as e:
                with lock:
                    error_count[0] += 1
            with lock:
                done_count[0] += 1
                n = done_count[0]
                errs = error_count[0]
            progress_bar.progress(n / total)
            if errs > 0:
                status_text.text(f"🔍 已完成 {n}/{total}（{errs} 个错误）")
            else:
                status_text.text(f"🔍 已完成 {n}/{total}")

    return [r for r in results if r is not None]


def main():
    st.set_page_config(page_title="客服对话AI分析", page_icon="📊", layout="wide")
    st.title("📊 客服对话 AI 分析工具")
    st.caption("使用 DeepSeek 分析客服聊天记录，提取采购意向、客户情绪等结构化数据")

    # File upload
    uploaded_file = st.file_uploader("上传Excel文件（支持会话级或消息级格式）", type=["xlsx", "xls"])

    if uploaded_file:
        with st.spinner("📖 正在读取Excel文件，请稍候..."):
            df = pd.read_excel(uploaded_file, engine='openpyxl')

        st.success(f"✅ 读取完成，共 **{len(df)}** 行数据")
        st.dataframe(df.head(3), use_container_width=True)

        # Detect file type
        cols = set(df.columns)
        is_session = '会话内容' in cols or '有效对话' in cols
        is_message = '消息内容' in cols and '发送人' in cols

        if is_session:
            st.info(f"检测到 **会话级** 格式（每行一个完整对话，共 {len(df)} 个会话）")
        elif is_message:
            st.info("检测到 **消息级** 格式（每行一条消息，将自动按会话分组）")
        else:
            st.error("无法识别文件格式，请检查列名是否包含[会话内容/有效对话]或[消息内容+发送人]")
            return

        # Row range selection
        col1, col2 = st.columns(2)
        with col1:
            start_row = st.number_input("起始行", min_value=0, max_value=len(df) - 1, value=0)
        with col2:
            end_row = st.number_input("结束行", min_value=1, max_value=len(df), value=min(len(df), 20))

        if st.button("🚀 开始分析", type="primary"):
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
            subset = df.iloc[start_row:end_row].copy().reset_index(drop=True)

            st.divider()
            status_text = st.empty()
            progress_bar = st.progress(0)
            status_text.text(f"🚀 开始分析 {len(subset)} 条数据...")

            if is_session:
                results = process_session_file(client, subset, progress_bar, status_text)
            else:
                results = process_message_file(client, subset, progress_bar, status_text)

            status_text.text(f"✅ 分析完成！共处理 {len(results)} 个会话")

            # Build result DataFrame — fixed 14 columns
            result_rows = []
            for r in results:
                row = {}
                for col in OUTPUT_COLUMNS:
                    row[col] = r.get(col, 'none')
                if 'error' in r:
                    row['聊天大意'] = f"[错误] {r['error']}"
                result_rows.append(row)

            result_df = pd.DataFrame(result_rows, columns=OUTPUT_COLUMNS)
            st.subheader("📋 分析结果（固定14列）")
            st.dataframe(result_df, use_container_width=True, height=400)

            # Download
            base_name = os.path.splitext(uploaded_file.name)[0]
            output_name = f"{base_name}_分析结果.xlsx"
            output_buf = io.BytesIO()
            result_df.to_excel(output_buf, index=False, sheet_name='分析结果', engine='openpyxl')
            output_buf.seek(0)

            st.download_button(
                label="📥 下载分析结果",
                data=output_buf.getvalue(),
                file_name=output_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


if __name__ == "__main__":
    main()
