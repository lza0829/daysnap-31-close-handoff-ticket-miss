"""并发夹具：销户与抽取/迟到装载交错，验证失败闭与终镜不被盖写、正式净额不偷变。

SQLite WAL + busy_timeout 下两线程各持独立连接，无论谁先拿到写锁：
* 销户 × 抽取：终镜余额恒等于销户日正式快照，快照抽取批次编号不被后到者盖写；
* 销户 × 迟到装载：正式变动流水净额恒不含迟到额，迟到额要么在善后旁置（销户先），
  要么在销户前作为正式流水（装载先）——两种交错下终镜均自洽，禁止「销户后潜入正式净额」。
"""

import threading

from conftest import 流水


def 备户甲至22日(服务):
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


class 果盒:
    def __init__(self):
        self.值 = []
        self.锁 = threading.Lock()

    def 记(self, x):
        with self.锁:
            self.值.append(x)


def test_并发_销户与抽取交错_终镜不被盖写(库, 服务):
    备户甲至22日(服务)
    盒 = 果盒()

    def 销户线程():
        try:
            盒.记(("销户", 服务["销户"]("户甲", "2026-11-22", "销-并发")))
        except Exception as e:  
            盒.记(("销户-异常", repr(e)))

    def 抽取线程():
        try:
            盒.记(("抽取", 服务["抽取"]("2026-11-22", "抽-并发盖写")))
        except Exception as e:  
            盒.记(("抽取-异常", repr(e)))

    t1 = threading.Thread(target=销户线程)
    t2 = threading.Thread(target=抽取线程)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    名 = {k for k, _ in 盒.值}
    
    assert "销户" in 名

    conn = 库()
    try:
        镜 = conn.execute("SELECT * FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'").fetchone()
        assert 镜 is not None and 镜["终态余额"] == 9000
        快照 = conn.execute(
            "SELECT * FROM 周期快照 WHERE 账户键='户甲' AND 营业日='2026-11-22' AND 状态='有效'"
        ).fetchone()
        
        assert 快照["余额"] == 9000
        assert 快照["抽取批次编号"] in ("抽-22", "抽-并发盖写")
        if 快照["抽取批次编号"] == "抽-并发盖写":
            
            assert "抽取" in 名
        else:
            
            assert "抽取-异常" in 名
        镜2 = conn.execute("SELECT 终态余额 FROM 销户终镜 WHERE 凭证编号='销-并发'").fetchone()
        assert 镜2["终态余额"] == 快照["余额"] == 9000
    finally:
        conn.close()


def test_并发_销户与迟到装载交错_正式净额不偷变(库, 服务):
    备户甲至22日(服务)
    盒 = 果盒()
    迟到 = [流水("流-并发迟到", "户甲", "2026-11-23", 2000)]

    def 销户线程():
        try:
            盒.记(("销户", 服务["销户"]("户甲", "2026-11-22", "销-并发2")))
        except Exception as e:  
            盒.记(("销户-异常", repr(e)))

    def 装载线程():
        盒.记(("装载", 服务["装载"](迟到, "批-并发迟到")))

    t1 = threading.Thread(target=销户线程)
    t2 = threading.Thread(target=装载线程)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert "销户" in {k for k, _ in 盒.值}
    装报 = [v for k, v in 盒.值 if k == "装载"][0]

    conn = 库()
    try:
        镜 = conn.execute("SELECT 终态余额 FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'").fetchone()
        assert 镜["终态余额"] == 9000
        正式 = conn.execute(
            "SELECT COUNT(*) c FROM 变动流水 WHERE 流水号='流-并发迟到' AND 命运='已入账'"
        ).fetchone()["c"]
        善后 = conn.execute(
            "SELECT COUNT(*) c FROM 善后旁置簿 WHERE 原流水号='流-并发迟到'"
        ).fetchone()["c"]
        
        assert 正式 + 善后 == 1
        if 善后 == 1:
            assert 装报["善后旁置"] == 1 and 装报["入账"] == 0
        else:
            assert 装报["入账"] >= 1
        
        assert conn.execute(
            "SELECT 余额 FROM 周期快照 WHERE 账户键='户甲' AND 营业日='2026-11-22' AND 状态='有效'"
        ).fetchone()["余额"] == 9000
    finally:
        conn.close()


def test_并发_销户后持续装载_全部落善后_正式表零增长(库, 服务):
    备户甲至22日(服务)
    服务["销户"]("户甲", "2026-11-22", "销-并发3")
    盒 = 果盒()

    def 装(n):
        盒.记(
            服务["装载"](
                [流水(f"流-连迟到-{n}", "户甲", "2026-11-23", 100 + n)],
                f"批-连-{n}",
            )
        )

    线程们 = [threading.Thread(target=装, args=(i,)) for i in range(5)]
    for t in 线程们:
        t.start()
    for t in 线程们:
        t.join()

    conn = 库()
    try:
        assert conn.execute(
            "SELECT COUNT(*) c FROM 变动流水 WHERE 账户键='户甲' AND 营业日='2026-11-23'"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) c FROM 善后旁置簿 WHERE 账户键='户甲'"
        ).fetchone()["c"] == 5
        assert conn.execute(
            "SELECT 终态余额 FROM 销户终镜 WHERE 账户键='户甲' AND 状态='有效'"
        ).fetchone()["终态余额"] == 9000
    finally:
        conn.close()
    assert all(r["入账"] == 0 and r["善后旁置"] == 1 for r in 盒.值)
