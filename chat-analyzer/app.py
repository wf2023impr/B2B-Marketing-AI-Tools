"""
戴尔客服对话AI分析工具
使用DeepSeek API分析客服聊天记录，提取采购意向、客户情绪等结构化数据。
"""

import os
import re
import time
import json
import pandas as pd
import streamlit as st
from openai import OpenAI

SYSTEM_PROMPT = """你是一个专业的客服对话分析师。请严格按要求分析以下聊天内容。

分析维度：

一、基础信息提取：
- 会话时间：从对话中提取
- 客户名：咨询客户的名称
- 员工名：接待人员的名称
- 是否为企业购买：是/否/不确定
- 是否为个人购买：是/否/不确定

二、对话分析：
- 聊天大意：用一句话概括对话内容
- 采购意向：高/中/低/无
- 预算：从对话中提取，没有则填none
- 采购时间：从对话中提取，没有则填none
- 需求产品：从对话中提取具体产品型号或类型
- 客户顾虑：价格/质量/售后/配置/其他/none
- 销售方案：员工提出的解决方案概括
- 客户情绪：只能填以下之一：积极有意向/犹豫/冷淡/不耐烦/质疑/无明显情绪
- 员工态度：只能填以下之一：专业耐心/热情主动/敷衍/急躁/无明显表现

三、问卷映射（根据对话内容判断，没有信息填none）：

1. 采购时间计划？
A. 1个月内  B. 1-3个月  C. 3-6个月  D. 暂无计划

2. 计划采购的主要产品类型？（可多选，用+连接）
A. 台式电脑/笔记本  B. 服务器及存储设备  C. CPU、内存、硬盘等核心配件  D. 显示器、键鼠、网络设备等外设  E. 其他

3. 采购的核心用途？
A. 个人日常办公/娱乐  B. 企业日常办公  C. 服务器运维、数据存储  D. 设计、编程、游戏等高性能需求  E. 其他

4. 采购时最看重的因素？
A. 产品质量与性能  B. 价格性价比  C. 售后服务与技术支持  D. 供货速度与库存  E. 品牌口碑

5. 预算区间？
A. 5000元以内  B. 5000-10000元  C. 10000-30000元  D. 30000元以上  E. 暂未确定

6. 更倾向通过哪种渠道了解产品信息？
A. 门店实地体验  B. 线上产品详情/官网  C. 销售一对一介绍  D. 行业评测/朋友推荐

请严格以JSON格式输出，字段如下：
{
  "会话时间": "",
  "客户名": "",
  "员工名": "",
  "是否为企业购买": "",
  "是否为个人购买": "",
  "聊天大意": "",
  "采购意向": "",
  "预算": "",
  "采购时间": "",
  "需求产品": "",
  "客户顾虑": "",
  "销售方案": "",
  "客户情绪": "",
  "员工态度": "",
  "Q1_采购时间计划": "",
  "Q2_产品类型": "",
  "Q3_核心用途": "",
  "Q4_看重因素": "",
  "Q5_预算区间": "",
  "Q6_信息渠道": ""
}

规则：
1. 客户情绪只能填：积极有意向/犹豫/冷淡/不耐烦/质疑/无明显情绪
2. 员工态度只能填：专业耐心/热情主动/敷衍/急躁/无明显表现
3. 问卷题只填选项字母（如A、B+C），没有信息填none
4. 空值一律填none
5. 只输出JSON，不要任何多余解释
"""


