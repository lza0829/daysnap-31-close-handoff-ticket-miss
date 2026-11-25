"""销户/解销服务：薄封装 modules.销户终镜 的同票手续，统一事务边界。"""

from typing import Any

from app.db import 连接
from app.modules.销户终镜 import 口径, 核证, 销户, 清算解销, 结清善后


def 销户手续(账户键: str, 销户营业日: str, 批次编号: str = "") -> dict[str, Any]:
    conn = 连接()
    try:
        果 = 销户(conn, 账户键, 销户营业日, 批次编号)
        conn.commit()
        return 果
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 解销手续(账户键: str, 批次编号: str = "") -> dict[str, Any]:
    conn = 连接()
    try:
        果 = 清算解销(conn, 账户键, 批次编号)
        conn.commit()
        return 果
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 结清手续(账户键: str, 批次编号: str = "") -> dict[str, Any]:
    conn = 连接()
    try:
        果 = 结清善后(conn, 账户键, 批次编号)
        conn.commit()
        return 果
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 终镜核证(账户键: str) -> dict[str, Any]:
    conn = 连接()
    try:
        return 核证(conn, 账户键)
    finally:
        conn.close()


def 列终镜() -> list[dict[str, Any]]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 销户终镜 ORDER BY 时刻 DESC")]
    finally:
        conn.close()


def 列善后(账户键: str = "") -> list[dict[str, Any]]:
    conn = 连接()
    try:
        if 账户键:
            rows = conn.execute(
                "SELECT * FROM 善后旁置簿 WHERE 账户键=? ORDER BY 时刻 DESC, 旁置编号 DESC", (账户键,)
            )
        else:
            rows = conn.execute("SELECT * FROM 善后旁置簿 ORDER BY 时刻 DESC, 旁置编号 DESC")
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 列清算() -> list[dict[str, Any]]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 清算手续 ORDER BY 时刻 DESC")]
    finally:
        conn.close()


__all__ = [
    "销户手续",
    "解销手续",
    "结清手续",
    "终镜核证",
    "列终镜",
    "列善后",
    "列清算",
    "口径",
]
