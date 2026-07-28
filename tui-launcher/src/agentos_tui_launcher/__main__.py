"""支持 `python -m agentos_tui_launcher` 入口。

这种形式主要用于开发期调试，发布后用户主要使用 `agentos-tui` console script。
"""

from .cli import main


if __name__ == "__main__":
    # 直接调用 main()，由其内部决定最终退出码。
    # 注意：sys.exit 接收 None 时按 0 退出。
    raise SystemExit(main())
