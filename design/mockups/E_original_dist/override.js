/* E 微调层 override.js — 原版 100% 保留；只做"加"：侧栏两项 + 占位面板。
   真实实现（D6/D7）= fork 旧前端源码后在 src/router+AppShell 中正式加入；
   本文件仅为原版+微调的静态演示。 */

(function () {
  "use strict";

  var ITEMS = [
    { id: "e-nav-ai", label: "AI 参谋", icon: "✦", badge: "新增", panel: panelAI },
    { id: "e-nav-shadow", label: "影子对照", icon: "⇋", badge: "新增", panel: panelShadow },
  ];

  function ensureNav() {
    // Naive UI 菜单容器
    var menu = document.querySelector(".n-menu");
    if (!menu) return false;
    if (document.getElementById("e-nav-ai")) return true;
    var ul = menu.querySelector("ul") || menu;
    ITEMS.forEach(function (it) {
      var li = document.createElement("div");
      li.className = "n-menu-item";
      li.id = it.id;
      li.style.cursor = "pointer";
      li.innerHTML =
        '<div class="n-menu-item-content" style="padding-left:18px">' +
        '<span style="margin-right:8px">' + it.icon + '</span>' +
        '<span style="font-size:13px">' + it.label + '</span>' +
        '<span class="e-new" style="margin-left:auto">' + it.badge + '</span></div>';
      li.addEventListener("click", function () { openPanel(it); });
      ul.appendChild(li);
    });
    return true;
  }

  function openPanel(it) {
    var old = document.getElementById("e-panel");
    if (old) old.remove();
    var div = document.createElement("div");
    div.id = "e-panel";
    div.innerHTML =
      '<span class="close" id="e-close">×</span>' +
      '<h2>' + it.label + ' <span class="tag">D6/D7 规划页 · 静态演示</span></h2>' +
      it.panel();
    document.body.appendChild(div);
    document.getElementById("e-close").addEventListener("click", function () {
      div.remove();
    });
  }

  function panelAI() {
    return (
      '<p>AI 参谋 = 自建 agent 底座（工具调用 + 会话 + persona/记忆/技能）上的对话页。</p>' +
      '<div class="kv">' +
      '<div class="kvd"><b>内置工具 8 个</b>get_positions / get_indicators / get_candles / get_account_info / get_trades_history / get_market_price / get_gate_stats / get_shadow_summary</div>' +
      '<div class="kvd"><b>PA 分析工具</b>get_pa_analysis(tf) → pa_agent sidecar 两阶段分析（AGPL 隔离），决策 JSON 落 ai_analysis 表</div>' +
      '<div class="kvd"><b>交互</b>SSE 流式对话 + 工具调用过程展示 + 追问锚定分析记录</div>' +
      '<div class="kvd"><b>纪律</b>AI 永远不下单——工具纪律代码级注入</div>' +
      '</div><p>左侧栏新增入口；本页为静态占位，正式实现见 UI_APP_PLAN D6。</p>'
    );
  }

  function panelShadow() {
    return (
      '<p>影子对照 = MT5 demo 引擎 vs MT4 实盘的同窗对照（晋升核验证据）。</p>' +
      '<div class="kv">' +
      '<div class="kvd"><b>对照口径</b>方向一致率 ≥90%（±2 bar），每周生成 shadow_weekly 报告</div>' +
      '<div class="kvd"><b>图表</b>MT5 vs MT4 每日盈亏分组柱图（已在 v2 面板预览）</div>' +
      '<div class="kvd"><b>跟踪档</b>docs/promotions/m{30,15}_followave_promotion.md</div>' +
      '<div class="kvd"><b>判据来源</b>T2.6 修订（2026-10-03 确认）</div>' +
      '</div><p>本页为静态占位；v2 面板已有 /shadow 页可先行预览。</p>'
    );
  }

  // 等 Vue 挂载后注入（轮询至菜单出现）
  var timer = setInterval(function () {
    if (ensureNav()) clearInterval(timer);
  }, 400);
})();
