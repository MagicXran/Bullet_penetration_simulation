# -*- coding: utf-8 -*-
"""
测试 API_BASE 动态获取功能
验证前端能正确从 window.location.origin 获取后端地址
"""
import sys
import io

# 修复 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

def test_api_base_on_port_9000():
    """测试端口 9000 时 API_BASE 是否正确"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 监听控制台输出
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        print("=" * 60)
        print("测试 1: 验证 index.html (app.js) 的 API_BASE")
        print("=" * 60)

        # 访问首页
        page.goto('http://localhost:9000/index.html')
        page.wait_for_load_state('networkidle')

        # 获取 API_BASE 值
        api_base = page.evaluate("() => API_BASE")
        print(f"访问地址: http://localhost:9000/index.html")
        print(f"API_BASE 值: {api_base}")
        print(f"期望值: http://localhost:9000/api")

        if api_base == "http://localhost:9000/api":
            print("[PASS] 测试通过！API_BASE 正确动态获取")
        else:
            print("[FAIL] 测试失败！API_BASE 不匹配")
            browser.close()
            return False

        print()
        print("=" * 60)
        print("测试 2: 验证 output.html 的 API_BASE")
        print("=" * 60)

        # 访问 output.html
        page.goto('http://localhost:9000/output.html')
        page.wait_for_load_state('networkidle')

        # 获取 API_BASE 值
        api_base_output = page.evaluate("() => API_BASE")
        print(f"访问地址: http://localhost:9000/output.html")
        print(f"API_BASE 值: {api_base_output}")
        print(f"期望值: http://localhost:9000/api")

        if api_base_output == "http://localhost:9000/api":
            print("[PASS] 测试通过！API_BASE 正确动态获取")
        else:
            print("[FAIL] 测试失败！API_BASE 不匹配")
            browser.close()
            return False

        print()
        print("=" * 60)
        print("测试 3: 验证 window.location.origin 机制")
        print("=" * 60)

        # 验证 window.location.origin
        origin = page.evaluate("() => window.location.origin")
        print(f"window.location.origin: {origin}")
        print(f"构建的 API_BASE: {origin}/api")

        # 截图保存
        screenshot_path = "D:/Nercar/NanGang/PSD/Apps/Bullet_penetration_simulation/tests/api_base_test_result.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n截图已保存: {screenshot_path}")

        browser.close()

        print()
        print("=" * 60)
        print("[SUCCESS] 所有测试通过！前后端 IP:Port 配置已同步")
        print("=" * 60)
        return True

if __name__ == "__main__":
    success = test_api_base_on_port_9000()
    exit(0 if success else 1)
