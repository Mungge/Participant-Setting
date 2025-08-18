from flask import Blueprint, jsonify, render_template
from datetime import datetime

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """메인 페이지"""
    return jsonify({
        'message': 'Fleecy Cloud Participant Server',
        'status': 'running',
        'timestamp': datetime.now().isoformat()
    })

@main_bp.route('/health')
def health_check():
    """서버 상태 확인"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

# Web Dashboard
@main_bp.route('/dashboard')
def dashboard():
    """앱 상태를 확인하고 API를 테스트할 수 있는 웹 대시보드"""
    return render_template('index.html')

# 에러 핸들러
@main_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@main_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500
