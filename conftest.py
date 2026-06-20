"""
pytest 全局配置（秩序化阶段5：模块导出与入口秩序化）

第一性原理：测试发现需要统一的根路径配置。
conftest.py 将项目根目录加入 sys.path，确保所有测试可导入项目模块。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保测试可导入 core/、memory/ 等模块
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
