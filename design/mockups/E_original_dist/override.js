/* E 微调层 override.js v2（按用户裁定修订）：
   ① 撤销 v1 的两个新增导航项——影子对照并入「日报周报」页、AI 参谋 =
      升级现有 AI agent（不新增页面；FortuneCat/AiChatPanel 入口保留）
   ② 演示：在「日报周报」页注入「影子对照」周报卡片（正式实现 = ReportView
      加 Tab，数据源 tools/weekly_shadow_report.py 产物）
   ③ 零字体/底色/布局变更 */

(function () {
  "use strict";

  var SHADOW_HTML =
    '<div id="e-shadow-card" style="background:#fff;border:1px solid #e3e6eb;' +
    'border-radius:10px;padding:16px 20px;box-shadow:0 2px 10px rgba(0,0,0,.08);margin:14px 0">' +
    '<h3 style="margin:0 0 4px;font-size:15px">影子对照（MT5 demo vs MT4 实盘）' +
    '<span style="color:#f0b90b;font-size:11px;margin-left:8px">新增 Tab 演示</span></h3>' +
    '<p style="font-size:12px;color:#8b8f97;margin:4px 0 10px">周度对照：方向一致率 ≥90%' +
    '（±2 bar）｜ 数据源 tools/weekly_shadow_report.py ｜ 判据 T2.6 修订（2026-10-03 确认）</p>' +
    '<table style="border-collapse:collapse;font-size:13px">' +
    '<tr style="color:#8b8f97"><th align="left">策略</th><th>MT5 笔数</th><th>MT4 笔数</th>' +
    '<th>一致率</th><th>MT5 盈亏</th><th>MT4 盈亏</th></tr>' +
    '<tr><td>m30_followave</td><td align="center">12</td><td align="center">15</td>' +
    '<td align="center">93%</td><td align="center" style="color:#0ecb81">+86.4</td>' +
    '<td align="center" style="color:#f6465d">-31.2</td></tr>' +
    '<tr><td>m15_followave</td><td align="center">31</td><td align="center">27</td>' +
    '<td align="center">91%</td><td align="center" style="color:#0ecb81">+124.7</td>' +
    '<td align="center" style="color:#f6465d">-104.1</td></tr></table>' +
    '<p style="font-size:11px;color:#8b8f97;margin:8px 0 0">（示例数据 · 正式版每周自动' +
    '生成 shadow_weekly 报告并在此渲染）</p></div>';

  function inject() {
    if (!/\/report/i.test(location.pathname + location.hash)) return;
    if (document.getElementById("e-shadow-card")) return;
    var host = document.querySelector(".n-layout-scroll-container") || document.body;
    if (!host) return;
    host.insertAdjacentHTML("beforeend", SHADOW_HTML);
    // 固定定位：浮于内容区顶部（避开 200px 侧栏），与页面滚动联动性简化
    var card = document.getElementById("e-shadow-card");
    card.style.position = "fixed";
    card.style.top = "58px";
    card.style.left = "218px";
    card.style.right = "18px";
    card.style.zIndex = "500";
  }

  // 路由变化（history 模式）+ 挂载轮询；60s 后停止（演示用途）
  window.addEventListener("popstate", inject);
  var timer = setInterval(inject, 1200);
  setTimeout(function () { clearInterval(timer); }, 60000);
})();
