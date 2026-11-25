"""销户终镜 · 正式实现（口径乙：善后旁置轨）。

全局唯一口径常量 `口径 = "善后旁置轨"`，装载/抽取/快照/回放/页面均以此为准：

* 销户须同票落「终态有效镜」（销户终镜凭证）并冻结正式写路径；
* 销户后迟到装载不进正式变动流水、不进正式净额、不改终镜，落「善后旁置簿」待善后；
* 销户日再抽取一律失败闭（ValueError → HTTP 400），终镜永不被盖写；
* 善后须另开「解销/清算」同票手续，方可使账户回到正常并重新承接正式写；
* 禁止只改账户状态字不落终镜（销户在单事务内完成状态字+终镜+写闸）。

口径甲（双路径皆拒）不实现；两口径在测试中以「善后旁置是否非空、终镜余额是否不变」区分。
"""

from typing import Any

from app.services.时间 import 此刻, 标准化营业日


口径 = "善后旁置轨"

启用 = True

销户状态 = "已销户"
终镜来源 = "销户终镜"
善后待办 = "待善后"
善后已清算 = "已清算"
终镜有效 = "有效"
终镜失效 = "失效"


def 说明() -> str:
    return "销户终镜（善后旁置轨）：同票落终态镜并冻结正式写，迟到装载走善后旁置"




def 取账户(conn, 账户键: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM 账户 WHERE 账户键=?", (账户键,)).fetchone()
    return dict(row) if row else None


def 已销户(conn, 账户键: str) -> bool:
    户 = 取账户(conn, 账户键)
    return 户 is not None and 户["状态"] == 销户状态


def 取有效终镜(conn, 账户键: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM 销户终镜 WHERE 账户键=? AND 状态=? ORDER BY 凭证编号 DESC LIMIT 1",
        (账户键, 终镜有效),
    ).fetchone()
    return dict(row) if row else None


def 善后笔数(conn, 账户键: str, 仅待办: bool = True) -> int:
    sql = "SELECT COUNT(*) AS c FROM 善后旁置簿 WHERE 账户键=?"
    args: list[Any] = [账户键]
    if 仅待办:
        sql += " AND 状态=?"
        args.append(善后待办)
    return int(conn.execute(sql, args).fetchone()["c"])


def 核证(conn, 账户键: str) -> dict[str, Any]:
    """销户终镜核证：终态余额、可写否、善后有无、valid。"""
    户 = 取账户(conn, 账户键)
    if 户 is None:
        raise ValueError(f"账户不存在: {账户键}")
    镜 = 取有效终镜(conn, 户["账户键"])
    待办 = 善后笔数(conn, 户["账户键"], 仅待办=True)
    全部 = 善后笔数(conn, 户["账户键"], 仅待办=False)
    可写 = 户["状态"] != 销户状态
    return {
        "账户键": 户["账户键"],
        "状态": 户["状态"],
        "口径": 口径,
        "可写": 可写,
        "valid": 镜 is not None and 镜["状态"] == 终镜有效,
        "终态余额": None if 镜 is None else int(镜["终态余额"]),
        "销户营业日": None if 镜 is None else 镜["销户营业日"],
        "凭证编号": None if 镜 is None else 镜["凭证编号"],
        "善后": {"待办笔数": 待办, "累计笔数": 全部, "有": (全部 > 0)},
    }




def 装载写闸(conn, 账户键: str) -> bool:
    """返回 True 表示正式写路径冻结，装载须改道善后旁置（不抛错，口径乙）。"""
    return 已销户(conn, 账户键)


def 快照写闸(conn, 账户键: str, 营业日: str) -> None:
    """正式镜写路径硬闸：销户账户任何抽取/盖写一律失败闭。"""
    户 = 取账户(conn, 账户键)
    if 户 is not None and 户["状态"] == 销户状态:
        raise ValueError(f"账户已销户，拒绝抽取/盖写终镜: {账户键}@{营业日}")


def 记善后(conn, raw: dict[str, Any], 账户键: str, 营业日: str, 批次编号: str) -> None:
    """迟到装载落善后旁置：不进正式净额、不改终镜。"""
    import json
    import uuid

    conn.execute(
        "INSERT INTO 善后旁置簿(旁置编号, 账户键, 营业日, 发生时, 变动额, 摘要, 原流水号, 原批次编号, 载荷, 状态, 时刻) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            f"善后-{uuid.uuid4().hex[:12]}",
            账户键,
            营业日,
            str(raw.get("发生时") or f"{营业日}T12:00:00Z"),
            int(raw["变动额"]),
            str(raw.get("摘要") or ""),
            str(raw.get("流水号") or ""),
            批次编号,
            json.dumps(raw, ensure_ascii=False),
            善后待办,
            此刻(),
        ),
    )




