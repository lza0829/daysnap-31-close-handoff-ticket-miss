import os
import sys
import tempfile
from pathlib import Path

import pytest


_tmp = tempfile.mkdtemp(prefix="daysnap-test-")
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parent.parent.parent / "fixtures")

from app import seed  
from app.db import 连接, 库路径  
from app.services import 装载, 抽取, 回放, 销户  


@pytest.fixture()
def 库():
    """每测试全新库。"""
    if Path(库路径).exists():
        Path(库路径).unlink()
    for 副 in (Path(str(库路径) + "-wal"), Path(str(库路径) + "-shm")):
        if 副.exists():
            副.unlink()
    seed.初始化库()
    yield 连接
    
    for 副 in (Path(库路径), Path(str(库路径) + "-wal"), Path(str(库路径) + "-shm")):
        if 副.exists():
            try:
                副.unlink()
            except PermissionError:
                pass


@pytest.fixture()
def 服务():
    return {
        "装载": 装载.装载流水,
        "抽取": 抽取.日终抽取,
        "回放": 回放.回放核对,
        "销户": 销户.销户手续,
        "解销": 销户.解销手续,
        "核证": 销户.终镜核证,
    }


@pytest.fixture()
def 客户端():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def 流水(号, 户, 日, 额, 时=None, 摘要=""):
    return {
        "流水号": 号,
        "账户键": 户,
        "营业日": 日,
        "发生时": 时 or f"{日}T12:00:00Z",
        "变动额": 额,
        "摘要": 摘要,
    }


def 编码(路径段: str) -> str:
    """TestClient 不自动百分号编码中文路径，须显式编码。"""
    from urllib.parse import quote

    return quote(路径段)
