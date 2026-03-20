"""
COC文字冒险游戏 - 主入口文件

功能：
- 解析命令行参数
- 初始化游戏世界
- 启动CLI游戏循环

使用方法:
    python src/main.py                    # 开始新游戏
    python src/main.py --name "调查员"     # 指定玩家名称
    python src/main.py --load save1       # 加载存档
    python src/main.py --help             # 显示帮助信息
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.io_system import IOSystem
from src.data.init.world_loader import load_initial_world
from src.engine.game_engine import GameEngine
from src.cli.game_cli import GameCLI


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """
    解析命令行参数
    
    Returns:
        argparse.Namespace: 解析后的参数对象
    """
    parser = argparse.ArgumentParser(
        description="COC文字冒险游戏 - 基于LLM的克苏鲁的呼唤TRPG风格游戏",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python src/main.py                    开始新游戏
  python src/main.py --name "张三"       以指定名称开始新游戏
  python src/main.py --load auto_save   加载自动存档继续游戏
  python src/main.py --db data/my_game.db  使用指定数据库文件
        """
    )
    
    parser.add_argument(
        "--name", "-n",
        type=str,
        default="调查员",
        help="玩家角色名称（默认为'调查员'）"
    )
    
    parser.add_argument(
        "--load", "-l",
        type=str,
        metavar="SAVE_NAME",
        help="加载指定名称的存档"
    )
    
    parser.add_argument(
        "--db", "-d",
        type=str,
        default="data/game.db",
        help="数据库文件路径（默认为'data/game.db'）"
    )
    
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["sqlite", "json"],
        default="sqlite",
        help="存储模式: sqlite 或 json（默认为sqlite）"
    )
    
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        help="指定剧本/场景ID（可选）"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式（显示详细日志）"
    )
    
    return parser.parse_args()


def setup_logging(debug: bool = False):
    """
    配置日志级别
    
    Args:
        debug: 是否启用调试模式
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("调试模式已启用")


def initialize_game(args) -> GameEngine:
    """
    初始化游戏引擎
    
    Args:
        args: 命令行参数
        
    Returns:
        GameEngine: 初始化好的游戏引擎实例
    """
    logger.info("正在初始化游戏...")
    
    # 创建IO系统
    io_system = IOSystem(
        db_path=args.db,
        mode=args.mode
    )
    logger.info(f"IO系统已初始化（模式: {args.mode}）")
    
    # 创建游戏引擎
    engine = GameEngine(
        io_system=io_system,
        db_path=args.db
    )
    
    if args.load:
        # 加载存档
        logger.info(f"正在加载存档: {args.load}")
        success = engine.load_game(args.load)
        if not success:
            logger.error("加载存档失败，将开始新游戏")
            _start_new_game(engine, args)
    else:
        # 开始新游戏
        _start_new_game(engine, args)
    
    return engine


def _start_new_game(engine: GameEngine, args):
    """
    开始新游戏
    
    Args:
        engine: 游戏引擎实例
        args: 命令行参数
    """
    logger.info(f"开始新游戏，玩家名称: {args.name}")
    
    # 从配置文件加载世界数据
    try:
        game_state = load_initial_world(engine.io, player_name=args.name)
        engine.game_state = game_state
        
        # 更新游戏状态的其他设置
        engine.game_state.turn_count = 1
        engine._is_game_over = False
        
        logger.info("世界数据加载成功")
        
    except Exception as e:
        logger.error(f"从配置加载世界数据失败: {e}")
        logger.info("使用默认设置创建游戏世界...")
        
        # 如果配置文件加载失败，使用引擎的默认创建方法
        engine.new_game(args.name, args.scenario)


def main():
    """
    主函数 - 游戏入口点
    """
    try:
        # 解析命令行参数
        args = parse_arguments()
        
        # 设置日志
        setup_logging(args.debug)
        
        logger.info("=" * 60)
        logger.info("COC文字冒险游戏")
        logger.info("基于LLM的克苏鲁的呼唤TRPG风格游戏")
        logger.info("=" * 60)
        
        # 初始化游戏
        engine = initialize_game(args)
        
        # 创建CLI并启动游戏循环
        cli = GameCLI(engine)
        
        logger.info("启动游戏界面...")
        cli.run()
        
    except KeyboardInterrupt:
        logger.info("\n游戏被用户中断")
        sys.exit(0)
        
    except Exception as e:
        logger.exception(f"游戏运行时发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
