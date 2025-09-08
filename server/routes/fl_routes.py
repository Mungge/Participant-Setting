from flask import Blueprint, jsonify, request
from datetime import datetime
import logging
import os
import tempfile
import subprocess
import threading

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

echo "=== Flower 클라이언트 설정 시작 ==="

echo "Python 및 pip 확인..."
python3 --version

# pip 설치 확인 및 설치
if ! python3 -m pip --version 2>/dev/null; then
    echo "pip를 설치합니다..."
    sudo apt update && sudo apt install -y python3-pip
fi

echo "의존성 패키지를 설치합니다..."
python3 -m pip install --user --upgrade pip
python3 -m pip install --user flwr>=1.20.0 torch==2.7.1 torchvision==0.22.1

echo "설치된 패키지 확인:"
python3 -m pip list --user | grep -E "(flwr|torch)"

echo "Flower 클라이언트를 시작합니다..."
echo "python3로 클라이언트 실행"
echo "파티션 ID: ` + str(partition_id) + `"
echo "전체 파티션 수: ` + str(num_partitions) + `"
echo "집계자 주소: ` + aggregator_address + `"
python3 client_app.py --server-address ` + aggregator_address + ` --partition-id ` + str(partition_id) + ` --num-partitions ` + str(num_partitions) + ` --local-epochs 3
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


@fl_bp.route('/api/fl/execute-local', methods=['POST'])
def execute_federated_learning_local():
    """파일들을 받아서 로컬에서 python3 client_app.py를 직접 실행"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.get_json()
        required_fields = ['server_address']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing required fields: {missing}', 'required_fields': required_fields}), 400

        # 파라미터 추출
        server_address = data['server_address']
        local_epochs = data.get('local_epochs', 1)
        received_files = data.get('files', {})

        # 필수 파일 확인
        required_files = ['client_app.py', 'task.py']
        missing_files = [f for f in required_files if f not in received_files]
        if missing_files:
            return jsonify({'success': False, 'error': f'Required files missing: {missing_files}'}), 400

        # 임시 디렉토리 생성
        temp_dir = tempfile.mkdtemp(prefix='fl_client_')
        task_id = f"fl-local-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # 파일들을 임시 디렉토리에 저장
        for filename, content in received_files.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        logger.info(f"Files written to temporary directory: {temp_dir}")
        
        # client_app.py 실행 명령 구성
        python_cmd = [
            'python3', 
            os.path.join(temp_dir, 'client_app.py'),
            '--server-address', server_address,
            '--local-epochs', str(local_epochs)
        ]
        
        # 백그라운드에서 실행할 함수
        def run_client():
            try:
                # 환경 변수 설정 (필요한 경우)
                env = os.environ.copy()
                env['PYTHONPATH'] = temp_dir
                
                # 1. 먼저 필요한 패키지들 설치
                logger.info(f"Installing required packages for {task_id}")
                
                # pip 업그레이드 먼저 실행
                upgrade_cmd = ['python3', '-m', 'pip', 'install', '--upgrade', 'pip']
                subprocess.run(upgrade_cmd, cwd=temp_dir, env=env, capture_output=True)
                
                # 패키지 설치
                pip_cmd = [
                    'python3', '-m', 'pip', 'install',
                    'flwr>=1.20.0', 'torch==2.7.1', 'torchvision==0.22.1', 
                    'mlflow', 'scikit-learn', 'Pillow'
                ]
                
                pip_process = subprocess.run(
                    pip_cmd,
                    cwd=temp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10분 타임아웃 (패키지 설치)
                )
                
                if pip_process.returncode != 0:
                    logger.error(f"Package installation failed for {task_id}")
                    logger.error(f"STDOUT: {pip_process.stdout}")
                    logger.error(f"STDERR: {pip_process.stderr}")
                    logger.error(f"Return code: {pip_process.returncode}")
                    return
                else:
                    logger.info(f"Packages installed successfully for {task_id}")
                    logger.info(f"Installation output: {pip_process.stdout}")
                
                # 2. client_app.py 실행
                logger.info(f"Starting FL client {task_id}")
                process = subprocess.run(
                    python_cmd,
                    cwd=temp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1시간 타임아웃
                )
                
                # 결과 로깅
                if process.returncode == 0:
                    logger.info(f"FL Client {task_id} completed successfully")
                    logger.info(f"Output: {process.stdout}")
                else:
                    logger.error(f"FL Client {task_id} failed with return code {process.returncode}")
                    logger.error(f"Stderr: {process.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"FL Client {task_id} timed out")
            except Exception as e:
                logger.error(f"Error running FL Client {task_id}: {str(e)}")

        # 백그라운드 스레드에서 실행
        thread = threading.Thread(target=run_client, daemon=True)
        thread.start()
        
        response = {
            'task_id': task_id,
            'server_address': server_address,
            'local_epochs': local_epochs,
            'submitted_at': datetime.now().isoformat(),
            'success': True,
            'message': 'Federated Learning client started successfully',
            'temp_dir': temp_dir,
            'command': ' '.join(python_cmd)
        }
        
        return jsonify(response), 201
        
    except Exception as e:
        logger.error(f"Error executing local federated learning: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to execute local federated learning: {str(e)}'}), 500
