(() => {
	const $ = (sel, el = document) => el.querySelector(sel);
	const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

	const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.baseUrl) || "";

	async function fetchJSON(path, opts = {}) {
		const res = await fetch(baseUrl + path, opts);
		const text = await res.text();
		try {
			return JSON.parse(text);
		} catch {
			return { raw: text, status: res.status };
		}
	}

	function showEnvPreview(cfg) {
		const pre = $("#env-preview");
		if (!pre) return;
		pre.hidden = false;
		pre.textContent = JSON.stringify({ run_config: cfg }, null, 2);
	}

	// Overview
	async function loadOverview() {
		const data = await fetchJSON("/health");
		$("#status").textContent = data.status || "-";
		$("#timestamp").textContent = data.timestamp || new Date().toISOString();
	}
	$("#refresh-overview").addEventListener("click", loadOverview);

	// VMs
	function renderVMs(vms = []) {
		const tbody = $("#vms-table tbody");
		tbody.innerHTML = "";
		if (!vms.length) {
			$("#vms-empty").hidden = false;
			return;
		}
		$("#vms-empty").hidden = true;
		vms.forEach((vm) => {
			const tr = document.createElement("tr");
			tr.innerHTML = `
					<td><code>${vm.id || ""}</code></td>
					<td>${vm.name || ""}</td>
					<td>
						<div style="display:flex;align-items:center;gap:8px;">
							<span>${vm.floating_ip || ""}</span>
							${
								vm.floating_ip
									? `<button class="btn btn-ssh" data-vm="${vm.id}">SSH 체크</button>`
									: ""
							}
						</div>
					</td>
      `;
			tbody.appendChild(tr);
		});

		// Bind SSH check buttons
		$$(".btn-ssh").forEach((btn) => {
			btn.addEventListener("click", async (e) => {
				const vmId = e.currentTarget.getAttribute("data-vm");
				e.currentTarget.textContent = "체크 중...";
				e.currentTarget.disabled = true;
				try {
					const res = await fetchJSON(
						`/api/vms/${encodeURIComponent(vmId)}/ssh-check`
					);
					alert(
						res.success
							? `성공: ${res.remote_info || ""} (${res.latency_ms}ms)`
							: `실패: ${res.error || res.message}`
					);
				} finally {
					e.currentTarget.textContent = "SSH 체크";
					e.currentTarget.disabled = false;
				}
			});
		});
	}
	$("#refresh-vms").addEventListener("click", async () => {
		const data = await fetchJSON("/api/vms");
		renderVMs(data.vms || []);
	});

	// Direct IP SSH check
	const ipBtn = document.querySelector("#ssh-check-ip-btn");
	if (ipBtn) {
		ipBtn.addEventListener("click", async () => {
			const ipInput = document.querySelector("#ssh-check-ip");
			const ip = ((ipInput && ipInput.value) || "").trim();
			if (!ip) return alert("IP를 입력하세요");
			ipBtn.textContent = "체크 중...";
			ipBtn.disabled = true;
			try {
				const res = await fetchJSON(
					`/api/ssh-check?ip=${encodeURIComponent(ip)}`
				);
				alert(
					res.success
						? `성공: ${res.remote_info || ""} (${res.latency_ms}ms)`
						: `실패: ${res.error || res.message}`
				);
			} finally {
				ipBtn.textContent = "IP로 SSH 체크";
				ipBtn.disabled = false;
			}
		});
	}

	// Unified FL Submit (Flower client_app.py deploy)
	$("#fl-form").addEventListener("submit", async (e) => {
		e.preventDefault();
		const vm_id = $("#vm_id").value.trim();
		if (!vm_id) return;
		$("#fl-submit-status").textContent = "제출 중...";

		// Use env_config as Flower run_config and deploy client_app.py
		let run_cfg = {};
		try {
			run_cfg = JSON.parse($("#env_config").value || "{}");
		} catch (e) {}
		if (run_cfg.CLIENT_ID === undefined) run_cfg.CLIENT_ID = vm_id;
		showEnvPreview(run_cfg);
		const res = await fetchJSON("/api/fl/deploy-flower-app", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ vm_id, env_config: run_cfg }),
		});
		$("#fl-submit-status").textContent = res.success ? "성공" : "실패";
		const out = $("#fl-result");
		out.hidden = false;
		out.textContent = JSON.stringify(res, null, 2);
		if (res.task_id) {
			$("#log_task_id").value = res.task_id;
			$("#log_vm_id").value = vm_id;
		}
	});

	// Logs
	$("#btn-get-logs").addEventListener("click", async (e) => {
		e.preventDefault();
		const taskId = $("#log_task_id").value.trim();
		const vmId = $("#log_vm_id").value.trim();
		if (!taskId || !vmId) return;
		const res = await fetchJSON(
			`/api/fl/logs/${encodeURIComponent(taskId)}?vm_id=${encodeURIComponent(
				vmId
			)}`
		);
		const out = $("#logs-output");
		out.hidden = false;
		out.textContent =
			res.log_content || res.error || JSON.stringify(res, null, 2);
	});

	// Initial load
	loadOverview();
	$("#refresh-vms").click();
})();
