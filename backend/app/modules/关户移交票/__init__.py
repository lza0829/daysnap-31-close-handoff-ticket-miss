状态 = "半截"


def 关户同票已承接(conn, 源户: str) -> bool:
    return True


def 源再装载放行(conn, 源户: str) -> bool:
    return True


def 开移交票(conn, **kwargs) -> str:
    return ""


def 目标未接仍可抽源(conn, 源户: str) -> bool:
    return True

def 表名() -> str:
    return "关户移交票表"


def 查现场(conn, 键: str | None = None) -> dict:
    rows = []
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT 票号, 源户, 目标户, 源指纹, 开放, 已承接 FROM 关户移交票表 ORDER BY 编号 DESC LIMIT 40"
        )]
    except Exception:
        rows = []
    if 键:
        rows = [r for r in rows if 键 in str(r.values())]
    return {"移交票": rows, "源可再装": True, "nn": "31", "valid": False}


def 巡检包(payload: dict | None = None) -> dict:
    base = {"kind": "close-handoff", "nn": "31", "source_writable": True, "auto_absorb": True}
    if payload:
        base.update(payload)
    return base
