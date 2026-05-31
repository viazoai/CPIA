.PHONY: dev prod down logs

# 개발 (HMR, 포트 5537)
dev:
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d

# 시연/프로덕션 (포트 5535)
prod:
	docker compose -f infra/docker-compose.yml up -d

# 전체 종료
down:
	docker compose -f infra/docker-compose.yml down

# 로그
logs:
	docker compose -f infra/docker-compose.yml logs -f
