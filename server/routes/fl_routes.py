from flask import Blueprint, jsonify, request
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

fl_bp = Blueprint('fl', __name__)

@fl_bp.route('/api/fl/execute', methods=['POST'])
def execute_federated_learning():
    """VM ID와 run_config를 받아 client_app.py를 실행(flwr run .)"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.get_json()
        required_fields = ['vm_id', 'env_config']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing required fields: {missing}', 'required_fields': required_fields}), 400

        vm_id = data['vm_id']
        run_config = data.get('env_config', {}) or {}

        # 템플릿 로드
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fl_client_templates')
        pyproject_path = os.path.join(base, 'pyproject.toml')
        client_app_path = os.path.join(base, 'client_app.py')
        for p in (pyproject_path, client_app_path):
            if not os.path.exists(p):
                return jsonify({'success': False, 'error': f'Template file missing: {p}'}), 500

        def read(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()

        # pyproject.toml 패치: clientapp 경로와 run_config, remote federation 주소
        def to_toml_literal(val):
            if isinstance(val, bool):
                return 'true' if val else 'false'
            if isinstance(val, (int, float)):
                return str(val)
            s = str(val).replace('"', '\"')
            return f'"{s}"'

        import re as _re
        def patch_components_client_only(text: str, client_path: str) -> str:
            block = "[tool.flwr.app.components]\n" + f"clientapp = \"{client_path}\"\n\n"
            pat = _re.compile(r"(?ms)^\[tool\\.flwr\\.app\\.components\]\s*.*?(?=^\[|\Z)")
            return pat.sub(block.rstrip('\n'), text) if pat.search(text) else text + ("\n" if not text.endswith('\n') else "") + "\n" + block

        def patch_pyproject_config(text: str, cfg: dict) -> str:
            if not cfg:
                return text
            lines = ["[tool.flwr.app.config]"] + [f"{k} = {to_toml_literal(v)}" for k, v in cfg.items()]
            block = "\n".join(lines) + "\n\n"
            pat = _re.compile(r"(?ms)^\[tool\\.flwr\\.app\\.config\]\s*.*?(?=^\[|\Z)")
            return pat.sub(block.rstrip('\n'), text) if pat.search(text) else text + ("\n" if not text.endswith('\n') else "") + "\n" + block

        def patch_federations_default_to_remote(text: str) -> str:
            pat = _re.compile(r"(?m)^(\[tool\\.flwr\\.federations\][\s\S]*?)(^\[|\Z)")
            m = pat.search(text)
            if not m:
                return text + ("\n" if not text.endswith("\n") else "") + "\n[tool.flwr.federations]\ndefault = \"remote-federation\"\n\n"
            sec = m.group(1)
            sec = _re.sub(r"(?m)^default\s*=\s*\".*?\"", 'default = "remote-federation"', sec)
            a, b = m.span(1)
            return text[:a] + sec + text[b:]

        def set_remote_address(text: str, address: str) -> str:
            pat = _re.compile(r"(?ms)^\[tool\\.flwr\\.federations\\.remote-federation\]\s*.*?(?=^\[|\Z)")
            line = f"address = \"{address}\"\n"
            if pat.search(text):
                def repl(m):
                    blk = m.group(0)
                    blk = _re.sub(r"(?m)^address\s*=\s*\".*?\"", line.rstrip('\n'), blk) if _re.search(r"(?m)^address\s*=\s*\".*?\"", blk) else blk + ("\n" if not blk.endswith('\n') else "") + line
                    return blk
                return pat.sub(repl, text)
            return text + ("\n" if not text.endswith('\n') else "") + "\n[tool.flwr.federations.remote-federation]\n" + line + "insecure = true\n\n"

        pyproj = read(pyproject_path)
        pyproj = patch_components_client_only(pyproj, 'client_app:app')
        pyproj = patch_federations_default_to_remote(pyproj)
        remote_addr = run_config.get('remote-address') or run_config.get('superlink-address')
        if isinstance(remote_addr, str) and remote_addr.strip():
            pyproj = set_remote_address(pyproj, remote_addr.strip())
        cfg_only = {k: v for k, v in run_config.items() if k not in {'remote-address', 'superlink-address'}}
        pyproj = patch_pyproject_config(pyproj, cfg_only)

        additional_files = {
            'pyproject.toml': pyproj,
            'client_app.py': read(client_app_path),
        }

        custom_cmd = (
            'export PATH=$HOME/.local/bin:$PATH && '
            'python3 -m pip install --upgrade pip && '
            'python3 -m pip install '
            'flwr[simulation]>=1.20.0 '
            'flwr-datasets[vision]>=0.5.0 '
            'torch==2.7.1 '
            'torchvision==0.22.1 && '
            'which flwr && '
            'flwr run .'
        )

        # VM 정보 조회하고 SSH로 직접 배포
        from utils.openstack import get_openstack_vmList
        from services.ssh_service import SSHService
        
        vm_list = get_openstack_vmList()
        target_vm = next((vm for vm in vm_list if vm.get('id') == vm_id), None)
        if not target_vm:
            return jsonify({'success': False, 'error': f'VM with ID {vm_id} not found', 'vm_id': vm_id}), 404
        
        floating_ip = target_vm.get('floating_ip')
        if not floating_ip:
            return jsonify({'success': False, 'error': f'VM {vm_id} has no floating IP assigned', 'vm_id': vm_id, 'vm_info': target_vm}), 400
        
        task_id = f"fl-task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        ssh_service = SSHService()
        result = ssh_service.deploy_and_execute_fl_code(
            floating_ip=floating_ip,
            task_id=task_id,
            env_config={},
            entry_point=None,
            additional_files=additional_files,
            custom_command=custom_cmd,
        )
        
        # 응답 형식 맞추기
        response = {
            'task_id': task_id,
            'vm_id': vm_id,
            'target_ip': floating_ip,
            'submitted_at': datetime.now().isoformat(),
            'entry_point': 'flwr run .',
            'success': result['success'],
            'message': result.get('message', ''),
        }
        
        if result['success']:
            response['ssh_output'] = result.get('output', '')
            response['remote_path'] = result.get('remote_path', '')
        else:
            response['error'] = result.get('error', '')

        return jsonify(response), (201 if response.get('success') else 500)

    except Exception as e:
        logger.error(f"Error executing federated learning: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to execute federated learning'}), 500


@fl_bp.route('/api/fl/logs/<string:task_id>', methods=['GET'])
def get_fl_logs(task_id):
    """연합학습 작업 로그 조회"""
    try:
        vm_id = request.args.get('vm_id')
        if not vm_id:
            return jsonify({'error': 'vm_id parameter is required'}), 400
        
        from services.fl_service import FederatedLearningService
        fl_service = FederatedLearningService()
        result = fl_service.get_task_logs(task_id, vm_id)
        
        status_code = 200 if result['success'] else 404
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Error getting FL logs for {task_id}: {str(e)}")
        return jsonify({'error': 'Failed to retrieve logs'}), 500

@fl_bp.route('/api/fl/status/<string:vm_id>', methods=['GET'])
def get_task_status(vm_id):
    """현재 실행 중인 작업 상태"""
    # TODO: 실제 작업 상태 조회 로직 구현
    return jsonify({
        'active_tasks': [
            {
                'task_id': 'fl-training-001',
                'type': 'federated_learning',
                'status': 'running',
                'progress': 75.5,
                'started_at': '2025-08-11T10:30:00Z'
            }
        ],
        'completed_tasks': 5,
        'failed_tasks': 0,
        'timestamp': datetime.now().isoformat()
    })
