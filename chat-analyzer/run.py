"""
启动器 — 双击即用，自动找空闲端口，自动打开浏览器
"""
import socket
import sys
import os
import webbrowser
import threading
import subprocess


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def open_browser(port):
    """等streamlit启动后打开浏览器"""
    import time
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(('127.0.0.1', port))
                webbrowser.open(f'http://localhost:{port}')
                return
        except ConnectionRefusedError:
            time.sleep(0.5)


def main():
    port = find_free_port()
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

    print(f"正在启动客服对话分析工具，端口: {port}")
    print(f"浏览器将自动打开 http://localhost:{port}")
    print("关闭此窗口即可停止程序")

    # 后台线程等服务起来后自动开浏览器
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run', app_path,
        '--server.port', str(port),
        '--server.headless', 'true',
        '--browser.gatherUsageStats', 'false',
        '--global.developmentMode', 'false',
    ])


if __name__ == '__main__':
    main()
