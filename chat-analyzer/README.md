# 客服对话 AI 分析工具

使用 DeepSeek API 自动分析客服聊天记录，批量提取采购意向、客户情绪等结构化数据。

## 功能

- 支持两种 Excel 格式：
  - **会话级**：每行一个完整对话（含"会话内容"或"有效对话"列）
  - **消息级**：每行一条消息（含"消息内容"、"发送人"列，自动按会话分组）
- 10 线程并发调用 DeepSeek，失败自动重试 3 次
- 输出固定 14 列结果表格，导出 Excel

## 输出列（固定 14 列）

会话时间 | 客户名 | 员工名 | 是否为企业购买 | 是否为个人购买 | 聊天大意 | 采购意向 | 预算 | 采购时间 | 需求产品 | 客户顾虑 | 销售方案 | 客户情绪 | 员工态度

## 使用方式

### 方式一：直接运行（需 Python 环境）

```bash
pip install openai pandas openpyxl
python app_tk.py
```

### 方式二：打包成 exe 发给客户

```bash
pip install pyinstaller
python -m PyInstaller --name ChatAnalyzer --onedir --windowed \
  --hidden-import openai --hidden-import openpyxl --hidden-import pandas \
  --exclude-module torch --exclude-module torchvision --exclude-module scipy \
  --exclude-module pyarrow --exclude-module PIL --exclude-module matplotlib \
  --exclude-module streamlit --exclude-module altair \
  --exclude-module win32com --exclude-module Pythonwin \
  app_tk.py
```

打包产物在 `dist/ChatAnalyzer/`，整个文件夹压缩发给客户，双击 `ChatAnalyzer.exe` 即可使用。

## 文件说明

| 文件 | 说明 |
|------|------|
| `app_tk.py` | 主程序（tkinter 桌面版，用于打包 exe） |
| `app.py` | Streamlit Web 版（开发/内部使用） |
| `run.py` | Streamlit 启动器（自动端口+浏览器） |
| `build.py` | 打包脚本 |
| `requirements.txt` | Python 依赖 |

## 技术栈

- DeepSeek API（deepseek-chat 模型）
- Python + tkinter（桌面 GUI）
- pandas + openpyxl（Excel 读写）
- PyInstaller（打包 exe，约 109MB）
