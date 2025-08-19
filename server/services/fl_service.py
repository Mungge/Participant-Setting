import logging
from datetime import datetime
from typing import Dict, Optional

from utils.openstack import get_openstack_vmList
from services.ssh_service import SSHService

logger = logging.getLogger(__name__)

class FederatedLearningService:
    def __init__(self):
        self.ssh_service = SSHService()

    def get_task_logs(self, task_id: str, vm_id: str) -> Dict:
        """연합학습 작업 로그 조회"""
        # VM 정보 조회
        vm_list = get_openstack_vmList()
        target_vm = self._find_vm_by_id(vm_list, vm_id)
        
        if not target_vm:
            return {
                'success': False,
                'error': f'VM {vm_id} not found'
            }
        
        floating_ip = target_vm.get('floating_ip')
        if not floating_ip:
            return {
                'success': False,
                'error': f'VM {vm_id} has no floating IP'
            }
        
        # SSH로 로그 조회
        log_result = self.ssh_service.get_logs(floating_ip, task_id)
        
        if log_result['success']:
            return {
                'success': True,
                'task_id': task_id,
                'vm_id': vm_id,
                'log_content': log_result['log_content'],
                'process_running': log_result['process_running'],
                'process_info': log_result['process_info'],
                'error': log_result.get('error'),
                'timestamp': datetime.now().isoformat()
            }
        else:
            return {
                'success': False,
                'error': log_result['error']
            }

    def _find_vm_by_id(self, vm_list: list, vm_id: str) -> Optional[Dict]:
        """VM ID로 VM 정보 찾기"""
        for vm in vm_list:
            if vm.get('id') == vm_id:
                return vm
        return None
