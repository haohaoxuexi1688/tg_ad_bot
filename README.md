# Telegram GUI 自动化工具

## 1. 项目简介

本项目是一个基于 GUI 自动化的 Telegram 桌面客户端实验工具，用于管理多个账号、批量执行加入群组/频道、消息发送等重复操作。它通过 GUI 自动化模拟用户操作，采用并发执行模型同时运行多个账号，并具备持久化状态管理系统来跟踪进度和冷却时间。

---

## 2. 项目结构

代码库已重构为模块化、分层架构，以增强可维护性、可测试性和未来开发的便利性。

-   **`main.py`**: 应用程序的主入口。负责解析命令行参数（如 `--concurrency`）并实例化运行 `BotController`。

-   **`bot_controller.py`**: 机器人的"大脑"。`BotController` 类负责高级编排和调度逻辑：
    -   管理活跃和非活跃的 `TelegramAccount` 实例池。
    -   实现账号轮换策略（停止旧账号，启动新账号）。
    -   根据 `StateManager` 的逻辑为空闲账号分配任务（如 `SEND_AD`、`JOIN_GROUP`、`JOIN_CHANNEL`）。
    -   包含主应用程序循环 (`run()`)。

-   **`telegram_account.py`**: 定义 `TelegramAccount` 类，表示单个运行的 Telegram 实例。负责：
    -   管理 `Telegram.exe` 进程的生命周期（启动和停止）。
    -   查找并激活正确的应用程序窗口。
    -   将所有 GUI 特定操作委托给 `TelegramDriver`。

-   **`telegram_driver.py`**: GUI 自动化层，抽象了所有 `pyautogui` 调用。`TelegramDriver` 类包含与屏幕相关的脆弱代码。
    -   提供高级方法如 `send_ad_flow()`、`join_group_flow()` 和 `join_channel_flow()`。
    -   包含所有图像查找（`locateOnScreen`）、点击和输入逻辑。
    -   **注意**: 这是应用程序最脆弱的部分。未来的重构应重点用更稳健的方法替换这里的逻辑。

-   **`state_manager.py`**: 处理所有状态持久化。`StateManager` 类从 `results/state.json` 读取并写入。
    -   提供清晰的方法来查询和更新状态（如 `is_group_on_cooldown`、`get_failure_count`、`mark_group_joined`）。
    -   确保所有与状态相关的逻辑集中并与主控制器逻辑解耦。

-   **`test_*.py` 文件**: 使用 `pytest` 的全面测试套件，确保每个模块的逻辑正常工作。这包括对 `StateManager` 的单元测试，以及对 `BotController` 和 `TelegramDriver` 的基于模拟的测试，无需实时 GUI 即可测试复杂流程。

---

## 3. 配置

所有运行数据存储在 `data/` 目录中。

-   **`accounts/`**: 每个子目录（如 `Telegram 001`、`Telegram 002`）应包含 Telegram 便携版应用程序（`Telegram.exe`）。机器人会自动发现这些目录。

-   **`data/grouplist.txt`**: 示例群组和频道列表。每行应遵循以下格式：
    ```
    https://t.me/链接,冷却时间,可发链接,是否频道
    ```
    -   **`链接`** (必填): 群组或频道的链接，如 `https://t.me/groupname`
    -   **`冷却时间`** (必填): 两次发送广告之间的等待时间（分钟）
    -   **`可发链接`** (可选): `true` 或 `false`，表示该群组/频道是否允许发送链接，默认 `false`
    -   **`是否频道`** (可选): `true` 或 `false`，表示是否为频道，默认 `false`
        -   **群组** (`false`): 使用 `view_group.png` → `join_group.png` → 验证 `input.png`
        -   **频道** (`true`): 使用 `view_channel.png` → `join_channel.png` → 验证 `mute.png`

    **示例:**
    ```text
    # 群组示例 - 60分钟冷却，可发链接
    https://t.me/mygroup,60,true,false
    
    # 频道示例 - 30分钟冷却，不可发链接
    https://t.me/mychannel,30,false,true
    
    # 简短写法 - 默认为群组
    https://t.me/simplegroup,15
    ```

-   **`data/messages.txt`**: 每行包含一个不同的示例消息。程序会随机选择其中一条用于发送。

-   **`data/contacts.txt`**: 示例联系人句柄列表（如 `@mycontact`），会附加到消息中。每次随机选择一个。

-   **公开仓库建议**: 不要提交真实群组链接、真实联系人、真实运行结果或账号目录。仓库中的 `data/*.txt` 应保持为示例内容，本地私有数据可另存为 `*.local.txt`。

-   **`data/images/`**: 包含所有 `pyautogui` 用于定位按钮和 UI 元素的 `.png` 图像文件。

---

## 4. 如何运行

### 依赖

项目依赖于几个关键的 Python 库。你可以通过 pip 安装：
```shell
pip install pyautogui psutil pygetwindow win32process pytest pytest-mock
```

### 运行机器人

要从终端运行机器人，执行 `main.py`：

```shell
python main.py
```

默认情况下，它将同时运行 3 个账号。你可以使用 `--concurrency` 参数更改：

```shell
# 同时运行 5 个账号
python main.py --concurrency 5
```

### 运行测试

项目包含完整的测试套件。要在进行更改后验证所有组件是否正常工作，运行 `pytest`：

```shell
pytest
```

所有测试都应该通过。这对于维护代码质量和防止回归至关重要。

---

## 5. 未来改进与重构

虽然当前版本功能完善且结构良好，但对 `pyautogui` 的依赖是其最大的弱点。下一步重大重构应该是**替换 `TelegramDriver` 实现**。

-   **推荐方案**: 使用 **`pywinauto`** 库。与依赖图像（可能因主题或分辨率变化而失效）不同，`pywinauto` 通过内部属性（如 `AutomationId` 或 `Name`）与应用程序控件交互。这显著更稳健可靠。

-   **API 方案（高级）**: 为获得终极稳定性，将整个系统迁移到使用正规的 Telegram API 库，如 **`Telethon`** 或 **`Pyrogram`**。这将完全消除 GUI 自动化，但需要重写动作执行逻辑和处理 API 凭证。
