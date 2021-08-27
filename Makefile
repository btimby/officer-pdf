DOCKER_COMPOSE = docker-compose

build:
	${DOCKER_COMPOSE} build

run: build
	${DOCKER_COMPOSE} up
