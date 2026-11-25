import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function 账户册() {
  const [行, set行] = useState([]);
  const [讯, set讯] = useState("");
  const [证, set证] = useState(null);

  const 刷新 = () => api.账户().then(set行);

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  const 核证 = (键) =>
    api
      .核证(键)
      .then(set证)
      .catch((e) => set讯(String(e.message || e)));

  return (
    <div>
      <h1 className="题">账户册</h1>
      <p className="述">种子账户。金额单位为分。已销户账户正式写路径冻结，终镜核证见「销户终镜」页。</p>
      {讯 ? <p className="讯">{讯}</p> : null}
      {证 ? (
        <div className="提示条">
          核证 {证.账户键}：valid={String(证.valid)} · 可写={String(证.可写)} · 终态余额=
          {证.终态余额 ?? "—"} · 善后={证.善后.有 ? `有(待办${证.善后.待办笔数})` : "无"}
        </div>
      ) : null}
      {!行.length ? (
        <div className="空态">暂无账户</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>账户键</th>
              <th>户名</th>
              <th>币种</th>
              <th>开户营业日</th>
              <th>状态</th>
              <th>写闸</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.账户键}>
                <td>{r.账户键}</td>
                <td>{r.户名}</td>
                <td>{r.币种}</td>
                <td>{r.开户营业日}</td>
                <td>{r.状态}</td>
                <td>{r.状态 === "已销户" ? "冻结" : "开放"}</td>
                <td>
                  {r.状态 === "已销户" ? (
                    <button className="次" onClick={() => 核证(r.账户键)}>终镜核证</button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
