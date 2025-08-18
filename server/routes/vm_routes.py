from flask import Blueprint, jsonify, request
from datetime import datetime
import logging

from utils.openstack import get_openstack_vmList
from services.ssh_service import SSHService

logger = logging.getLogger(__name__)

vm_bp = Blueprint('vm', __name__)
ssh_service = SSHService()

@vm_bp.route('/api/vms', methods=['GET'])
def get_vm_list():
    """VM ID와 Floating IP 목록 조회 API"""
    try:
        vm_list = get_openstack_vmList()
        if vm_list is None:
            vm_list = []
        
        return jsonify({
            'status': 'success',
            'count': len(vm_list),
            'vms': vm_list,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in get_vm_list endpoint: {str(e)}")
        return jsonify({'error': 'Failed to retrieve VM list'}), 500

@vm_bp.route('/api/vms/<string:vm_id>/ssh-check', methods=['GET'])
def ssh_check(vm_id: str):
    """주어진 VM ID의 Floating IP로 SSH 접속 가능 여부 확인"""
    try:
        vm_list = get_openstack_vmList() or []
        target = next((vm for vm in vm_list if vm.get('id') == vm_id), None)
        if not target:
            return jsonify({'success': False, 'error': f'VM {vm_id} not found'}), 404
        ip = target.get('floating_ip')
        if not ip:
            return jsonify({'success': False, 'error': f'VM {vm_id} has no floating IP'}), 400

        result = ssh_service.check_connection(ip)
        status = 200 if result.get('success') else 502
        result.update({'vm_id': vm_id, 'target_ip': ip, 'timestamp': datetime.now().isoformat()})
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error in ssh_check for {vm_id}: {str(e)}")
        return jsonify({'success': False, 'error': 'SSH check failed'}), 500

@vm_bp.route('/api/ssh-check', methods=['GET'])
def ssh_check_by_ip():
    """IP를 직접 받아 SSH 접속 가능 여부 확인 (OpenStack 의존 없이 테스트용)"""
    try:
        ip = request.args.get('ip')
        if not ip:
            return jsonify({'success': False, 'error': 'ip query parameter is required'}), 400
        result = ssh_service.check_connection(ip)
        status = 200 if result.get('success') else 502
        result.update({'target_ip': ip, 'timestamp': datetime.now().isoformat()})
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error in ssh_check_by_ip: {str(e)}")
        return jsonify({'success': False, 'error': 'SSH check failed'}), 500