def analyze_conversation(client, model, conversation_text, customer_name, staff_name, session_time):
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
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        content = response.choices[0].message.content.strip()
        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": f"JSON解析失败: {content[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def process_session_file(client, model, df, progress_bar=None, status_text=None):
    """处理会话级Excel文件（每行一个完整对话）"""
    results = []
    total = len(df)

    for idx, row in df.iterrows():
        customer = str(row.get('咨询客户', '')).split('@')[0].strip()
        staff = str(row.get('接待人员', ''))
        session_time = str(row.get('接待时间', ''))
        conversation = str(row.get('有效对话', '') or row.get('会话内容', ''))

        if not conversation or conversation == 'nan' or len(conversation.strip()) < 10:
            results.append({"会话时间": session_time, "客户名": customer, "员工名": staff, "error": "对话内容过短"})
            continue

        # Truncate very long conversations
        if len(conversation) > 4000:
            conversation = conversation[:4000] + "\n...(对话过长已截断)"

        if status_text:
            status_text.text(f"正在分析 {idx + 1}/{total}: {customer}")
        if progress_bar:
            progress_bar.progress((idx + 1) / total)

        result = analyze_conversation(client, model, conversation, customer, staff, session_time)
        results.append(result)

        # Rate limiting
        time.sleep(0.5)

    return results


def process_message_file(client, model, df, progress_bar=None, status_text=None):
    """处理消息级Excel文件（每行一条消息，需按会话分组）"""
    # Group by conversation (customer-employee pair on same date)
    df['会话标识'] = df['日期'].astype(str) + '|' + df.apply(
        lambda r: r['发送人'] if r['是否员工'] != '是' else r['接收人'], axis=1
    )

    results = []
    groups = list(df.groupby('会话标识'))
    total = len(groups)

    for idx, (session_key, group) in enumerate(groups):
        date_str, customer = session_key.split('|', 1)
        staff_rows = group[group['是否员工'] == '是']
        staff = staff_rows['发送人'].iloc[0] if len(staff_rows) > 0 else 'unknown'

        # Build conversation text
        lines = []
        for _, msg in group.iterrows():
            sender = str(msg['发送人'])
            content = str(msg['消息内容'])
            time_str = str(msg['时间'])
            if msg['消息类型'] == '文本':
                lines.append(f"{sender} {time_str}: {content}")
        conversation = '\n'.join(lines)

        if len(conversation.strip()) < 10:
            continue

        if len(conversation) > 4000:
            conversation = conversation[:4000] + "\n...(对话过长已截断)"

        if status_text:
            status_text.text(f"正在分析 {idx + 1}/{total}: {customer}")
        if progress_bar:
            progress_bar.progress((idx + 1) / total)

        result = analyze_conversation(client, model, conversation, customer, staff, date_str)
        results.append(result)
        time.sleep(0.5)

    return results


def main():
    st.set_page_config(page_title="客服对话AI分析", page_icon="📊", layout="wide")
    st.title("📊 客服对话 AI 分析工具")
    st.caption("使用 DeepSeek 分析客服聊天记录，提取采购意向、客户情绪等结构化数据")

    # Sidebar config
    with st.sidebar:
        st.header("⚙️ 配置")
        api_key = st.text_input("DeepSeek API Key", type="password",
                                value=os.environ.get("DEEPSEEK_API_KEY", ""))
        base_url = st.text_input("API Base URL", value="https://api.deepseek.com")
        model = st.text_input("模型", value="deepseek-chat")
        st.divider()
        st.markdown("**数据格式说明**")
        st.markdown("""
        支持两种Excel格式：
        - **会话级**：含"会话内容"或"有效对话"列
        - **消息级**：含"消息内容"、"发送人"列
        """)

    # File upload
    uploaded_file = st.file_uploader("上传Excel文件", type=["xlsx", "xls"])

    if uploaded_file and api_key:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        st.write(f"读取到 **{len(df)}** 行数据")
        st.dataframe(df.head(3), use_container_width=True)

        # Detect file type
        cols = set(df.columns)
        is_session = '会话内容' in cols or '有效对话' in cols
        is_message = '消息内容' in cols and '发送人' in cols

        if is_session:
            st.info("检测到 **会话级** 格式（每行一个完整对话）")
        elif is_message:
            st.info("检测到 **消息级** 格式（每行一条消息）")
        else:
            st.error("无法识别文件格式，请检查列名")
            return

        # Row range selection
        col1, col2 = st.columns(2)
        with col1:
            start_row = st.number_input("起始行", min_value=0, max_value=len(df) - 1, value=0)
        with col2:
            end_row = st.number_input("结束行", min_value=1, max_value=len(df), value=min(len(df), 20))

        if st.button("🚀 开始分析", type="primary"):
            client = OpenAI(api_key=api_key, base_url=base_url)
            subset = df.iloc[start_row:end_row].copy().reset_index(drop=True)

            progress_bar = st.progress(0)
            status_text = st.empty()

            if is_session:
                results = process_session_file(client, model, subset, progress_bar, status_text)
            else:
                results = process_message_file(client, model, subset, progress_bar, status_text)

            status_text.text("分析完成!")

            # Build result DataFrame
            output_columns = [
                '会话时间', '客户名', '员工名', '是否为企业购买', '是否为个人购买',
                '聊天大意', '采购意向', '预算', '采购时间', '需求产品',
                '客户顾虑', '销售方案', '客户情绪', '员工态度',
                'Q1_采购时间计划', 'Q2_产品类型', 'Q3_核心用途',
                'Q4_看重因素', 'Q5_预算区间', 'Q6_信息渠道'
            ]

            result_rows = []
            for r in results:
                row = {}
                for col in output_columns:
                    row[col] = r.get(col, 'none')
                if 'error' in r:
                    row['聊天大意'] = f"[错误] {r['error']}"
                result_rows.append(row)

            result_df = pd.DataFrame(result_rows, columns=output_columns)
            st.subheader("📋 分析结果")
            st.dataframe(result_df, use_container_width=True, height=400)

            # Download button
            output_path = uploaded_file.name.replace('.xlsx', '_分析结果.xlsx').replace('.xls', '_分析结果.xlsx')
            buffer = pd.ExcelWriter(f"/tmp/{output_path}", engine='openpyxl')
            result_df.to_excel(buffer, index=False, sheet_name='分析结果')
            buffer.close()

            with open(f"/tmp/{output_path}", "rb") as f:
                st.download_button(
                    label="📥 下载分析结果",
                    data=f.read(),
                    file_name=output_path,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    elif not api_key:
        st.warning("请在侧边栏输入 DeepSeek API Key")


if __name__ == "__main__":
    main()
