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
	async function loadVMs() {
		const data = await fetchJSON("/api/vms");
		renderVMs(data.vms || []);
	}
	$("#refresh-vms").addEventListener("click", loadVMs);

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

	// FL Submit
	$("#fl-form").addEventListener("submit", async (e) => {
		e.preventDefault();
		const vm_id = $("#vm_id").value.trim();
		const entry_point = $("#entry_point").value.trim() || "main.py";
		const reqRaw = $("#requirements").value.trim();
		const requirements = reqRaw
			? reqRaw
					.split(",")
					.map((s) => s.trim())
					.filter(Boolean)
			: [];

		let env_config = {};
		try {
			env_config = JSON.parse($("#env_config").value || "{}");
		} catch (e) {}

		const fl_code = $("#fl_code").value;
		$("#fl-submit-status").textContent = "제출 중...";

		const res = await fetchJSON("/api/fl/execute", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				vm_id,
				fl_code,
				env_config,
				entry_point,
				requirements,
			}),
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
	loadVMs();
})();
