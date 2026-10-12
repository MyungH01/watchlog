# watchlog

기계식 시계의 일오차(하루에 몇 초 빠르거나 느린지)를 기록하는 모바일 웹 서비스.
폰 브라우저로 시계 소리를 녹음하면 서버가 분석해서 일오차를 알려 주고, 시계 사진을 찍어 두면 실제 착용 일오차를 계산한다.

요구사항과 설계 근거는 [REQUIREMENTS.md](REQUIREMENTS.md)에 있다.

## 구성

```
[모바일 브라우저] ──HTTPS──> [api: FastAPI + 정적 웹]  ──> [PostgreSQL]
       │                            │
       │ 녹음·사진 직접 업로드         │ 분석 요청 {measurement_id}
       ▼                            ▼
     [S3] <─────────────── [worker: 분석] <── [SQS] ──(3회 실패)──> [격리 큐]
```

| 폴더 | 내용 |
|---|---|
| `backend/app` | API(`api.py`), 워커(`worker.py`), 분석(`analysis.py`), 계산 규칙(`rules.py`), 구글 연결(`auth_google.py`) |
| `backend/migrations` | DB 스키마 (Alembic) |
| `backend/tests` | 테스트. 분석은 `fixtures/`의 실제 아이폰 녹음으로 검증한다 |
| `web` | 화면 (React + Vite). 빌드 결과물을 API가 함께 제공한다 |
| `fixtures` | 실제 녹음 여섯 개와 기준 일오차 (REQUIREMENTS.md 7장) |

## 로컬 실행

Docker Desktop이 켜져 있어야 한다.

```bash
docker compose up --build
```

http://localhost:8000 을 연다. PostgreSQL, LocalStack(S3·SQS), 마이그레이션, API, 워커가 함께 뜬다.

- 마이크는 `localhost`와 HTTPS에서만 동작한다. 폰에서 실제 녹음을 시험하려면 HTTPS로 배포해야 한다.
- PC에서는 측정 화면의 "개발용: WAV 파일로 측정"에 `fixtures/rec3.wav`를 넣으면 업로드 → 큐 → 워커 → 결과 흐름을 볼 수 있다. 이 버튼은 localhost에서만 보인다.

요약 문장과 변화 추세를 보려면 6개월치 예시 기록을 넣는다. 출력되는 쿠키 값을 브라우저 개발자 도구에서 설정하고 새로고침한다.

```bash
docker compose exec api python -m app seed
```

## 실행 명령

이미지는 하나이고 명령으로 역할을 고른다.

| 명령 | 역할 |
|---|---|
| `python -m app api` | API와 웹 화면 (포트 8000) |
| `python -m app worker` | 분석 워커 |
| `python -m app migrate` | DB 스키마를 최신으로 올린다. 배포 때 API보다 먼저 한 번 실행한다 |
| `python -m app seed` | 예시 기록 생성 (개발용) |

## 환경 변수

전체 목록과 설명은 [.env.example](.env.example)에 있다.

| 변수 | 필수 | 설명 |
|---|---|---|
| `DATABASE_URL` | 예 | `postgresql+psycopg://사용자:비밀번호@주소:5432/DB` |
| `S3_BUCKET` | 예 | 녹음과 사진을 두는 버킷 |
| `SQS_QUEUE_URL` | 예 | 분석 요청 큐 |
| `AWS_DEFAULT_REGION` | 예 | 리전 |
| `COOKIE_SECURE` | | 기본 `true`. 로컬 http에서만 `false` |
| `PORT`, `LOG_LEVEL` | | 기본 `8000`, `INFO` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `PUBLIC_BASE_URL` | | 구글 계정 연결. 비워 두면 익명 전용으로 동작한다 |
| `AWS_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL` | | LocalStack 전용. 운영에서는 설정하지 않는다 |

AWS 인증 정보는 앱이 다루지 않는다. boto3 기본 인증 체인을 쓰므로 운영에서는 ECS 태스크 역할을 붙인다.

## 인프라가 제공해야 하는 것

로컬에서는 [localstack-init.sh](localstack-init.sh)가 대신 만든다. 운영 환경을 구성할 때 같은 조건을 맞춘다.

| 항목 | 조건 |
|---|---|
| 로드밸런서 상태 확인 | `GET /health` (프로세스 생존), `GET /ready` (DB 연결까지 확인, 실패 시 503) |
| S3 버킷 | 비공개. 브라우저가 직접 올리므로 서비스 도메인에 대해 `POST`, `GET` CORS 허용 |
| SQS 큐 | 보이지 않는 시간 120초 이상(분석 한 건은 30초 녹음 기준 약 6초). 3회 실패 시 격리 큐로 |
| API 태스크 권한 | S3 `PutObject` `GetObject` `DeleteObject`, SQS `SendMessage` |
| 워커 태스크 권한 | S3 `GetObject` `DeleteObject`, SQS `ReceiveMessage` `DeleteMessage` |
| 녹음 파일 수명 | 워커가 분석을 마치면 녹음을 바로 지운다. 올리기만 하고 분석되지 않은 파일에 대비해 `audio/` 경로에 1일 뒤 삭제하는 수명 주기 규칙을 둔다 |
| 종료 대기 시간 | 워커는 종료 신호를 받으면 진행 중인 한 건을 마치고 멈춘다. 30초 이상으로 둔다 |
| 워커 확장 | 워커 하나가 한 번에 한 건만 처리한다. 큐에 쌓인 메시지 수를 기준으로 워커 수를 늘린다 |
| HTTPS | 필수. 마이크와 세션 쿠키가 HTTPS에서만 동작한다 |
| 로그 | 표준 출력에 JSON 한 줄씩. 요청에는 `request_id` `path` `status` `ms`, 분석에는 `measurement_id` `status` `seconds` |

배포 후에는 점검 스크립트로 전체 흐름을 확인할 수 있다. 시계 등록부터 분석 결과까지 실제로 돌려 보고, 만든 데이터를 지운다.

```bash
cd backend && python scripts/smoke.py https://서비스-주소
```

## 테스트

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS·Linux는 .venv/bin/pip
.venv/Scripts/python -m pytest
```

테스트는 메모리 SQLite와 가짜 S3·SQS로 돌아서 Docker가 필요 없다. 실제 녹음을 분석하므로 2분쯤 걸린다.

화면만 고칠 때는 API를 띄운 채로 개발 서버를 쓴다.

```bash
cd web && npm install && npm run dev
```

## 알려진 한계

- 분석의 기준 일오차는 이 프로젝트의 계산으로 얻은 값이며, 다른 측정 장비와 대조한 참값이 아니다.
- 검증한 환경은 아이폰 사파리와 28,800회/시간 시계 한 개다. 다른 박자는 녹음 속도를 바꾼 흉내 파일로만 확인했다.
- 한 번의 측정은 ±1.5초/일쯤 흔들리고, 폰 자체의 시간 오차가 그대로 섞인다. 화면에는 범위와 함께 표시한다.
- 사진 기록은 사용자가 사진 속 시각을 직접 읽어 입력한다. 자동 판독은 없다.
- 소리 측정과 실제 착용 일오차는 따로 보여 줄 뿐, 그 차이로 소리 측정을 보정하지는 않는다.
- 점검 기준 도달 시점은 지금까지의 변화가 직선으로 이어진다고 가정한 참고값이다. 폰을 바꾸면 폰 시간 오차가 달라져 추세가 왜곡될 수 있다.
- 익명 사용자는 쿠키를 지우면 기록을 다시 볼 수 없다.
