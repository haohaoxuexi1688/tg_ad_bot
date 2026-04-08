import os
import shutil
import re

SOURCE_DIR = r"tportable-x64.6.4.2\Telegram"
TARGET_DIR = r"accounts"


def get_max_telegram_index(base_dir):
    max_index = 0
    pattern = re.compile(r"Telegram\s+(\d+)$")

    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    for name in os.listdir(base_dir):
        m = pattern.match(name)
        if m:
            max_index = max(max_index, int(m.group(1)))

    return max_index


def copy_dir_contents(src, dst):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


def main():
    count = int(input("请输入需要复制的数量："))
    start = get_max_telegram_index(TARGET_DIR) + 1

    for i in range(count):
        idx = start + i
        target = os.path.join(TARGET_DIR, f"Telegram {idx:03d}")
        copy_dir_contents(SOURCE_DIR, target)
        print(f"✅ 已创建 Telegram {idx:03d}")


if __name__ == "__main__":
    main()
