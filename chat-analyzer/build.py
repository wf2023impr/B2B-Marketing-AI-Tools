"""打包成exe — 运行: python build.py"""
import subprocess
import sys

subprocess.run([
    sys.executable, '-m', 'PyInstaller',
    '--name', '客服对话AI分析',
    '--onedir',
    '--console',
    '--icon', 'NONE',
    '--collect-all', 'streamlit',
    '--collect-all', 'streamlit_config',
    '--hidden-import', 'openai',
    '--hidden-import', 'openpyxl',
    '--hidden-import', 'pandas',
    '--copy-metadata', 'streamlit',
    '--copy-metadata', 'openai',
    '--add-data', 'app.py;.',
    'run.py',
], check=True)

print("\n✅ 打包完成！exe在 dist/客服对话AI分析/ 目录下")
print("把整个文件夹发给客户，双击 客服对话AI分析.exe 即可使用")
