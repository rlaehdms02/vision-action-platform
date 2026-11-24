/*
 * 9단계 분석 화면 동작 (DRF API 호출)
 *
 *  AI 분석 시작 → POST /api/v1/analyses/            (작업 생성, 바로 PENDING 응답)
 *              → 2초마다 GET /api/v1/analyses/{id}/status/   (대기 → 영상 수집 → AI 분석 → 완료/실패)
 *              → 끝나면 GET /api/v1/analyses/{id}/            (사람별 결과 표 그리기)
 *  최근 기록    → GET /api/v1/analyses/                       (내 작업 목록)
 */
(() => {
  const cfg = JSON.parse(document.getElementById("page-config").textContent);
  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const POLL_MS = 2000;

  let inputType = "UPLOAD";
  let pollTimer = null;
  let captureTimer = null;
  let currentJobId = null;
  let lastStep = 0;
  let rotation = 0;                        // IP Webcam 화면 회전 (0/90/180/270, 시계 방향)

  // ---------- 공통 ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(url, options = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, Accept: "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw { status: res.status, data };
    return data;
  }

  function errorText(err) {
    if (!err || !err.data) return "서버와 통신하지 못했습니다. Django 서버가 켜져 있는지 확인하세요.";
    if (err.status === 403) return "로그인이 만료되었습니다. 새로고침 후 다시 로그인하세요.";
    const d = err.data;
    if (typeof d === "string") return d;
    if (d.detail) return d.detail;
    return Object.entries(d).map(([k, v]) => (k === "non_field_errors" ? "" : k + ": ") + [].concat(v).join(" ")).join("\n");
  }

  const fmtTime = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  // ---------- 탭 ----------
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      inputType = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== inputType));
      hideFormError();
      if (inputType === "IP_WEBCAM") loadFacing();
    })
  );

  // ---------- 화면 회전 (미리보기 + 녹화 영상) ----------
  // 미리보기: CSS 로 돌려서 보여줌 / 녹화: Worker 가 같은 각도로 프레임을 돌려서 저장
  function layoutPreview() {
    const img = $("preview"), frame = $("preview-frame");
    if (!img || !frame) return;
    const w = img.naturalWidth || 16, h = img.naturalHeight || 9;
    const side = rotation % 180 !== 0;                       // 90/270 이면 가로·세로가 바뀜
    frame.style.width = side ? "60%" : "100%";
    frame.style.aspectRatio = side ? `${h} / ${w}` : `${w} / ${h}`;
    const fw = frame.clientWidth;
    img.style.width = (side ? (fw * w) / h : fw) + "px";
    img.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;
  }

  function setRotation(deg) {
    rotation = [0, 90, 180, 270].includes(deg) ? deg : 0;
    document.querySelectorAll("#rotate-group button").forEach((b) =>
      b.classList.toggle("active", Number(b.dataset.rot) === rotation));
    try { localStorage.setItem("vision.rotation", String(rotation)); } catch (_) {}
    layoutPreview();
  }

  document.querySelectorAll("#rotate-group button").forEach((b) =>
    b.addEventListener("click", () => setRotation(Number(b.dataset.rot))));
  try { setRotation(Number(localStorage.getItem("vision.rotation") || 0)); } catch (_) { setRotation(0); }
  window.addEventListener("resize", layoutPreview);
  let lastSize = "";
  setInterval(() => {                                        // MJPEG 는 load 이벤트가 늦어서 크기를 주기적으로 확인
    const img = $("preview");
    const size = img ? `${img.naturalWidth}x${img.naturalHeight}` : "";
    if (size !== lastSize) { lastSize = size; layoutPreview(); }
  }, 500);

  // ---------- 전면 / 후면 카메라 전환 (Django 가 IP Webcam 앱에 대신 요청) ----------
  const FACING_URL = "/analyses/camera/facing/";
  function showFacing(facing) {
    document.querySelectorAll("#facing-group button").forEach((b) =>
      b.classList.toggle("active", b.dataset.facing === facing));
  }
  async function loadFacing() {
    if (!$("camera_url") || !$("facing-group")) return;
    try {
      const d = await api(`${FACING_URL}?camera_url=${encodeURIComponent($("camera_url").value)}`);
      showFacing(d.facing);
      $("facing-hint").textContent = "후면 카메라가 화질이 더 좋습니다. 전환하면 미리보기가 잠깐 끊겼다 다시 나옵니다.";
    } catch (err) {
      showFacing("");
      $("facing-hint").textContent = (err.data && err.data.error) || "카메라 상태를 확인하지 못했습니다.";
    }
  }
  function reloadPreview() {
    if ($("preview-box") && !$("preview-box").classList.contains("hidden")) {
      const url = $("camera_url").value;
      $("preview").src = "";
      setTimeout(() => { $("preview").src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(); }, 1500);
    }
  }
  document.querySelectorAll("#facing-group button").forEach((b) =>
    b.addEventListener("click", async () => {
      if ($("start-btn").disabled) { setStatus("분석 중에는 카메라를 바꿀 수 없습니다.", "warn"); return; }
      const fd = new FormData();
      fd.append("camera_url", $("camera_url").value);
      fd.append("facing", b.dataset.facing);
      $("facing-hint").textContent = "카메라 전환 중…";
      try {
        const d = await api(FACING_URL, { method: "POST", body: fd });
        showFacing(d.facing);
        $("facing-hint").textContent = d.facing === "front"
          ? "전면 카메라로 바꿨습니다. 좌우가 반전되어 보일 수 있습니다."
          : "후면 카메라로 바꿨습니다.";
        reloadPreview();
      } catch (err) {
        $("facing-hint").textContent = (err.data && err.data.error) || "카메라를 전환하지 못했습니다.";
      }
    })
  );

  // ---------- 카메라 미리보기 (브라우저가 휴대폰에 직접 접속) ----------
  const previewBtn = $("preview-toggle");
  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      const box = $("preview-box");
      const on = box.classList.contains("hidden");
      box.classList.toggle("hidden", !on);
      $("preview").src = on ? $("camera_url").value : "";
      previewBtn.textContent = on ? "카메라 미리보기 끄기" : "카메라 미리보기 켜기";
      requestAnimationFrame(layoutPreview);
    });
    $("camera_url")?.addEventListener("change", () => {
      loadFacing();
      if (!$("preview-box").classList.contains("hidden")) $("preview").src = $("camera_url").value;
    });
    $("preview").addEventListener("error", () => {
      if ($("preview").getAttribute("src")) setStatus("미리보기를 불러오지 못했습니다. 휴대폰 IP Webcam 앱에서 Start server 를 눌렀는지 확인하세요.", "warn");
    });
  }

  // ---------- 진행 단계 표시 ----------
  function stepOf(job) {
    if (job.status === "PENDING") return 0;
    if (job.status === "PROCESSING") return job.stage === "CAPTURING" ? 1 : job.stage === "ANALYZING" ? 2 : 1;
    if (job.status === "COMPLETED") return 4;     // 4 = 전부 완료
    // FAILED: 마지막으로 본 단계에서 실패. 너무 빨리 실패해서 못 봤으면
    //         영상이 없으면(카메라 수집 실패) ②영상 수집, 영상이 있으면 ③AI 분석에서 실패로 표시
    if (lastStep > 0) return lastStep;
    return job.input_type === "IP_WEBCAM" && !job.video ? 1 : 2;
  }

  function drawSteps(job) {
    const step = stepOf(job);
    const failed = job.status === "FAILED";
    document.querySelectorAll("#steps li").forEach((li) => {
      const i = Number(li.dataset.step);
      li.className = "";
      if (failed && i === step) li.classList.add("failed");
      else if (i < step || step === 4) li.classList.add("done");
      else if (i === step) li.classList.add("active");
    });
    if (!failed) lastStep = Math.min(step, 3);
  }

  function resetSteps() {
    lastStep = 0;
    document.querySelectorAll("#steps li").forEach((li) => (li.className = ""));
  }

  function setStatus(text, kind = "") {
    const el = $("status-text");
    el.textContent = text;
    el.className = "status-text " + (kind || "sub");
  }

  function statusMessage(job) {
    const isCam = job.input_type === "IP_WEBCAM";
    switch (stepOf(job)) {
      case 0: return "작업 대기 중입니다. (Celery Worker 가 꺼져 있으면 계속 대기합니다)";
      case 1: return isCam ? "카메라에서 영상을 수집하는 중입니다. 카메라 앞에서 동작하세요!" : "영상을 준비하는 중입니다.";
      case 2: return "AI 가 사람을 찾고 동작을 분석하는 중입니다. (영상 길이에 따라 수십 초~몇 분)";
      default: return "";
    }
  }

  // IP Webcam 수집 중 남은 시간 카운트다운
  function startCaptureCountdown() {
    if (captureTimer) return;
    let left = cfg.captureSeconds;
    setStatus(`카메라 수집 중… ${left}초 남음 — 카메라 앞에서 동작하세요!`, "live");
    captureTimer = setInterval(() => {
      left -= 1;
      if (left > 0) setStatus(`카메라 수집 중… ${left}초 남음 — 카메라 앞에서 동작하세요!`, "live");
      else stopCaptureCountdown();
    }, 1000);
  }
  function stopCaptureCountdown() {
    clearInterval(captureTimer);
    captureTimer = null;
  }

  // ---------- 결과 표 ----------
  function drawResult(job) {
    const body = $("result-body");
    const preds = job.predictions || [];
    if (job.status === "FAILED") {
      body.innerHTML = `<tr><td colspan="3" class="center error-text">분석 실패: ${esc(job.error_message)}</td></tr>`;
    } else if (job.status !== "COMPLETED") {
      body.innerHTML = `<tr><td colspan="3" class="sub center">분석이 끝나면 결과가 표시됩니다.</td></tr>`;
    } else if (!preds.length) {
      body.innerHTML = `<tr><td colspan="3" class="sub center">${esc(job.result_message || "영상에서 사람을 찾지 못했습니다.")}</td></tr>`;
    } else {
      body.innerHTML = preds.map((p) => {
        const pct = Math.round(p.confidence * 100);
        const match = job.expected_action
          ? (p.action_id === job.expected_action
              ? '<span class="badge ok">예상과 일치</span>'
              : '<span class="badge no">예상과 다름</span>')
          : "";
        const unsure = p.uncertain ? '<span class="badge warn">불확실</span>' : "";
        const label = cfg.actions[p.action_id] || `${p.action_id} ${p.action_label}`;
        return `<tr>
          <td><strong>Track ${esc(p.track_id)}</strong></td>
          <td>${esc(label)} ${match} ${unsure}</td>
          <td><div class="conf"><div class="bar"><span style="width:${pct}%"></span></div>${pct}%</div></td>
        </tr>`;
      }).join("");
    }

    const meta = [];
    if (job.expected_action_display) meta.push(`예상 동작: ${job.expected_action_display}`);
    if (job.status === "COMPLETED" && job.result_message) meta.push(job.result_message);
    if (job.processing_sec != null) meta.push(`처리 시간 ${job.processing_sec.toFixed(1)}초`);
    const parts = meta.map(esc);
    if (job.video) parts.push(`<a href="${esc(job.video)}" target="_blank">영상 보기</a>`);
    $("result-meta").innerHTML = parts.join(" · ");
  }

  function showJob(job) {
    currentJobId = job.id;
    $("job-label").textContent = `작업 #${job.id} · ${job.input_type_display}${job.title ? " · " + job.title : ""}`;
    drawSteps(job);
    drawResult(job);
    if (job.status === "COMPLETED") {
      setStatus(`분석 완료 — ${(job.predictions || []).length}명의 결과`, "ok");
    } else if (job.status === "FAILED") {
      setStatus(`분석 실패 — ${job.error_message}`, "error-text");
    } else if (!(job.stage === "CAPTURING" && captureTimer)) {
      setStatus(statusMessage(job));
    }
  }

  // ---------- 상태 확인 (polling) ----------
  function stopPolling() {
    clearTimeout(pollTimer);
    pollTimer = null;
    stopCaptureCountdown();
  }

  async function poll(jobId) {
    try {
      const s = await api(`${cfg.apiUrl}${jobId}/status/`);
      if (jobId !== currentJobId) return;                // 다른 작업을 보는 중이면 중단
      if (s.is_finished) {
        stopPolling();
        const job = await api(`${cfg.apiUrl}${jobId}/`);
        showJob(job);
        setBusy(false);
        loadHistory();
        return;
      }
      drawSteps(s);
      if (s.stage === "CAPTURING") startCaptureCountdown();
      else { stopCaptureCountdown(); setStatus(statusMessage({ ...s, input_type: inputTypeOf(jobId) })); }
    } catch (err) {
      setStatus("상태 확인 실패: " + errorText(err) + " (다시 시도 중…)", "warn");
    }
    pollTimer = setTimeout(() => poll(jobId), POLL_MS);
  }

  const jobTypes = {};
  const inputTypeOf = (id) => jobTypes[id] || inputType;

  function watchJob(job) {
    stopPolling();
    resetSteps();
    jobTypes[job.id] = job.input_type;
    showJob(job);
    if (job.status === "PENDING" || job.status === "PROCESSING") {
      setBusy(true);
      pollTimer = setTimeout(() => poll(job.id), 500);
    }
  }

  // ---------- 분석 시작 ----------
  function setBusy(busy) {
    const b = $("start-btn");
    b.disabled = busy;
    b.textContent = busy ? "분석 진행 중…" : "AI 분석 시작";
  }
  function showFormError(msg) { const e = $("form-error"); e.textContent = msg; e.classList.remove("hidden"); }
  function hideFormError() { $("form-error").classList.add("hidden"); }

  function validate() {
    if (inputType === "UPLOAD") {
      const f = $("video").files[0];
      if (!f) return "분석할 영상 파일을 선택하세요.";
      const ext = "." + f.name.split(".").pop().toLowerCase();
      if (!cfg.allowedExt.includes(ext)) return `지원하지 않는 형식입니다 (${ext}). 허용: ${cfg.allowedExt.join(", ")}`;
      if (f.size > cfg.maxUploadMb * 1024 * 1024) return `파일이 너무 큽니다. 최대 ${cfg.maxUploadMb}MB`;
    } else if (!$("camera_url") || !$("camera_url").value) {
      return "카메라 주소가 없습니다.";
    }
    return "";
  }

  // 업로드 진행률을 보여주기 위해 XMLHttpRequest 사용
  function postJob(formData) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", cfg.apiUrl);
      xhr.setRequestHeader("X-CSRFToken", csrf);
      xhr.setRequestHeader("Accept", "application/json");
      const prog = $("upload-progress");
      if (inputType === "UPLOAD") {
        prog.classList.remove("hidden");
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) prog.textContent = `업로드 중… ${Math.round((e.loaded / e.total) * 100)}%`;
        };
      }
      xhr.onload = () => {
        prog.classList.add("hidden");
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (_) { data = { detail: xhr.responseText.slice(0, 200) }; }
        xhr.status >= 200 && xhr.status < 300 ? resolve(data) : reject({ status: xhr.status, data });
      };
      xhr.onerror = () => { prog.classList.add("hidden"); reject({}); };
      xhr.send(formData);
    });
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  $("analysis-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    hideFormError();
    const problem = validate();
    if (problem) return showFormError(problem);

    const fd = new FormData();
    fd.append("input_type", inputType);
    fd.append("title", $("title").value.trim());
    fd.append("expected_action", $("expected_action").value);
    if (inputType === "UPLOAD") fd.append("video", $("video").files[0]);
    else { fd.append("camera_url", $("camera_url").value); fd.append("rotation", String(rotation)); }

    setBusy(true);
    stopPolling();
    resetSteps();
    currentJobId = null;
    $("result-body").innerHTML = `<tr><td colspan="3" class="sub center">분석이 끝나면 결과가 표시됩니다.</td></tr>`;
    $("result-meta").textContent = "";
    $("job-label").textContent = "";

    // IP Webcam: 자리 잡을 시간 (시작 전 대기)
    if (inputType === "IP_WEBCAM") {
      for (let n = Number($("countdown").value); n > 0; n--) {
        setStatus(`${n}초 후 촬영 시작 — 카메라 앞 자리로 이동하세요`, "live");
        await sleep(1000);
      }
    }

    try {
      const job = await postJob(fd);
      $("title").value = "";
      if (inputType === "UPLOAD") $("video").value = "";
      watchJob(job);
      loadHistory();
    } catch (err) {
      setBusy(false);
      setStatus("작업을 만들지 못했습니다.", "error-text");
      showFormError(errorText(err));
    }
  });

  // ---------- 최근 기록 ----------
  const STATUS_CLASS = { PENDING: "pending", PROCESSING: "processing", COMPLETED: "completed", FAILED: "failed" };

  async function loadHistory() {
    const body = $("history-body");
    try {
      const data = await api(cfg.apiUrl);
      const jobs = data.results || data;
      if (!jobs.length) {
        body.innerHTML = `<tr><td colspan="9" class="sub center">아직 분석 기록이 없습니다.</td></tr>`;
        return jobs;
      }
      body.innerHTML = jobs.slice(0, 10).map((j) => {
        const top = (j.predictions || []).slice().sort((a, b) => b.confidence - a.confidence)[0];
        const stage = j.status === "PROCESSING" && j.stage ? ` (${j.stage === "CAPTURING" ? "영상 수집" : "AI 분석"})` : "";
        // 예상 동작과 비교: 사람 전원 일치 / 일부 일치 / 다름
        const preds = j.predictions || [];
        let expect = j.expected_action ? esc(j.expected_action) : "-";
        if (j.expected_action && j.status === "COMPLETED" && preds.length) {
          const hit = preds.filter((p) => p.action_id === j.expected_action).length;
          expect += hit === preds.length ? ' <span class="badge ok">일치</span>'
                  : hit === 0 ? ' <span class="badge no">다름</span>'
                  : ` <span class="badge warn">${hit}/${preds.length} 일치</span>`;
        }
        const conf = top ? Math.round(top.confidence * 100) : null;
        return `<tr class="clickable${j.id === currentJobId ? " selected" : ""}" data-id="${j.id}">
          <td>#${j.id}</td>
          <td>${esc(j.title || "-")}</td>
          <td>${esc(j.input_type_display)}</td>
          <td><span class="pill ${STATUS_CLASS[j.status]}">${esc(j.status_display)}${stage}</span></td>
          <td>${j.status === "COMPLETED" ? (j.predictions || []).length + "명" : "-"}</td>
          <td>${top ? esc(top.action_id + " " + top.action_label) + (top.uncertain ? ' <span class="badge warn">불확실</span>' : "") : "-"}</td>
          <td>${conf == null ? "-" : `<div class="conf small"><div class="bar"><span style="width:${conf}%"></span></div>${conf}%</div>`}</td>
          <td class="nowrap">${expect}</td>
          <td>${fmtTime(j.created_at)}</td>
        </tr>`;
      }).join("");
      body.querySelectorAll("tr.clickable").forEach((tr) =>
        tr.addEventListener("click", async () => {
          const job = await api(`${cfg.apiUrl}${tr.dataset.id}/`);
          watchJob(job);
          body.querySelectorAll("tr").forEach((r) => r.classList.toggle("selected", r === tr));
        })
      );
      return jobs;
    } catch (err) {
      body.innerHTML = `<tr><td colspan="9" class="center error-text">${esc(errorText(err))}</td></tr>`;
      return [];
    }
  }

  $("history-refresh").addEventListener("click", loadHistory);

  // 처음 열 때: 진행 중인 작업이 있으면 이어서 상태 확인
  loadHistory().then((jobs) => {
    const RECENT_MS = 10 * 60 * 1000;   // 10분 넘은 미완료 작업은 자동으로 이어받지 않음
    const running = jobs.find((j) => (j.status === "PENDING" || j.status === "PROCESSING")
      && Date.now() - new Date(j.created_at).getTime() < RECENT_MS);
    if (running) watchJob(running);
  });
})();
