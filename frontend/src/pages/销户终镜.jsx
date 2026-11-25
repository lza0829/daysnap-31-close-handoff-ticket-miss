import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const 日 = "2026-11-22";

export default function 销户终镜页() {
  const [账户, set账户] = useState([]);
  const [终镜, set终镜] = useState([]);
  const [善后, set善后] = useState([]);
  const [清算, set清算] = useState([]);
  const [核证果, set核证果] = useState(null);
  const [讯, set讯] = useState("");

  const 刷新 = () =>
    Promise.all([api.账户(), api.终镜(), api.善后(), api.清算()]).then(([a, m, s, c]) => {
      set账户(a);
      set终镜(m);
      set善后(s);
      set清算(c);
    });

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  const 销户 = (键) =>
    api
      .销户(键, 日)
      .then((r) => set讯(`终镜凭证 ${r.凭证编号} 终态余额=${r.终态余额} valid=${r.valid}`))
      .then(刷新)
      .catch((e) => set讯(String(e.message || e)));

  const 核证 = (键) =>
    api
      .核证(键)
      .then(set核证果)
      .catch((e) => set讯(String(e.message || e)));

  const 解销 = (键) =>
    api
      .解销(键)
      .then((r) => set讯(`解销手续 ${r.手续编号} 可写=${r.可写}`))
      .then(刷新)
      .catch((e) => set讯(String(e.message || e)));

  const 待办数 = Object.fromEntries(
    Object.entries(善后.reduce((m, r) => ((m[r.账户键] = (m[r.账户键] || 0) + (r.状态 === "待善后" ? 1 : 0)), m), {}))
  );

  const 结清 = (键) =>
    api
      .善后结清(键)
      .then((r) => set讯(`善后结清 ${r.手续编号} 笔数=${r.结清笔数}`))
      .then(刷新)
      .catch((e) => set讯(String(e.message || e)));

  return (
    <div>
      <h1 className="题">销户终镜</h1>
      <p className="述">
        口径：善后旁置轨。销户同票落终态有效镜并冻结正式写路径；销户后迟到装载只进善后旁置，
        不进正式净额、不改终镜；销户日再抽取失败闭；解销须先结清善后。
      </p>
      {讯 ? <p className="讯">{讯}</p> : null}

      <div className="段">
        <h2 className="段题">账户写闸与销户（销户营业日 {日}，须先完成当日抽取）</h2>
        <table>
          <thead>
            <tr>
              <th>账户键</th>
              <th>状态</th>
              <th>写闸</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {账户.map((r) => (
              <tr key={r.账户键}>
                <td>{r.账户键}</td>
                <td>{r.状态}</td>
                <td>{r.状态 === "已销户" ? "冻结（拒绝正式写）" : "开放"}</td>
                <td>
                  {r.状态 === "正常" ? (
                    <button onClick={() => 销户(r.账户键)}>同票销户落终镜</button>
                  ) : (
                    <>
                      <button className="次" onClick={() => 核证(r.账户键)}>终镜核证</button>
                      {待办数[r.账户键] ? (
                        <button onClick={() => 结清(r.账户键)}>结清善后({待办数[r.账户键]})</button>
                      ) : null}
                      <button className="次" onClick={() => 解销(r.账户键)}>结清后解销</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {核证果 ? (
        <div className="段">
          <h2 className="段题">终镜核证 · {核证果.账户键}</h2>
          <table>
            <tbody>
              <tr><th>valid</th><td>{String(核证果.valid)}</td></tr>
              <tr><th>可写否</th><td>{String(核证果.可写)}</td></tr>
              <tr><th>终态余额</th><td>{核证果.终态余额 ?? "—"}</td></tr>
              <tr><th>销户营业日</th><td>{核证果.销户营业日 ?? "—"}</td></tr>
              <tr><th>凭证编号</th><td>{核证果.凭证编号 ?? "—"}</td></tr>
              <tr><th>善后有无</th><td>{核证果.善后.有 ? `有（待办 ${核证果.善后.待办笔数} / 累计 ${核证果.善后.累计笔数}）` : "无"}</td></tr>
              <tr><th>口径</th><td>{核证果.口径}</td></tr>
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="段">
        <h2 className="段题">终镜凭证（append-only，失效留痕）</h2>
        {!终镜.length ? (
          <div className="空态">尚无终镜</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>凭证编号</th><th>账户键</th><th>销户营业日</th><th>终态余额</th>
                <th>来源快照键</th><th>状态</th><th>时刻</th>
              </tr>
            </thead>
            <tbody>
              {终镜.map((r) => (
                <tr key={r.凭证编号}>
                  <td>{r.凭证编号}</td><td>{r.账户键}</td><td>{r.销户营业日}</td>
                  <td>{r.终态余额}</td><td>{r.来源快照键}</td><td>{r.状态}</td><td>{r.时刻}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">善后旁置轨（不进正式净额、不改终镜）</h2>
        {!善后.length ? (
          <div className="空态">善后为空</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>旁置编号</th><th>账户键</th><th>营业日</th><th>变动额</th>
                <th>原流水号</th><th>状态</th><th>时刻</th>
              </tr>
            </thead>
            <tbody>
              {善后.map((r) => (
                <tr key={r.旁置编号}>
                  <td>{r.旁置编号}</td><td>{r.账户键}</td><td>{r.营业日}</td>
                  <td>{r.变动额}</td><td>{r.原流水号 || "—"}</td><td>{r.状态}</td><td>{r.时刻}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">清算/解销手续</h2>
        {!清算.length ? (
          <div className="空态">尚无手续</div>
        ) : (
          <table>
            <thead>
              <tr><th>手续编号</th><th>账户键</th><th>原凭证编号</th><th>处置</th><th>时刻</th></tr>
            </thead>
            <tbody>
              {清算.map((r) => (
                <tr key={r.手续编号}>
                  <td>{r.手续编号}</td><td>{r.账户键}</td><td>{r.原凭证编号}</td>
                  <td>{r.处置}</td><td>{r.时刻}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="行">
        <button className="次" onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新</button>
      </div>
    </div>
  );
}
