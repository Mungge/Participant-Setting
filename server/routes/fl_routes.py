from flask import Blueprint, jsonify, request
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

fl_bp = Blueprint('fl', __name__)

@fl_bp.route('/api/fl/execute', methods=['POST'])
def execute_federated_learning():
    """VM ID와 run_config, 그리고 파일들을 받아 client_app.py를 실행(flwr run .)"""
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
        received_files = data.get('files', {})  # 요청으로 받은 파일들

        # 필수 파일 확인
        if not received_files or not received_files.get('pyproject.toml') or not received_files.get('client_app.py') or not received_files.get('server_app.py'):
            return jsonify({'success': False, 'error': 'Required files (pyproject.toml, client_app.py, server_app.py) missing in request'}), 400
            
        logger.info("Using files from request payload")
        pyproj_content = received_files.get('pyproject.toml', '')
        client_app_content = received_files.get('client_app.py', '')
        server_app_content = received_files.get('server_app.py', '')
        task_content = received_files.get('task.py', '')

        # 파일들이 백엔드에서 이미 완전히 준비된 상태로 옴
        # 추가 패치 불필요

        # 파일들 준비
        additional_files = {
            'pyproject.toml': pyproj_content,
            'client_app.py': client_app_content,
            'server_app.py': server_app_content,
        }
        
        # task.py가 있으면 추가
        if task_content:
            additional_files['task.py'] = task_content
            
        # 실행 스크립트 추가
        additional_files['run_fl.sh'] = '''#!/bin/bash
                set -e
                export PATH=$HOME/.local/bin:$PATH

                echo "Checking Python and pip..."
                python3 --version

                # pip 설치 확인 및 설치
                if ! python3 -m pip --version 2>/dev/null; then
                    echo "Installing pip with apt..."
                    sudo apt update && sudo apt install -y python3-pip
                fi

                echo "Installing dependencies..."
                python3 -m pip install --user --upgrade pip
                python3 -m pip install --user flwr>=1.20.0 torch==2.7.1 torchvision==0.22.1 mlflow scikit-learn

                echo "Checking flwr installation..."
                which flwr || echo "flwr not in PATH, will use python -m flwr"

                echo "Starting Flower client..."
                if command -v flwr >/dev/null 2>&1; then
                    flwr run .
                else
                    flwr run .
                fi
                '''

        custom_cmd = 'chmod +x run_fl.sh && ./run_fl.sh'

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
