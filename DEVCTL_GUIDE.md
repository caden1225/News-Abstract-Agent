# 使用 devctl.sh 构建和部署

## 概述

`devctl.sh` 是项目自动化部署脚本，可以一键构建、推送和部署到管理平台。

## 前置条件

### 1. 环境检查

```bash
# 检查开发环境
./devctl.sh check
```

会检查以下内容：
- ✅ zbxctl 是否已安装
- ✅ 是否已登录到管理平台
- ✅ Docker 是否正常运行

### 2. 配置文件

确保以下配置文件存在且正确：

- `.appinfo` - 应用ID配置
- `.devctl.env` - 环境变量配置（REGISTRY等）
- `docker/Dockerfile` - Docker镜像构建文件
- `Bdefile` - BDE配置文件

## devctl.sh 命令

### 1. check - 检查开发环境

```bash
./devctl.sh check
```

### 2. docker - 构建Docker镜像

#### 基础用法（仅构建）

```bash
./devctl.sh docker
```

这个命令会：
- 构建Docker镜像（从 docker/Dockerfile）
- 打上版本标签（时间戳）和 latest 标签
- **不会**推送到仓库
- **不会**部署到平台

#### 构建并推送 (-p)

```bash
./devctl.sh docker -p
```

这个命令会：
- 构建Docker镜像
- 推送到镜像仓库（需要配置 REGISTRY）
- 在管理平台创建版本记录
- **不会**部署应用

#### 构建并部署 (-d)

```bash
./devctl.sh docker -d
```

这个命令会：
- 构建Docker镜像
- 推送到镜像仓库
- 在管理平台创建版本记录
- 部署到默认环境

#### 构建并开发部署 (-dd)

```bash
./devctl.sh docker -dd
```

这个命令会：
- 构建Docker镜像
- 推送到镜像仓库
- 在管理平台创建版本记录
- 部署到开发环境并自动上线

#### 指定部署环境 (-e)

```bash
./devctl.sh docker -d -e prod
```

部署到指定环境（如 prod、staging 等）

#### 组合使用

```bash
# 构建 + 推送 + 部署到开发环境
./devctl.sh docker -p -dd

# 构建 + 推送 + 部署到指定环境
./devctl.sh docker -p -d -e hy_qa
```

### 3. sidecar - 管理Sidecar服务

```bash
# 启动 sidecar
./devctl.sh sidecar start

# 停止 sidecar
./devctl.sh sidecar stop

# 重启 sidecar
./devctl.sh sidecar restart

# 查看状态
./devctl.sh sidecar status
```

## 完整部署流程

### 方式一：开发部署（推荐用于测试）

```bash
# 1. 检查环境
./devctl.sh check

# 2. 启动 sidecar（本地测试需要）
./devctl.sh sidecar start

# 3. 构建、推送并部署（开发模式，自动上线）
./devctl.sh docker -p -dd
```

### 方式二：生产部署

```bash
# 1. 检查环境
./devctl.sh check

# 2. 构建、推送并部署到指定环境
./devctl.sh docker -p -d -e prod
```

## .devctl.env 配置说明

`.devctl.env` 文件包含必要的环境变量：

```bash
# 镜像仓库地址（必须）
export REGISTRY=ccr-53sfop7y-pub.cnc.su.baidubce.com
export REGISTRY_VPC=ccr-53sfop7y-vpc.cnc.su.baidubce.com

# LLM 环境
export LLM_ENV=dev
export LLM_AGENT_ENV=hy_qa
export LLM_DOMAIN_ID=HYUNDAI
```

**重要**：
- `REGISTRY` 是必须配置的，否则无法推送镜像
- 如果不配置，docker -p 会报错

## 镜像标签规则

devctl.sh 生成的镜像标签格式：

```
ebanma/llm-agent:llm-skeleton-test_20250109-102030  # 带时间戳版本
ebanma/llm-agent:llm-skeleton-test_latest            # latest版本
```

推送后的完整标签：

```
${REGISTRY}/ebanma/llm-agent:llm-skeleton-test_20250109-102030
```

## Git 检查

devctl.sh 在构建前会检查是否有未提交的文件：

```bash
$ ./devctl.sh docker -p
# Untracked files:
#   ...
# You have uncommitted files, please ensure this is expected, deployment will continue in 5 seconds
```

这是提醒，不会阻止部署。

## 常见问题

### Q1: 报错 "registry not set"

**原因**：没有配置 .devctl.env 文件或 REGISTRY 变量

**解决**：
```bash
# 检查 .devctl.env 是否存在
cat .devctl.env

# 如果不存在，创建它
cp .devctl.env.example .devctl.env
# 编辑并设置正确的 REGISTRY 值
```

### Q2: 报错 "docker/Dockerfile not found"

**原因**：Dockerfile 不在 docker/ 目录下

**解决**：
```bash
# 确保 docker/Dockerfile 存在
ls -la docker/Dockerfile
```

### Q3: zbxctl 未登录

**原因**：没有登录到管理平台

**解决**：
```bash
# 登录管理平台
zbxctl login

# 或检查配置文件
cat ~/.zebrax/config.yaml
```

### Q4: sidecar 启动失败

**原因**：端口被占用或配置错误

**解决**：
```bash
# 检查端口
lsof -i :13984

# 查看 sidecar 日志
tail -f logs/sidecar.log

# 重启 sidecar
./devctl.sh sidecar restart
```

## 快速参考

| 命令 | 说明 |
|------|------|
| `./devctl.sh check` | 检查环境 |
| `./devctl.sh docker` | 仅构建镜像 |
| `./devctl.sh docker -p` | 构建并推送 |
| `./devctl.sh docker -d` | 构建并部署 |
| `./devctl.sh docker -dd` | 构建并开发部署 |
| `./devctl.sh docker -p -dd` | 构建、推送并开发部署 |
| `./devctl.sh sidecar start` | 启动 sidecar |
| `./devctl.sh sidecar stop` | 停止 sidecar |
| `./devctl.sh sidecar status` | sidecar 状态 |

## 注意事项

1. **首次使用**：确保已运行 `./devctl.sh check` 检查环境
2. **配置文件**：确保 .devctl.env 文件中的 REGISTRY 已正确配置
3. **网络环境**：确保能够访问镜像仓库和管理平台
4. **权限**：确保有 Docker 权限和 zbxctl 操作权限

---

**提示**：大部分情况下，使用 `./devctl.sh docker -p -dd` 即可完成开发和测试部署。
