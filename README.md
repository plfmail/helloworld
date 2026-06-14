# helloworld - AI-CICD Demo

一个最简 Flask 示例应用，用于演示完整的 AI-CICD 流水线：

```
① GitHub 代码提交
    ↓ webhook
② Jenkins 触发
    ↓
③ SonarQube 代码扫描
    ↓
④ AI 测试平台 Pytest 白盒测试（ai_playwright_backend 容器执行）
    ↓ (通过)
⑤ Jenkins 构建 Docker 镜像
    ↓
⑥ 部署到开发测试环境
```

## 目录说明

| 文件 | 说明 |
|------|------|
| `app.py` | Flask 主应用 |
| `requirements.txt` | Python 依赖 |
| `templates/index.html` | 首页模板 |
| `Dockerfile` | 应用镜像构建 |
| `Jenkinsfile` | CI/CD 流水线 |
| `sonar-project.properties` | SonarQube 扫描配置 |

## 前置条件

1. **Jenkins** 已启动（`cicd-jenkins` 容器，端口 8888）。
2. **SonarQube** 已启动（`cicd-sonarqube` 容器，端口 9090）。
3. **AI 质量平台** 已启动（`ai_playwright_backend` 等容器）。
4. Jenkins 容器已挂载 `/var/run/docker.sock`，可执行 Docker 命令。
5. 所有服务在同一个 Docker 网络 `ai_network` 中。

## Jenkins 凭证配置

### 1. AI 平台凭证（已存在）

初始化脚本 `01jenkins/init.groovy.d/ai-setup.groovy` 已自动创建：

- **ID**: `ai-platform-credentials`
- **值**: `{"username":"admin","password":"Admin@123456"}`

如果缺失，请在 Jenkins 中手动添加一个 **Secret text** 类型凭证，ID 为 `ai-platform-credentials`，值为上述 JSON。

### 2. OpenAI API Key 凭证（可选但推荐）

流水线会自动读取 ID 为 `openai-api-key` 的 **Secret text** 凭证，并通过 `/api/config/save/openai` 接口配置到 AI 测试平台。

如果 AI 测试平台已经在系统设置中配置好 OpenAI API Key，则此凭证可以省略。

> 注意：当前 `ai_playwright_backend` 容器通过系统设置（数据库）读取 OpenAI 配置，若未配置，白盒测试将失败。

## Jenkins Job 配置

1. 在 Jenkins 中创建一个新的 **Pipeline** 类型 Job，例如 `helloworld-cicd-demo`。
2. 在 **Pipeline** 配置中选择 **Pipeline script from SCM**。
3. SCM 选择 **Git**，填写 GitHub 仓库地址（如 `https://github.com/<your-org>/helloworld.git`）。
4. 指定分支（如 `*/main`）。
5. **Script Path** 保持默认 `Jenkinsfile`。
6. 保存。

## GitHub Webhook 配置

1. 在 GitHub 仓库中进入 **Settings → Webhooks → Add webhook**。
2. **Payload URL** 填写：
   ```
   http://<你的公网IP或内网穿透地址>:8888/github-webhook/
   ```
   如果是本地测试，可使用 [ngrok](https://ngrok.com/) 等工具暴露 Jenkins 地址。
3. **Content type** 选择 `application/json`。
4. 选择 **Just the push event**。
5. 保存。

> 如果没有公网地址，也可以在 Jenkins Job 中启用 **Poll SCM**（如 `H/2 * * * *`）或手动点击 **Build Now** 测试。

## 手动测试流水线

在 Jenkins 中进入 `helloworld-cicd-demo` Job，点击 **Build Now**。

流水线将依次执行：

1. 从 GitHub 检出代码
2. SonarQube 扫描
3. AI 测试平台 Pytest 白盒测试
4. 构建 Docker 镜像 `helloworld:<BUILD_NUMBER>`
5. 部署容器 `helloworld-dev`，访问地址：
   ```
   http://host.docker.internal:8080
   ```

## 常见问题

### 1. SonarQube 扫描失败

- 确认 `cicd-sonarqube` 容器健康运行。
- 确认 `sonar-project.properties` 中的 `sonar.token` 有效。
- 流水线中通过环境变量 `SONAR_HOST_URL` 覆盖为 `http://cicd-sonarqube:9000`。

### 2. AI Pytest 提示 "API Key 未配置"

- 在 Jenkins 中添加 `openai-api-key` 凭证，流水线会自动配置。
- 或在 AI 测试平台前端（`http://host.docker.internal:3002`）进入系统设置，手动填写 OpenAI API Key、Base URL 和 Model。

### 3. docker build / docker cp 路径问题

Jenkins 容器内通过挂载的 `docker.sock` 调用宿主机 Docker Daemon，直接使用 `docker build .` 会找不到容器内路径。本流水线使用以下方式解决：

- 复制代码到 `ai_playwright_backend`：`tar -cf - . | docker exec -i ... tar -xf -`
- 构建镜像：`tar -cf - . | docker build -t ... -`
- SonarQube 扫描：`docker run --volumes-from cicd-jenkins ...`

### 4. 3002 端口与 Pytest 执行容器

用户描述中提到的 "3002 容器" 是指 AI 测试平台前端（`ai_playwright_frontend`，端口 3002）。
实际的 Pytest 白盒测试执行发生在 **后端容器 `ai_playwright_backend`（端口 5005）**，流水线通过调用其 REST API 触发。
