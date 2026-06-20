"""
支持 python -m agent_core 调用CLI。
"""

import sys

from agent_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
