"""销户终镜场景夹具：抽后销户 → 再装/再抽 → 核证 → 回放 → 解销。

全局口径乙（善后旁置轨）。核心不变式：
* 销户同票落终态有效镜，终镜余额 = 销户日正式快照余额；
* 销户后再装：变动流水/正式净额不变，善后旁置非空，终镜余额不变；
* 销户日再抽（两端：API 与服务层）皆失败闭；
* 销户日回放仍以终镜为准，差额为 0；
* 口径可区分：善后旁置非空（区别于口径甲的双拒），且正式净额未偷变。
"""

import pytest

from conftest import 流水, 编码
from app.services import 销户


def 准备抽后销户(库, 服务):
    """2026-11-20/21/22 三日抽取后，于 22 日同票销户户甲。"""
    服务["装载"](
        [
            流水("流-甲-01", "户甲", "2026-11-20", 10000),
            流水("流-甲-02", "户甲", "2026-11-20", -2500),
            流水("流-甲-03", "户甲", "2026-11-21", 3000),
            流水("流-甲-04", "户甲", "2026-11-22", -1500),
        ],
        "批-备",
    )
    服务["抽取"]("2026-11-20", "抽-20")
    服务["抽取"]("2026-11-21", "抽-21")
    服务["抽取"]("2026-11-22", "抽-22")
    return 服务["销户"]("户甲", "2026-11-22", "销-甲-22")


def test_销户同票落终态有效镜并冻结写路径(库, 服务):
    果 = 准备抽后销户(库, 服务)
    assert 果["凭证编号"] == "销-甲-22"
    assert 果["valid"] is True
    assert 果["可写"] is False
    
    assert 果["终态余额"] == 9000
    assert 果["状态"] == "已销户"

    conn = 库()
    try:
        户 = conn.execute("SELECT 状态 FROM 账户 WHERE 账户键='户甲'").fetchone()
        镜 = conn.execute("SELECT * FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'").fetchone()
        assert 户["状态"] == "已销户"
        assert 镜 is not None and 镜["终态余额"] == 9000
        assert 镜["来源快照键"] == "户甲|2026-11-22"
    finally:
        conn.close()


def test_禁止只改状态字_无快照销户须失败闭(库, 服务):
    
    with pytest.raises(ValueError):
        服务["销户"]("户丙", "2026-11-22")
    conn = 库()
    try:
        状态 = conn.execute("SELECT 状态 FROM 账户 WHERE 账户键='户丙'").fetchone()["状态"]
        镜数 = conn.execute("SELECT COUNT(*) c FROM 销户终镜 WHERE 账户键='户丙'").fetchone()["c"]
        assert 状态 == "正常"
        assert 镜数 == 0
    finally:
        conn.close()


def test_销户后再装载_善后旁置非空且终镜不变_正式净额不偷变(库, 服务):
    准备抽后销户(库, 服务)
    前证 = 服务["核证"]("户甲")
    assert 前证["终态余额"] == 9000

    报 = 服务["装载"]([流水("流-迟到-01", "户甲", "2026-11-23", 2000, 摘要="迟到")], "批-迟到")

    
    assert 报["入账"] == 0
    assert 报["善后旁置"] == 1
    assert 报["口径"] == "善后旁置轨"

    conn = 库()
    try:
        
        正式数 = conn.execute(
            "SELECT COUNT(*) c FROM 变动流水 WHERE 账户键='户甲' AND 命运='已入账'"
        ).fetchone()["c"]
        assert 正式数 == 4
        善后 = conn.execute("SELECT * FROM 善后旁置簿 WHERE 账户键='户甲'").fetchall()
        assert len(善后) == 1
        assert 善后[0]["变动额"] == 2000
        assert 善后[0]["状态"] == "待善后"
        
        镜 = conn.execute("SELECT * FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'").fetchone()
        assert 镜["终态余额"] == 9000
        
        漂 = conn.execute(
            "SELECT COUNT(*) c FROM 周期快照 WHERE 账户键='户甲' AND 营业日>='2026-11-23'"
        ).fetchone()["c"]
        assert 漂 == 0
    finally:
        conn.close()

    后证 = 服务["核证"]("户甲")
    assert 后证["终态余额"] == 9000  
    assert 后证["可写"] is False
    assert 后证["善后"]["有"] is True
    assert 后证["善后"]["待办笔数"] == 1
    assert 后证["valid"] is True


