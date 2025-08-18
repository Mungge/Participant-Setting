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
        <td>${vm.floating_ip || ""}</td>
      `;
			tbody.appendChild(tr);
		});
	}
	async function loadVMs() {
		const data = await fetchJSON("/api/vms");
		renderVMs(data.vms || []);
	}
	$("#refresh-vms").addEventListener("click", loadVMs);

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
