# Fleecy Cloud Participant Server

Flask를 기반으로 한 간단한 참가자 서버입니다.

## 기능

- **헬스 체크**: 서버 상태 모니터링
- **참가자 정보**: 참가자 시스템 정보 제공
- **모니터링 메트릭**: CPU, 메모리, 디스크 사용량 등
- **작업 관리**: 연합학습 작업 상태 관리
- **RESTful API**: JSON 기반 API 제공

## API 엔드포인트

### 기본 엔드포인트

- `GET /` - 서버 정보
- `GET /health` - 헬스 체크

### 참가자 정보

- `GET /api/participant/info` - 참가자 정보 조회

### 모니터링

- `GET /api/monitoring/metrics` - 시스템 메트릭 조회

### 작업 관리

- `GET /api/tasks/status` - 작업 상태 조회
- `POST /api/tasks/submit` - 새 작업 제출

## 설치 및 실행

### 1. 의존성 설치

```bash
# 가상환경 생성 (권장)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 설정

```bash
# 환경 변수 파일 생성
cp .env.example .env

# .env 파일을 편집하여 설정 변경
```

### 3. 서버 실행

#### 개발 환경

```bash
# 간단한 방법
./start_server.sh

# 또는 직접 실행
python app.py
```

## 환경 변수

| 변수명           | 기본값              | 설명        |
| ---------------- | ------------------- | ----------- |
| HOST             | 0.0.0.0             | 서버 호스트 |
| PORT             | 5000                | 서버 포트   |
| DEBUG            | False               | 디버그 모드 |
| PARTICIPANT_ID   | participant-001     | 참가자 ID   |
| PARTICIPANT_NAME | Default Participant | 참가자 이름 |

## 로그

- 액세스 로그: `logs/access.log`
- 에러 로그: `logs/error.log`

## 테스트

```bash
# 서버 상태 확인
curl http://localhost:5000/health

# 참가자 정보 조회
curl http://localhost:5000/api/participant/info

# 모니터링 메트릭 조회
curl http://localhost:5000/api/monitoring/metrics
```

## 개발 참고사항

- Flask-CORS가 설정되어 있어 크로스 오리진 요청이 허용됩니다
- JSON 형태의 응답을 제공합니다
- 에러 핸들링이 구현되어 있습니다
- 로깅이 설정되어 있습니다

## 확장 가능성

이 서버는 기본 구조를 제공하며, 다음과 같이 확장할 수 있습니다:

- 실제 시스템 메트릭 수집 (psutil 사용)
- 데이터베이스 연동
- 인증/인가 시스템
- 웹소켓 실시간 통신
- 작업 큐 시스템 (Celery 등)
- 컨테이너화 (Docker)
