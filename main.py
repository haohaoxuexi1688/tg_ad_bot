"""
Telegram 批量广告机器人 - 交互式控制台

用法:
    python main.py              # 进入交互式菜单
    python main.py --cli        # 进入交互式菜单（显式）
    python main.py --auto       # 自动模式（原有行为）
"""

import argparse
import datetime
import builtins
import sys
import os
import time

# --- Timestamped Print ---
_original_print = builtins.print

def timestamped_print(*args, **kwargs):
    """A wrapper around the original print function that adds a timestamp."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if args and isinstance(args[0], str) and args[0].strip().startswith('['):
        _original_print(f"[{now}] {args[0]}", *args[1:], **kwargs)
    else:
        _original_print(f"[{now}]", *args, **kwargs)

builtins.print = timestamped_print
# -------------------------

from src.bot_controller import BotController
from src.telegram_account import TelegramAccount
from src.state_manager import StateManager
from src.telegram_driver import AccountLoggedOutException


class SimpleController:
    """简单控制器，用于单账号操作"""
    def __init__(self):
        self.state_manager = StateManager()


def show_menu():
    """显示主菜单"""
    print("\n" + "=" * 60)
    print("   Telegram 批量广告机器人 - 控制台")
    print("=" * 60)
    print()
    print("  [1] 加群组模式     - 只加入群组 (不发送广告)")
    print("  [2] 加频道模式     - 只加入频道 (不发送广告)")
    print("  [3] 发广告模式     - 只发送广告 (需要已加入)")
    print("  [4] 完整模式       - 加入群组/频道 + 发送广告")
    print("  [5] 测试单个账号   - 测试第一个账号是否能正常启动")
    print("  [6] 检查所有账号   - 批量检查哪些账号已登出")
    print("  [0] 退出")
    print()
    print("=" * 60)


def get_user_choice():
    """获取用户选择"""
    while True:
        try:
            choice = input("请选择操作 [0-6]: ").strip()
            if choice in ['0', '1', '2', '3', '4', '5', '6']:
                return choice
            print("无效选择，请输入 0-6")
        except KeyboardInterrupt:
            print("\n已取消")
            return '0'


def get_num_accounts():
    """获取并发账号数"""
    while True:
        try:
            num = input("同时运行几个账号? [默认: 3]: ").strip()
            if not num:
                return 3
            num = int(num)
            if 1 <= num <= 20:
                return num
            print("请输入 1-20 之间的数字")
        except ValueError:
            print("请输入有效数字")


def run_join_groups_only():
    """只加入群组模式"""
    print("\n" + "=" * 60)
    print("加群组模式 - 只加入群组，不发送广告")
    print("=" * 60)
    
    num = get_num_accounts()
    
    print(f"\n准备启动 {num} 个账号加入群组...")
    print("提示: 已加入的群组会被跳过，不会发广告")
    
    # 过滤 grouplist，只保留群组
    print("\n[过滤] 只处理标记为 is_channel=false 的群组...")
    
    class Config:
        pass
    
    cfg = Config()
    cfg.concurrency = num
    cfg.skip_failure_check = True  # 加群组模式：忽略之前的失败记录
    
    controller = BotController(config=cfg)
    
    # 过滤：只保留群组（is_channel=False）
    original_links = controller.group_links
    controller.group_links = [g for g in original_links if g[3] == False]
    
    print(f"[过滤后] 共有 {len(controller.group_links)} 个群组需要处理")
    for link, cooldown, can_send, is_channel in controller.group_links:
        print(f"  - {link}")
    
    if not controller.group_links:
        print("[警告] 没有标记为 is_channel=false 的群组！")
        print("请在 grouplist.txt 中添加群组，例如:")
        print("  https://t.me/groupname,60,false,false")
        return
    
    # 覆盖任务分配：只执行 JOIN，不执行 SEND_AD
    # 注意：忽略之前的失败记录，强制重新尝试
    
    def join_group_only_task(account):
        # 先找到所有群组的任务
        for link, cooldown, can_send, is_channel in controller.group_links:
            # 检查是否已加入
            if controller.state_manager.is_account_in_group(account.name, link):
                print(f"    [{account.name}] {link} - 已加入，跳过")
                continue
            # 检查是否被禁
            if controller.state_manager.is_group_banned_for_account(account.name, link):
                continue
            # 忽略失败次数检查，强制重新尝试
            # 返回 JOIN 任务
            print(f"    [{account.name}] {link} - 准备加入")
            return (link, cooldown, can_send, False, "JOIN")
        return None
    
    controller._get_next_group_task_for_account = join_group_only_task
    controller.run()


def run_join_channels_only():
    """只加入频道模式"""
    print("\n" + "=" * 60)
    print("加频道模式 - 只加入频道，不发送广告")
    print("=" * 60)
    
    num = get_num_accounts()
    
    print(f"\n准备启动 {num} 个账号加入频道...")
    print("提示: 已加入的频道会被跳过，不会发广告")
    
    # 过滤 grouplist，只保留频道
    print("\n[过滤] 只处理标记为 is_channel=true 的频道...")
    
    class Config:
        pass
    
    cfg = Config()
    cfg.concurrency = num
    cfg.skip_failure_check = True  # 加频道模式：忽略之前的失败记录
    
    controller = BotController(config=cfg)
    
    # 过滤：只保留频道（is_channel=True）
    original_links = controller.group_links
    controller.group_links = [g for g in original_links if g[3] == True]
    
    print(f"[过滤后] 共有 {len(controller.group_links)} 个频道需要处理")
    for link, cooldown, can_send, is_channel in controller.group_links:
        print(f"  - {link}")
    
    if not controller.group_links:
        print("[警告] 没有标记为 is_channel=true 的频道！")
        print("请在 grouplist.txt 中添加 ,true 标记，例如:")
        print("  https://t.me/channelname,60,false,true")
        return
    
    # 覆盖任务分配：只执行 JOIN_CHANNEL，不执行 SEND_AD
    # 注意：忽略之前的失败记录，强制重新尝试
    
    def join_channel_only_task(account):
        # 先找到所有频道的任务
        for link, cooldown, can_send, is_channel in controller.group_links:
            # 检查是否已加入
            if controller.state_manager.is_account_in_group(account.name, link):
                print(f"    [{account.name}] {link} - 已加入，跳过")
                continue
            # 检查是否被禁
            if controller.state_manager.is_group_banned_for_account(account.name, link):
                continue
            # 忽略失败次数检查，强制重新尝试
            # 返回 JOIN_CHANNEL 任务
            print(f"    [{account.name}] {link} - 准备加入")
            return (link, cooldown, can_send, True, "JOIN_CHANNEL")
        return None
    
    controller._get_next_group_task_for_account = join_channel_only_task
    controller.run()


def run_send_ads_only():
    """只发送广告模式"""
    print("\n" + "=" * 60)
    print("发广告模式 - 只发送广告（需要已加入群组/频道）")
    print("=" * 60)
    
    num = get_num_accounts()
    
    print(f"\n准备启动 {num} 个账号发送广告...")
    print("警告: 只会向已加入的群组/频道发送广告")
    print("未加入的群组/频道会被跳过")
    
    # 修改状态：假装所有群组/频道都已加入
    # 这样控制器会分配 SEND_AD 任务而不是 JOIN 任务
    print("\n[准备] 检查已加入的群组/频道...")
    
    class Config:
        pass
    
    cfg = Config()
    cfg.concurrency = num
    
    controller = BotController(config=cfg)
    
    # 显示状态
    joined_count = 0
    for link, cooldown, can_send, is_channel in controller.group_links:
        account_name = "Telegram 001"  # 简化显示
        is_joined = controller.state_manager.is_account_in_group(account_name, link)
        if is_joined:
            joined_count += 1
            print(f"  [已加入] {link}")
        else:
            print(f"  [未加入] {link} (将跳过)")
    
    print(f"\n[统计] 共 {len(controller.group_links)} 个目标，已加入 {joined_count} 个")
    
    controller.run()


def run_full_mode():
    """完整模式（原有行为）"""
    print("\n" + "=" * 60)
    print("完整模式 - 加入群组/频道 + 发送广告")
    print("=" * 60)
    
    num = get_num_accounts()
    
    print(f"\n准备启动 {num} 个账号...")
    print("流程: 未加入 -> 加入 -> 发送广告")
    
    class Config:
        pass
    
    cfg = Config()
    cfg.concurrency = num
    
    controller = BotController(config=cfg)
    controller.run()


def test_single_account():
    """测试单个账号"""
    print("\n" + "=" * 60)
    print("测试模式 - 测试第一个账号 (Telegram 001)")
    print("=" * 60)
    
    controller = SimpleController()
    account = TelegramAccount("Telegram 001", os.path.join("accounts", "Telegram 001"), controller)
    
    try:
        print("\n[1/3] 启动 Telegram...")
        if not account.start():
            print("[失败] 无法启动 Telegram.exe")
            return
        
        print("[2/3] 查找窗口...")
        if not account.find_window():
            print("[失败] 无法找到窗口")
            account.stop()
            return
        
        print("[3/3] 等待启动界面...")
        if account.driver.wait_for_startup_screen(timeout=60):
            print("[成功] 账号正常！")
            input("\n按回车键关闭...")
        else:
            print("[失败] 启动界面超时")
        
        account.stop()
        
    except Exception as e:
        print(f"[错误] {e}")
        account.stop()


def check_all_accounts():
    """检查所有账号状态（是否登出）"""
    print("\n" + "=" * 60)
    print("检查所有账号状态")
    print("=" * 60)
    print("说明: 会逐个启动账号，检测是否已登出")
    print("      已登出的账号需要重新扫码登录")
    print("=" * 60)
    
    # 发现所有账号
    accounts_root = "accounts"
    account_dirs = []
    if os.path.exists(accounts_root):
        for name in sorted(os.listdir(accounts_root)):
            path = os.path.join(accounts_root, name)
            if os.path.isdir(path) and name.startswith("Telegram"):
                if os.path.exists(os.path.join(path, "Telegram.exe")):
                    account_dirs.append((name, path))
    
    if not account_dirs:
        print("\n[错误] 没有发现账号目录")
        return
    
    print(f"\n发现 {len(account_dirs)} 个账号，开始检查...\n")
    
    results = {
        "normal": [],
        "logged_out": [],
        "error": []
    }
    
    controller = SimpleController()
    
    for idx, (account_name, account_path) in enumerate(account_dirs, 1):
        print(f"[{idx}/{len(account_dirs)}] 检查 {account_name}...")
        
        account = TelegramAccount(account_name, account_path, controller)
        
        try:
            # 启动
            if not account.start():
                print(f"    [错误] 启动失败")
                results["error"].append((account_name, "启动失败"))
                continue
            
            # 查找窗口
            if not account.find_window():
                print(f"    [错误] 找不到窗口")
                results["error"].append((account_name, "找不到窗口"))
                account.stop()
                continue
            
            # 检测状态
            try:
                if account.driver.wait_for_startup_screen(timeout=30):
                    print(f"    [正常] 账号已登录")
                    results["normal"].append(account_name)
                else:
                    print(f"    [未知] 状态不确定")
                    results["error"].append((account_name, "状态不确定"))
            except AccountLoggedOutException:
                print(f"    [登出] 账号已登出，需要重新登录")
                results["logged_out"].append(account_name)
                # 标记为登出
                controller.state_manager.mark_account_as_logged_out(account_name)
            
            account.stop()
            time.sleep(1)  # 等待关闭
            
        except Exception as e:
            print(f"    [错误] {e}")
            results["error"].append((account_name, str(e)))
            account.stop()
    
    # 显示结果汇总
    print("\n" + "=" * 60)
    print("检查结果汇总")
    print("=" * 60)
    
    print(f"\n[正常] ({len(results['normal'])} 个):")
    for name in results["normal"]:
        print(f"  ✓ {name}")
    
    print(f"\n[已登出] ({len(results['logged_out'])} 个):")
    for name in results["logged_out"]:
        print(f"  ✗ {name} - 需要重新扫码登录")
    
    if results["error"]:
        print(f"\n[错误] ({len(results['error'])} 个):")
        for name, reason in results["error"]:
            print(f"  ! {name} - {reason}")
    
    print("\n" + "=" * 60)
    input("\n按回车键返回菜单...")


def interactive_mode():
    """交互式模式"""
    while True:
        show_menu()
        choice = get_user_choice()
        
        if choice == '0':
            print("\n再见！")
            break
        elif choice == '1':
            run_join_groups_only()
        elif choice == '2':
            run_join_channels_only()
        elif choice == '3':
            run_send_ads_only()
        elif choice == '4':
            run_full_mode()
        elif choice == '5':
            test_single_account()
        elif choice == '6':
            check_all_accounts()


def auto_mode():
    """自动模式（向后兼容）"""
    parser = argparse.ArgumentParser(description="Telegram Bulk Advertiser Bot")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of accounts to run at the same time.")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("自动模式 - 完整流程（加入 + 发送广告）")
    print(f"并发数: {args.concurrency}")
    print("=" * 60)
    
    controller = BotController(config=args)
    controller.run()


def main():
    parser = argparse.ArgumentParser(description="Telegram Bulk Advertiser Bot")
    parser.add_argument("--concurrency", type=int, default=None, help="Number of accounts to run at the same time.")
    parser.add_argument("--cli", action="store_true", help="Interactive CLI mode")
    parser.add_argument("--auto", action="store_true", help="Auto mode (legacy behavior)")
    
    args = parser.parse_args()
    
    # 默认进入交互模式
    if args.auto:
        auto_mode()
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