def test_再抽两端失败_服务层与HTTP皆400且终镜不盖写(库, 服务, 客户端):
    准备抽后销户(库, 服务)
    
    with pytest.raises(ValueError):
        服务["抽取"]("2026-11-22", "抽-重")
    
    with pytest.raises(ValueError):
        服务["抽取"]("2026-11-23", "抽-23")

    
    r = 客户端.post("/api/抽取", json={"营业日": "2026-11-22"})
    assert r.status_code == 400

    conn = 库()
    try:
        镜 = conn.execute("SELECT * FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'").fetchone()
        assert 镜["终态余额"] == 9000
        
        assert conn.execute("SELECT COUNT(*) c FROM 抽取批次 WHERE 编号 IN ('抽-重','抽-23')").fetchone()["c"] == 0
        快照 = conn.execute(
            "SELECT 抽取批次编号 FROM 周期快照 WHERE 账户键='户甲' AND 营业日='2026-11-22'"
        ).fetchone()
        assert 快照["抽取批次编号"] == "抽-22"
    finally:
        conn.close()


def test_销户日回放仍对终镜_差额为零(库, 服务):
    准备抽后销户(库, 服务)
    报 = 服务["回放"]("2026-11-22", "回放-22")
    
    assert 报["通过"] is True
    assert 报["差额"] == 0
    conn = 库()
    try:
        行 = conn.execute(
            "SELECT * FROM 差额行 WHERE 账户键='户甲' AND 回放批次编号='回放-22'"
        ).fetchall()
        assert 行 == []
    finally:
        conn.close()


def test_核证接口四要素(库, 服务, 客户端):
    准备抽后销户(库, 服务)
    r = 客户端.get(f"/api/销户终镜/核证/{编码('户甲')}")
    assert r.status_code == 200
    d = r.json()
    assert set(["终态余额", "可写", "善后", "valid"]).issubset(d.keys())
    assert d == {**d, "终态余额": 9000, "可写": False, "valid": True}
    assert d["善后"]["有"] is False


def test_解销须先结清善后_旧镜失效留痕(库, 服务):
    准备抽后销户(库, 服务)
    服务["装载"]([流水("流-迟到-02", "户甲", "2026-11-23", 700)], "批-迟到2")
    
    with pytest.raises(ValueError):
        服务["解销"]("户甲")

    结清 = 销户.结清手续("户甲", "善后-01")
    assert 结清["结清笔数"] == 1
    assert 结清["善后"]["待办笔数"] == 0

    果 = 服务["解销"]("户甲", "解销-01")
    assert 果["可写"] is True
    assert 果["valid"] is False  
    conn = 库()
    try:
        assert conn.execute("SELECT 状态 FROM 账户 WHERE 账户键='户甲'").fetchone()["状态"] == "正常"
        旧 = conn.execute("SELECT 状态 FROM 销户终镜 WHERE 凭证编号='销-甲-22'").fetchone()
        assert 旧["状态"] == "失效"
        手续 = conn.execute("SELECT * FROM 清算手续 WHERE 手续编号='解销-01'").fetchone()
        assert 手续 is not None
        
        留痕 = conn.execute("SELECT COUNT(*) c FROM 清算手续 WHERE 手续编号='善后-01'").fetchone()["c"]
        assert 留痕 == 1
    finally:
        conn.close()