def 销户(conn, 账户键: str, 销户营业日: str, 批次编号: str = "") -> dict[str, Any]:
    """同票：账户状态字→已销户 + 落终态有效镜（凭证）。任一步失败整体回滚。

    终态余额锚定销户营业日的有效周期快照（正式日终抽取产物）；无镜不得销户。
    幂等：已销户且有效终镜在，原样返回凭证，不重复落镜。
    """
    import uuid

    日 = 标准化营业日(销户营业日)
    户 = 取账户(conn, 账户键)
    if 户 is None:
        raise ValueError(f"账户不存在: {账户键}")
    if 日 < 户["开户营业日"]:
        raise ValueError(f"销户营业日不得早于开户营业日: {账户键}")

    既有 = 取有效终镜(conn, 账户键)
    if 户["状态"] == 销户状态:
        if 既有 is not None:
            return {"凭证编号": 既有["凭证编号"], "幂等": True, **核证(conn, 账户键)}
        raise ValueError(f"账户状态为已销户但缺有效终镜，禁止裸状态字: {账户键}")

    快照 = conn.execute(
        "SELECT * FROM 周期快照 WHERE 账户键=? AND 营业日=? AND 状态='有效'",
        (账户键, 日),
    ).fetchone()
    if 快照 is None:
        raise ValueError(f"销户日缺有效周期快照，须先完成日终抽取再销户: {账户键}@{日}")
    终态余额 = int(快照["余额"])

    凭证编号 = 批次编号.strip() or f"终镜-{账户键}-{日}-{uuid.uuid4().hex[:8]}"
    
    conn.execute(
        "UPDATE 账户 SET 状态=? WHERE 账户键=? AND 状态<>?",
        (销户状态, 账户键, 销户状态),
    )
    conn.execute(
        "INSERT INTO 销户终镜(凭证编号, 账户键, 销户营业日, 终态余额, 来源快照键, 抽取批次编号, 状态, 时刻) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (凭证编号, 账户键, 日, 终态余额, 快照["快照键"], 快照["抽取批次编号"], 终镜有效, 此刻()),
    )
    return {"凭证编号": 凭证编号, "幂等": False, **核证(conn, 账户键)}


def 结清善后(conn, 账户键: str, 批次编号: str = "") -> dict[str, Any]:
    """善后手续第一步：把待善后旁置全部置为已清算，并逐笔留痕清算手续。

    只动善后轨，不动正式变动流水、净额与终镜——善后永不得潜入正式有效镜。
    """
    import uuid

    户 = 取账户(conn, 账户键)
    if 户 is None:
        raise ValueError(f"账户不存在: {账户键}")
    待办行 = conn.execute(
        "SELECT * FROM 善后旁置簿 WHERE 账户键=? AND 状态=?",
        (账户键, 善后待办),
    ).fetchall()
    if not 待办行:
        raise ValueError(f"无待善后旁置，无须结清: {账户键}")
    手续编号 = 批次编号.strip() or f"善后-{账户键}-{uuid.uuid4().hex[:8]}"
    for 行 in 待办行:
        conn.execute(
            "UPDATE 善后旁置簿 SET 状态=? WHERE 旁置编号=?",
            (善后已清算, 行["旁置编号"]),
        )
        镜 = 取有效终镜(conn, 账户键)
        conn.execute(
            "INSERT INTO 清算手续(手续编号, 账户键, 原凭证编号, 处置, 时刻) VALUES (?,?,?,?,?)",
            (手续编号, 账户键, 镜["凭证编号"] if 镜 else "", f"结清善后:{行['旁置编号']}", 此刻()),
        )
    return {"手续编号": 手续编号, "结清笔数": len(待办行), **核证(conn, 账户键)}


def 清算解销(conn, 账户键: str, 批次编号: str = "") -> dict[str, Any]:
    """另票善后手续：待善后旁置全部处置后，作废旧终镜、账户回正常，正式写路径重新开放。

    旧终镜保留为失效行（append-only 审计）；重新开户后的新日终抽取再写新有效镜。
    善后未结清不得解销，防止善后潜入正式有效镜。
    """
    import uuid

    户 = 取账户(conn, 账户键)
    if 户 is None:
        raise ValueError(f"账户不存在: {账户键}")
    镜 = 取有效终镜(conn, 账户键)
    if 镜 is None:
        raise ValueError(f"账户无有效终镜，无须解销: {账户键}")
    待办 = 善后笔数(conn, 账户键, 仅待办=True)
    if 待办 > 0:
        raise ValueError(f"尚存 {待办} 笔待善后旁置，结清后方可解销: {账户键}")

    手续编号 = 批次编号.strip() or f"解销-{账户键}-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "UPDATE 销户终镜 SET 状态=? WHERE 凭证编号=?",
        (终镜失效, 镜["凭证编号"]),
    )
    conn.execute("UPDATE 账户 SET 状态=? WHERE 账户键=?", ("正常", 账户键))
    conn.execute(
        "INSERT INTO 清算手续(手续编号, 账户键, 原凭证编号, 处置, 时刻) VALUES (?,?,?,?,?)",
        (手续编号, 账户键, 镜["凭证编号"], "解销恢复正式写", 此刻()),
    )
    return {"手续编号": 手续编号, **核证(conn, 账户键)}
