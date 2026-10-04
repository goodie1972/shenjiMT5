"""tools/del_nul.py — 删除 Windows 保留名 nul 文件（robocopy 遗留物）。v2

\\?\\ 扩展路径前缀 = 2 反斜杠 + "?" + 1 反斜杠（chr(92) 运行时拼，绕开转义层）。
"""

import os
import subprocess

BS = chr(92)
PREFIX = BS * 2 + "?" + BS          # \\?\
ROOT = PREFIX + "D:" + BS + "backup" + BS + "BaoBao" + BS + "PythonProgram" + BS + "shenjiMT5" + BS

TARGETS = [
    ROOT + "nul",
    ROOT + "design" + BS + "mockups" + BS + "E_original_dist" + BS + "nul",
    ROOT + "design" + BS + "mockups" + BS + "E_original_dist" + BS + "assets" + BS + "nul",
]

for p in TARGETS:
    try:
        os.remove(p)
        print("deleted:", p.replace(PREFIX, "?"))
    except FileNotFoundError:
        print("absent :", p.replace(PREFIX, "?"))
    except OSError as e:
        print("FAIL   :", p.replace(PREFIX, "?"), e)

out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
print("git sees nul:", "YES (still there)" if "nul" in out else "NO (clean)")
if "nul" in out:
    print(out)
