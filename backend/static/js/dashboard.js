/*
 * 10단계 관리자 대시보드: Chart.js 막대(동작별 예측 수) + 도넛(상태별 작업 수) + 최근 작업 표
 * 처음엔 서버가 넣어준 값으로 그리고, 10초마다 /dashboard/data/ 를 다시 불러와 갱신합니다.
 */
(() => {
  const DATA_URL = "/dashboard/data/";
  const REFRESH_MS = 10000;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // 색: 막대는 한 가지 색(크기 비교), 도넛은 상태색(라벨+건수와 함께 표시)
  const BAR_COLOR = "#2a78d6";
  const STATUS_COLOR = { PENDING: "#9aa0b4", PROCESSING: "#2a78d6", COMPLETED: "#0ca30c", FAILED: "#d03b3b" };
  const STATUS_CLASS = { PENDING: "pending", PROCESSING: "processing", COMPLETED: "completed", FAILED: "failed" };
  const INK = "#4a5068", GRID = "#eceef5";

  if (typeof Chart === "undefined") {
    document.querySelectorAll(".chart-box").forEach((b) => (b.innerHTML = '<p class="error-text">차트 라이브러리를 불러오지 못했습니다 (static/vendor/chart.umd.min.js 확인)</p>'));
    return;
  }
  Chart.defaults.font.family = '"Segoe UI", "Malgun Gothic", sans-serif';
  Chart.defaults.color = INK;

  // 막대 라벨: "A001 앉아서 다리 앞으로 뻗기" → ["A001", "앉아서 다리 앞으로 뻗기"] 두 줄
  const twoLines = (label) => { const i = label.indexOf(" "); return i > 0 ? [label.slice(0, i), label.slice(i + 1)] : label; };

  const actionChart = new Chart($("action-chart"), {
    type: "bar",
    data: { labels: [], datasets: [{ label: "예측 수", data: [], backgroundColor: BAR_COLOR,
      borderRadius: 4, borderSkipped: "start", maxBarThickness: 64 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: (items) => [].concat(items[0].label).join(" "), label: (c) => ` ${c.parsed.y}건` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 12 } } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: GRID }, border: { display: false },
             title: { display: true, text: "예측 수 (건)" } },
      },
    },
  });

  const statusChart = new Chart($("status-chart"), {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderColor: "#fff", borderWidth: 2, hoverOffset: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%", animation: { duration: 300 },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "rectRounded", padding: 16 } },
        tooltip: { callbacks: { label: (c) => {
          const total = c.dataset.data.reduce((a, b) => a + b, 0) || 1;
          return ` ${c.raw}건 (${Math.round((c.raw / total) * 100)}%)`;
        } } },
      },
    },
  });

  function render(stats) {
    const s = stats.summary;
    $("t-total").textContent = s.total_jobs;
    $("t-completed").textContent = s.completed;
    $("t-failed").textContent = s.failed;
    $("t-running").textContent = s.running;
    $("t-people").textContent = s.people;
    $("t-avg").textContent = s.avg_sec ? `${s.avg_sec}초` : "-";
    $("t-match").textContent = s.match_rate == null ? "-" : `${s.match_rate}%`;
    $("t-match-sub").textContent = s.match_total ? `예상 동작을 고른 ${s.match_total}건 기준` : "예상 동작을 고른 작업 없음";
    $("updated-at").textContent = stats.updated_at;
    $("donut-total").textContent = s.total_jobs;

    actionChart.data.labels = stats.actions.map((a) => twoLines(a.label));
    actionChart.data.datasets[0].data = stats.actions.map((a) => a.count);
    actionChart.update();

    // 도넛 범례에 건수까지 써서 색만으로 구분하지 않게
    statusChart.data.labels = stats.statuses.map((x) => `${x.label} ${x.count}건`);
    statusChart.data.datasets[0].data = stats.statuses.map((x) => x.count);
    statusChart.data.datasets[0].backgroundColor = stats.statuses.map((x) => STATUS_COLOR[x.key] || "#9aa0b4");
    statusChart.update();

    const rows = stats.recent;
    $("recent-body").innerHTML = rows.length ? rows.map((j) => {
      const match = j.match === true ? '<span class="badge ok">일치</span>' : j.match === false ? '<span class="badge no">다름</span>' : "";
      const stage = j.stage_display ? ` (${esc(j.stage_display)})` : "";
      return `<tr${j.error ? ` title="${esc(j.error)}"` : ""}>
        <td><a href="${esc(j.admin_url)}">#${j.id}</a></td>
        <td>${esc(j.user)}</td>
        <td>${esc(j.title || "-")}</td>
        <td>${esc(j.input)}</td>
        <td><span class="pill ${STATUS_CLASS[j.status]}">${esc(j.status_display)}${stage}</span></td>
        <td>${j.status === "COMPLETED" ? j.people + "명" : "-"}</td>
        <td>${j.top ? esc(j.top) + ` (${j.top_conf}%)` : "-"}</td>
        <td>${esc(j.expected || "-")} ${match}</td>
        <td>${j.processing_sec != null ? j.processing_sec.toFixed(1) + "초" : "-"}</td>
        <td>${esc(j.created_at)}</td>
      </tr>`;
    }).join("") : '<tr><td colspan="10" class="sub center">아직 분석 작업이 없습니다.</td></tr>';
  }

  async function refresh() {
    try {
      const res = await fetch(DATA_URL, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!res.ok || !(res.headers.get("content-type") || "").includes("json")) throw new Error(res.status);
      render(await res.json());
    } catch (e) {
      $("updated-at").textContent = "갱신 실패 (로그인 만료 또는 서버 꺼짐)";
    }
  }

  render(JSON.parse($("dash-initial").textContent));
  $("dash-refresh").addEventListener("click", refresh);
  setInterval(refresh, REFRESH_MS);
})();
