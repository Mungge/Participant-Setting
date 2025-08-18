import paramiko
import os
import logging
import time
from typing import Dict

from config.settings import Config

logger = logging.getLogger(__name__)

class SSHService:
    def __init__(self):
        self.ssh_user = Config.SSH_USER
        self.ssh_key_path = Config.SSH_KEY_PATH
        self.ssh_port = Config.SSH_PORT

    def deploy_and_execute_fl_code(
        self,
        floating_ip: str,
        task_id: str,
        env_config: dict,
        entry_point: str | None = None,
        additional_files: Dict[str, str] | None = None,
        custom_command: str | None = None,
    ) -> dict:
        """SSH를 통해 연합학습 코드를 VM에 배포하고 실행"""
        try:
            # SSH 클라이언트 생성
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # SSH 연결
            key_path = os.path.expanduser(self.ssh_key_path)
            client.connect(
                hostname=floating_ip,
                port=self.ssh_port,
                username=self.ssh_user,
                key_filename=key_path,
                timeout=10,
            )

            # SFTP 클라이언트 생성
            sftp = client.open_sftp()

            # 원격 작업 디렉토리 생성
            remote_work_dir = f"/tmp/fl-workspace/{task_id}"
            client.exec_command(f"mkdir -p {remote_work_dir}")

            # 파일 업로드
            if additional_files:
                for rel_path, content in additional_files.items():
                    rel_path = rel_path.lstrip("/")
                    if ".." in rel_path:
                        continue
                    remote_path = f"{remote_work_dir}/{rel_path}"
                    remote_dir = os.path.dirname(remote_path)
                    if remote_dir and remote_dir != remote_work_dir:
                        client.exec_command(f'mkdir -p "{remote_dir}"')
                    with sftp.open(remote_path, "w") as f:
                        f.write(content if isinstance(content, str) else str(content))

            # .env 파일 생성
            env_lines = [f"{k}={v}" for k, v in (env_config or {}).items()]
            with sftp.open(f"{remote_work_dir}/.env", "w") as f:
                f.write("\n".join(env_lines))

            sftp.close()

            # 실행 커맨드 작성
            if custom_command:
                execute_cmd = (
                    f"cd {remote_work_dir} && "
                    f"export $(cat .env | xargs) && "
                    f"nohup {custom_command} > {task_id}.log 2>&1 &"
                )
            else:
                ep = entry_point or "main.py"
                execute_cmd = (
                    f"cd {remote_work_dir} && "
                    f"export $(cat .env | xargs) && "
                    f"nohup python3 {ep} > {task_id}.log 2>&1 &"
                )

            logger.info(f"Executing command on {floating_ip}: {execute_cmd}")
            stdin, stdout, stderr = client.exec_command(execute_cmd)
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")
            
            logger.info(f"Command output: {output}")
            if error:
                logger.error(f"Command error: {error}")

            # 파일 목록 확인
            check_files_cmd = f"ls -la {remote_work_dir}"
            _, files_out, _ = client.exec_command(check_files_cmd)
            files_list = files_out.read().decode("utf-8")
            logger.info(f"Files in remote directory: {files_list}")

            # 프로세스 시작 확인
            if custom_command and "flwr run" in custom_command:
                check_target = "flwr"
            elif custom_command:
                check_target = custom_command.split()[0]
            else:
                check_target = entry_point or "python3"
            check_cmd = f"ps aux | grep {check_target} | grep -v grep"
            _, out2, _ = client.exec_command(check_cmd)
            process_check = out2.read().decode("utf-8")

            client.close()

            if error and "nohup" not in error:
                logger.error(f"Error executing FL code on {floating_ip}: {error}")
                return {"success": False, "error": error, "message": "Failed to execute federated learning code"}

            return {
                "success": True,
                "output": output,
                "remote_path": remote_work_dir,
                "message": f"Federated learning code deployed and started in {remote_work_dir}",
                "process_check": process_check.strip() if process_check else "Process check unavailable",
            }

        except Exception as e:
            logger.error(f"Failed to deploy FL code to {floating_ip}: {str(e)}")
            return {"success": False, "error": str(e), "message": "Failed to deploy and execute federated learning code"}

    def get_logs(self, floating_ip: str, task_id: str) -> Dict:
        """SSH를 통해 원격 로그 파일 조회"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=floating_ip,
                port=self.ssh_port,
                username=self.ssh_user,
                key_filename=os.path.expanduser(self.ssh_key_path),
                timeout=10
            )
            
            # 로그 파일 읽기
            log_path = f'/tmp/fl-workspace/{task_id}/{task_id}.log'
            stdin, stdout, stderr = client.exec_command(f'cat {log_path}')
            log_content = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            # 프로세스 상태 확인
            stdin, stdout, stderr = client.exec_command(f'ps aux | grep {task_id} | grep -v grep')
            process_status = stdout.read().decode('utf-8')
            
            client.close()
            
            return {
                'success': True,
                'log_content': log_content,
                'process_running': bool(process_status.strip()),
                'process_info': process_status.strip(),
                'error': error if error else None
            }
            
        except Exception as e:
            logger.error(f"Error getting logs from {floating_ip}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def check_connection(self, floating_ip: str) -> Dict:
        """주어진 IP로 SSH 연결이 가능한지 빠르게 체크"""
        start = time.time()
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=floating_ip,
                port=self.ssh_port,
                username=self.ssh_user,
                key_filename=os.path.expanduser(self.ssh_key_path),
                timeout=5
            )
            # 원격 호스트 확인
            stdin, stdout, stderr = client.exec_command('whoami && uname -srm')
            out = stdout.read().decode('utf-8').strip()
            err = stderr.read().decode('utf-8').strip()
            client.close()

            latency_ms = int((time.time() - start) * 1000)
            return {
                'success': True,
                'message': 'SSH connection succeeded',
                'latency_ms': latency_ms,
                'remote_info': out,
                'warning': err or None
            }
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            logger.error(f"SSH connectivity check failed for {floating_ip}: {str(e)}")
            return {
                'success': False,
                'message': 'SSH connection failed',
                'error': str(e),
                'latency_ms': latency_ms
            }
