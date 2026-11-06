"""归档目录自带路径，根目录跑 pytest 也能收集到这里。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