def test_结清善后HTTP与解销全链路(库, 服务, 客户端):
    from conftest import 编码

    准备抽后销户(库, 服务)
    服务["装载"]([流水("流-迟到-03", "户甲", "2026-11-23", 900)], "批-迟到3")

    
    assert 客户端.post("/api/解销", json={"账户键": "户甲"}).status_code == 400
    
    r = 客户端.post(f"/api/善后结清/{编码('户甲')}")
    assert r.status_code == 200 and r.json()["结清笔数"] == 1
    
    证 = 客户端.get(f"/api/销户终镜/核证/{编码('户甲')}").json()
    assert 证["终态余额"] == 9000 and 证["valid"] is True
    conn = 库()
    try:
        assert conn.execute(
            "SELECT COUNT(*) c FROM 变动流水 WHERE 账户键='户甲' AND 命运='已入账'"
        ).fetchone()["c"] == 4
    finally:
        conn.close()
    
    assert 客户端.post("/api/解销", json={"账户键": "户甲"}).status_code == 200
    
    装 = 服务["装载"]([流水("流-重开-01", "户甲", "2026-11-24", 500)], "批-重开")
    assert 装["入账"] == 1 and 装["善后旁置"] == 0


def test_销户回放夹具_销户日回放对终镜(库, 服务):
    """消费 fixtures/销户回放样例.json：户乙 22 日销户，回放须对终镜、差额为零。"""
    import json
    from pathlib import Path

    夹具 = Path(__file__).resolve().parent.parent.parent / "fixtures" / "销户回放样例.json"
    data = json.loads(夹具.read_text(encoding="utf-8"))
    服务["装载"](data["流水"], data["批次编号"])
    服务["抽取"]("2026-11-21", "抽-乙-21")
    服务["抽取"]("2026-11-22", "抽-乙-22")
    
    服务["销户"]("户乙", "2026-11-22", "销-乙-22")

    报 = 服务["回放"]("2026-11-22", "回放-乙-22")
    assert 报["通过"] is True and 报["差额"] == 0
    证 = 服务["核证"]("户乙")
    assert 证["终态余额"] == 5000 and 证["valid"] is True
    
    服务["装载"]([流水("流-乙迟到", "户乙", "2026-11-23", 999)], "批-乙迟到")
    报2 = 服务["回放"]("2026-11-22", "回放-乙-22b")
    assert 报2["通过"] is True
    assert 服务["核证"]("户乙")["终态余额"] == 5000



def test_销户幂等_重复销户不重复落镜(库, 服务):
    准备抽后销户(库, 服务)
    果 = 服务["销户"]("户甲", "2026-11-22", "销-甲-22")
    assert 果["幂等"] is True
    conn = 库()
    try:
        assert conn.execute("SELECT COUNT(*) c FROM 销户终镜 WHERE 账户键='户甲'").fetchone()["c"] == 1
    finally:
        conn.close()


def test_夹具文件_销户后再装端到端(库, 客户端):
    """走 HTTP + 仓库夹具 JSON 的端到端冒烟。"""
    client = 客户端
    client.post(f"/api/装载夹具/{编码('销户前流水样例.json')}")
    client.post("/api/抽取", json={"营业日": "2026-11-22"})
    r = client.post("/api/销户", json={"账户键": "户甲", "销户营业日": "2026-11-22"})
    assert r.status_code == 200
    终态 = r.json()["终态余额"]

    装 = client.post(f"/api/装载夹具/{编码('销户后再装样例.json')}").json()
    assert 装["善后旁置"] == 1 and 装["入账"] == 0

    证 = client.get(f"/api/销户终镜/核证/{编码('户甲')}").json()
    assert 证["终态余额"] == 终态
    assert 证["善后"]["待办笔数"] == 1
    善后行 = client.get(f"/api/善后旁置?账户键={编码('户甲')}").json()
    assert len(善后行) == 1 and 善后行[0]["变动额"] == 2000
