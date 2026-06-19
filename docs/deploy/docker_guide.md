# Docker部署指南

## 目录

- [环境要求](#环境要求)
- [镜像构建](#镜像构建)
- [容器启动](#容器启动)
- [配置说明](#配置说明)

## 环境要求

- Docker Engine >= 20.10
- Docker Compose >= 1.29

## 镜像构建

```bash
bash scripts/build_image.sh
```

或手动执行：

```bash
docker build -t self_evolving_agent:1.0.0 -f Dockerfile .
```

## 容器启动

```bash
docker-compose up -d
```

## 配置说明

配置文件位于config目录，分为dev、test、prod三份：

- dev.yaml: 开发环境配置
- test.yaml: 测试环境配置
- prod.yaml: 生产环境配置

通过环境变量AGENT_CONFIG_PATH指定配置文件路径。
