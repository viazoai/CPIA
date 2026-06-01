.PHONY: dev dev2 prod build build-pipeline rebuild rebuild-pipeline down logs

# 개발 (HMR, 포트 5536)
dev:
	DEV_PORT=5536 DEV_CMD=dev:docker docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d
	@echo ""
	@echo "  CPIA Dev Server"
	@echo ""
	@echo "  ➜  Local:   http://localhost:5536"
	@echo ""

# 개발 2 (HMR, 포트 5537)
dev2:
	DEV_PORT=5537 DEV_CMD=dev2:docker docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d
	@echo ""
	@echo "  CPIA Dev Server"
	@echo ""
	@echo "  ➜  Local:   http://localhost:5537"
	@echo ""

# 시연/프로덕션 (포트 5535) — 이미지 없으면 자동 빌드
prod:
	docker compose -f infra/docker-compose.yml up -d

# web 프로덕션 이미지 재빌드 후 반영 (코드 변경 시)
# 캐시 사용: 변경된 레이어만 다시 빌드 → 빠르고 빌드캐시 누적 없음.
# 소스(web/) 변경 시 COPY 레이어 해시가 바뀌어 정상 반영된다.
build:
	docker compose -f infra/docker-compose.yml build web
	docker compose -f infra/docker-compose.yml up -d --force-recreate web

# pipeline 이미지 재빌드 후 반영 (pipeline 코드 변경 시)
build-pipeline:
	docker compose -f infra/docker-compose.yml build pipeline
	docker compose -f infra/docker-compose.yml up -d --force-recreate pipeline

# (드물게) 캐시 무시하고 처음부터 재빌드 — 캐시 꼬임 의심 시에만 사용
rebuild:
	docker compose -f infra/docker-compose.yml build --no-cache web
	docker compose -f infra/docker-compose.yml up -d --force-recreate web

rebuild-pipeline:
	docker compose -f infra/docker-compose.yml build --no-cache pipeline
	docker compose -f infra/docker-compose.yml up -d --force-recreate pipeline

# 전체 종료
down:
	docker compose -f infra/docker-compose.yml down

# 로그
logs:
	docker compose -f infra/docker-compose.yml logs -f
