from flask import Blueprint, jsonify, request
from datetime import datetime
import logging

from services.fl_service import FederatedLearningService
import os

logger = logging.getLogger(__name__)

fl_bp = Blueprint('fl', __name__)
fl_service = FederatedLearningService()

@fl_bp.route('/api/fl/execute', methods=['POST'])
def execute_federated_learning():
    """연합학습 코드와 환경 변수를 받아서 지정된 VM에서 실행"""
    try:
        # 요청 데이터 검증
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
            
        data = request.get_json()
        
        # 필수 필드 검증
        required_fields = ['vm_id', 'fl_code', 'env_config']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {missing_fields}',
                'required_fields': required_fields
            }), 400
        
        vm_id = data['vm_id']
        fl_code = data['fl_code']  # 연합학습 Python 코드 (문자열)
        env_config = data['env_config']  # 환경 변수 설정 (딕셔너리)

        # 선택적 필드
        entry_point = data.get('entry_point', 'main.py')  # 실행할 파일명
        requirements = data.get('requirements', [])  # 추가 패키지 리스트
    # 추가 파일 (예: pyproject.toml, 패키지 파일 등). 맵 형태: { "파일명": "내용" }
        additional_files = data.get('additional_files', {})
        # 커스텀 실행 커맨드 (예: flwr run .)
        custom_command = data.get('custom_command')
        
        # 연합학습 실행
        result = fl_service.execute_fl_task(
            vm_id=vm_id,
            fl_code=fl_code,
            env_config=env_config,
            entry_point=entry_point,
            requirements=requirements
            , additional_files=additional_files
            , custom_command=custom_command
        )
        
        status_code = 201 if result['success'] else 500
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Error executing federated learning: {str(e)}")
        return jsonify({'error': 'Failed to execute federated learning'}), 500


