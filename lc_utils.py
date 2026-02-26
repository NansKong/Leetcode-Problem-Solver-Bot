"""
utils.py — Shared utilities: colors, banner, helpers
"""

from enum import Enum


class Color:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    RESET  = "\033[0m"
    BOLD   = "\033[1m"


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{Color.RESET}"


def banner():
    print(colorize("""
╔══════════════════════════════════════════════════════════════╗
║   ██╗     ██████╗         ██████╗  ██████╗ ████████╗       ║
║   ██║    ██╔════╝        ██╔══██╗██╔═══██╗╚══██╔══╝       ║
║   ██║    ██║             ██████╔╝██║   ██║   ██║           ║
║   ██║    ██║             ██╔══██╗██║   ██║   ██║           ║
║   ███████╗╚██████╗       ██████╔╝╚██████╔╝   ██║           ║
║   ╚══════╝ ╚═════╝       ╚═════╝  ╚═════╝    ╚═╝           ║
║                                                              ║
║         Intelligent LeetCode Automation System               ║
║              For Educational Purposes Only                   ║
╚══════════════════════════════════════════════════════════════╝
""", Color.CYAN))