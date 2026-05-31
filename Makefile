.PHONY: dev dev2 prod build build-pipeline down logs

# 개발 (HMR, 포트 5536)
dev:
	DEV_PORT=5536 DEV_CMD=dev:docker docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d

# 개발 2 (HMR, 포트 5537)
dev2:
	DEV_PORT=5537 DEV_CMD=dev2:docker docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d

# 시연/프로덕션 (포트 5535) — 이미지 없으면 자동 빌드
prod:
	docker compose -f infra/docker-compose.yml up -d

# web 프로덕션 이미지 재빌드 후 반영 (코드 변경 시)
build:
	docker compose -f infra/docker-compose.yml build --no-cache web
	docker compose -f infra/docker-compose.yml up -d --force-recreate web

# pipeline 이미지 재빌드 후 반영 (pipeline 코드 변경 시)
build-pipeline:
	docker compose -f infra/docker-compose.yml build --no-cache pipeline
	docker compose -f infra/docker-compose.yml up -d --force-recreate pipeline

# 전체 종료
down:
	docker compose -f infra/docker-compose.yml down

# 로그
logs:
	docker compose -f infra/docker-compose.yml logs -f