@fl_bp.route('/api/fl/deploy-flower-test', methods=['POST'])
def deploy_flower_test_app():
    """test 폴더의 Flower 예시 앱을 VM에 배포/실행 (flwr run .)"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        data = request.get_json()
        vm_id = data.get('vm_id')
        env_config = data.get('env_config', {})

        # Collect files from server/test
        root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'test')
        pyproject_path = os.path.join(root, 'pyproject.toml')
        pkg_init_path = os.path.join(root, 'test', '__init__.py')
        client_app_path = os.path.join(root, 'test', 'client_app.py')
        server_app_path = os.path.join(root, 'test', 'server_app.py')
        task_path = os.path.join(root, 'test', 'task.py')

        if not os.path.exists(pyproject_path):
            return jsonify({'error': 'test/pyproject.toml not found'}), 500

        def read(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()

        additional_files = {
            'pyproject.toml': read(pyproject_path),
            'test/__init__.py': read(pkg_init_path) if os.path.exists(pkg_init_path) else '',
            'test/client_app.py': read(client_app_path),
            'test/server_app.py': read(server_app_path),
            'test/task.py': read(task_path),
        }

        # requirements for remote env: need flwr runtime and torch/vision per pyproject
        # We'll rely on `pip install -e .` to install dependencies from pyproject.toml
        # So requirements list can be empty here; we'll install via custom command.

        # Compose custom command: install hatchling, pip install -e ., then run flwr
        custom_cmd = (
            'bash -lc '
            '"python3 -m pip install --upgrade pip && '
            'python3 -m pip install hatchling && '
            'pip install -e . && '
            'flwr run ."'
        )

        # An entry file is not used, but provide a dummy to satisfy API
        fl_code = '# Flower app deployment placeholder'  # not executed

        result = fl_service.execute_fl_task(
            vm_id=vm_id,
            fl_code=fl_code,
            env_config=env_config,
            entry_point='noop.py',
            requirements=[],
            additional_files=additional_files,
            custom_command=custom_cmd
        )
        status_code = 201 if result['success'] else 500
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Error in deploy_flower_test_app: {str(e)}")
        return jsonify({'error': 'Failed to deploy Flower test app'}), 500


@fl_bp.route('/api/fl/deploy-flower-app', methods=['POST'])
def deploy_flower_app():
    """Flower 기반 템플릿(pyproject.toml + test 패키지)을 업로드하고 flwr run . 실행"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        data = request.get_json()
        vm_id = data.get('vm_id')
        # run_config: Flower pyproject.toml의 [tool.flwr.app.config]를 대체할 값들(JSON)
        run_config = data.get('env_config', {})
        user_pyproject = data.get('pyproject_toml')
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fl_client_templates')
        pyproject = os.path.join(base, 'pyproject.toml')
        client_app = os.path.join(base, 'client_app.py')
        for p in [pyproject, client_app]:
            if not os.path.exists(p):
                return jsonify({'error': f'Template file missing: {p}'}), 500

        def read(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()

        def to_toml_literal(val):
            # 간단한 TOML 리터럴 변환기 (숫자/불리언/문자열)
            if isinstance(val, bool):
                return 'true' if val else 'false'
            if isinstance(val, (int, float)):
                return str(val)
            # 기본 문자열 처리
            s = str(val)
            s = s.replace('"', '\"')
            return f'"{s}"'

        def patch_pyproject_config(pyproj_text: str, run_cfg: dict) -> str:
            """주어진 pyproject 본문에서 [tool.flwr.app.config] 블록만 run_cfg로 대체"""
            if not run_cfg:
                return pyproj_text
            import re
            # 새 블록 생성
            lines = ["[tool.flwr.app.config]"]
            for k, v in run_cfg.items():
                lines.append(f"{k} = {to_toml_literal(v)}")
            new_block = "\n".join(lines) + "\n\n"
            # 기존 블록 탐지 및 치환
            pattern = re.compile(r"(?ms)^\[tool\\.flwr\\.app\\.config\]\s*.*?(?=^\[|\Z)")
            if pattern.search(pyproj_text):
                return pattern.sub(new_block.rstrip("\n"), pyproj_text)
            # 없으면 맨 끝에 추가
            if not pyproj_text.endswith('\n'):
                pyproj_text += '\n'
            return pyproj_text + '\n' + new_block

        def patch_components_client_only(pyproj_text: str, client_path: str) -> str:
            """[tool.flwr.app.components] 블록을 clientapp만 포함하도록 교체"""
            import re
            block = (
                "[tool.flwr.app.components]\n"
                f"clientapp = \"{client_path}\"\n\n"
            )
            pattern = re.compile(r"(?ms)^\[tool\\.flwr\\.app\\.components\]\s*.*?(?=^\[|\Z)")
            if pattern.search(pyproj_text):
                return pattern.sub(block.rstrip("\n"), pyproj_text)
            if not pyproj_text.endswith('\n'):
                pyproj_text += '\n'
            return pyproj_text + '\n' + block

        def patch_federations_default_to_remote(pyproj_text: str) -> str:
            """[tool.flwr.federations]의 default를 remote-federation으로 설정"""
            import re
            pattern = re.compile(r"(?m)^(\[tool\\.flwr\\.federations\][\s\S]*?)(^\[|\Z)")
            m = pattern.search(pyproj_text)
            if not m:
                # 섹션이 없으면 새로 추가
                return pyproj_text + ("\n" if not pyproj_text.endswith("\n") else "") + "\n[tool.flwr.federations]\ndefault = \"remote-federation\"\n\n"
            section = m.group(1)
            section = re.sub(r"(?m)^default\s*=\s*\".*?\"", 'default = "remote-federation"', section)
            if 'default' not in section:
                section = section.rstrip("\n") + '\n' + 'default = "remote-federation"' + '\n'
            start, end = m.span(1)
            return pyproj_text[:start] + section + pyproj_text[end:]

        def set_remote_address(pyproj_text: str, address: str) -> str:
            """[tool.flwr.federations.remote-federation]의 address 설정"""
            import re
            block_pattern = re.compile(r"(?ms)^\[tool\\.flwr\\.federations\\.remote-federation\]\s*.*?(?=^\[|\Z)")
            addr_line = f"address = \"{address}\"\n"
            if block_pattern.search(pyproj_text):
                def repl(m):
                    block = m.group(0)
                    # address 라인 교체 또는 추가
                    if re.search(r"(?m)^address\s*=\s*\".*?\"", block):
                        block = re.sub(r"(?m)^address\s*=\s*\".*?\"", addr_line.rstrip("\n"), block)
                    else:
                        if not block.endswith('\n'):
                            block += '\n'
                        block += addr_line
                    # insecure 기본 유지
                    return block
                return block_pattern.sub(repl, pyproj_text)
            # 블록이 없으면 추가
            tail = "\n[tool.flwr.federations.remote-federation]\n" + addr_line + "insecure = true\n\n"
            return pyproj_text + ("\n" if not pyproj_text.endswith("\n") else "") + tail

        # 최종 pyproject.toml 결정: 사용자가 전체 본문을 주면 그대로 사용, 아니면 템플릿에 run_config만 반영
        template_pyproj = read(pyproject)
        # 내부 제어 키 분리 후 config만 반영
        remote_addr = run_config.get('remote-address') or run_config.get('superlink-address')
        cfg_only = {k: v for k, v in run_config.items() if k not in {'client-only', 'remote-address', 'superlink-address'}}
        base_pyproj = (
            user_pyproject if isinstance(user_pyproject, str) and user_pyproject.strip()
            else patch_pyproject_config(template_pyproj, cfg_only)
        )
        # 무조건 클라이언트 전용으로 패치하고, 기본 federation을 remote로 설정
        final_pyproj = patch_components_client_only(base_pyproj, 'client_app:app')
        final_pyproj = patch_federations_default_to_remote(final_pyproj)
        if isinstance(remote_addr, str) and remote_addr.strip():
            final_pyproj = set_remote_address(final_pyproj, remote_addr.strip())

        additional_files = {
            'pyproject.toml': final_pyproj,
            'client_app.py': read(client_app),
        }

        # Explicitly install only the four requested dependencies on the VM, then run flwr
        custom_cmd = (
            'bash -lc '
            '"python3 -m pip install --upgrade pip && '
            'python3 -m pip install '
            '"flwr[simulation]>=1.20.0" '
            '"flwr-datasets[vision]>=0.5.0" '
            '"torch==2.7.1" '
            '"torchvision==0.22.1" && '
            'flwr run ."'
        )

        # run_config는 pyproject.toml에만 반영하고, 환경 변수는 비움
        result = fl_service.execute_fl_task(
            vm_id=vm_id,
            fl_code='# flower app template',
            env_config={},
            entry_point='noop.py',
            requirements=[],
            additional_files=additional_files,
            custom_command=custom_cmd
        )
        status_code = 201 if result['success'] else 500
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Error in deploy_flower_app: {str(e)}")
        return jsonify({'error': 'Failed to deploy flower app'}), 500

@fl_bp.route('/api/fl/logs/<string:task_id>', methods=['GET'])
def get_fl_logs(task_id):
    """연합학습 작업 로그 조회"""
    try:
        vm_id = request.args.get('vm_id')
        if not vm_id:
            return jsonify({'error': 'vm_id parameter is required'}), 400
        
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
