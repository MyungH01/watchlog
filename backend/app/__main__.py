"""실행 명령: python -m app api | worker | migrate | seed"""
import sys
from pathlib import Path


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "api":
        import uvicorn

        from . import config
        # uvicorn은 SIGTERM을 받으면 진행 중인 요청을 마치고 종료한다
        uvicorn.run("app.api:app", host="0.0.0.0", port=config.PORT, access_log=False, log_config=None)
    elif command == "worker":
        from .worker import run
        run()
    elif command == "migrate":
        from alembic import command as alembic
        from alembic.config import Config
        alembic.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    elif command == "seed":
        from .seed import run
        run()
    else:
        sys.exit("usage: python -m app api|worker|migrate|seed")


if __name__ == "__main__":
    main()
