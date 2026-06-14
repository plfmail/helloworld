pipeline {
    agent any

    environment {
        // AI 测试平台前端地址（容器内网络，3002 映射）
        AI_PLATFORM_URL = 'http://ai_playwright_frontend:3000'
        PORTAL_URL = 'http://ai_portal:5003'

        // SonarQube 地址（容器内网络）
        SONAR_HOST_URL = 'http://cicd-sonarqube:9000'

        // 部署配置
        IMAGE_NAME = 'helloworld'
        DEPLOY_CONTAINER = 'helloworld-dev'
        DEPLOY_HOST_PORT = '8080'
        APP_PORT = '5008'

        // 被测代码在 AI 测试平台 backend 容器中的目标目录
        UNDER_TEST_DIR = '/app/under-test'
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
    }

    triggers {
        pollSCM('* * * * *')
    }

    stages {
        stage('Checkout') {
            steps {
                echo '===== ① 代码检出 ====='
                checkout scm
                sh 'git log --oneline -3'
            }
        }

        stage('SonarQube Scan') {
            steps {
                echo '===== ② SonarQube 代码扫描 ====='
                withSonarQubeEnv('my-sonarqube') {
                    sh "docker run --rm --network ai_network -v /var/jenkins_home/workspace:/var/jenkins_home/workspace -e SONAR_HOST_URL=\${SONAR_HOST_URL} -e SONAR_AUTH_TOKEN=\${SONAR_AUTH_TOKEN} -w \"${WORKSPACE}\" sonarsource/sonar-scanner-cli -Dsonar.projectKey=helloworld -Dsonar.sources=."
                }
            }
        }

        stage('Quality Gate') {
            steps {
                echo '===== ③ Quality Gate 检查 ====='
                timeout(time: 1, unit: 'HOURS') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('AI Pytest - Whitebox') {
            steps {
                echo '===== ④ AI Pytest 白盒测试 ====='
                sh label: 'AI Pytest whitebox', script: """
                    PORTAL_URL="http://ai_portal:5003"
                    AI_URL="http://ai_playwright_frontend:3000"

                    # 1. Portal 登录
                    echo "[1/3] Portal 登录..."
                    LOGIN_RESP=\$(curl -s -X POST "\${PORTAL_URL}/api/login" \
                        -H 'Content-Type: application/json' \
                        -d '{"username":"admin","password":"Admin@123456"}')
                    JWT_TOKEN=\$(echo "\$LOGIN_RESP" | sed -n 's/.*"token":"\\([^"]*\\)".*/\\1/p')
                    if [ -z "$JWT_TOKEN" ]; then
                        echo "Portal 登录失败: $LOGIN_RESP"
                        exit 1
                    fi
                    echo "Portal 登录成功"

                    # 2. 复制代码到后端容器
                    echo "[2/3] 复制代码到后端容器..."
                    docker exec ai_playwright_backend sh -c "rm -rf \${UNDER_TEST_DIR} && mkdir -p \${UNDER_TEST_DIR}" || {
                        echo "清理目标目录失败"
                        exit 1
                    }
                    tar -cf - . | docker exec -i ai_playwright_backend tar -xf - -C "\${UNDER_TEST_DIR}" || {
                        echo "复制代码失败"
                        exit 1
                    }
                    echo "代码复制完成"

                    # 3. 白盒测试
                    echo "[3/3] 执行白盒测试..."
                    PAYLOAD=\$(printf '{"test_dir":"%s","name":"helloworld_%s","pytest_args":"-v --tb=short --color=no"}' "\${UNDER_TEST_DIR}" "\${BUILD_NUMBER}")
                    WHITEBOX_RESP=\$(curl -s -X POST "\${AI_URL}/api/pytest/whitebox-execute" \
                        -H 'Content-Type: application/json' \
                        -H "Authorization: Bearer \${JWT_TOKEN}" \
                        -d "\$PAYLOAD")
                    echo "白盒测试响应: \$WHITEBOX_RESP"

                    if echo "\$WHITEBOX_RESP" | grep -q '"status":"completed"'; then
                        echo "✅ 白盒测试通过"
                    else
                        echo "白盒测试未通过: \$WHITEBOX_RESP"
                        exit 1
                    fi
                """
            }
        }

        stage('AI Pytest - SonarQube Trigger') {
            steps {
                echo '===== ⑤ SonarQube Trigger（非阻塞）====='
                sh label: 'SonarQube trigger', script: """
                    curl -s -X POST http://ai_playwright_frontend:3000/api/sonarqube/trigger \
                        -H 'Content-Type: application/json' \
                        -H 'X-API-Key: jenkins-sonarqube-2026' \
                        -d '{"project_key":"helloworld","repo_path":"","changed_files":[],"issues":[],"coverage_gap":null}'
                """
            }
        }

        stage('Build Docker Image') {
            steps {
                echo '===== ⑤ Jenkins 构建编译 ====='
                script {
                    def buildStatus = sh(
                        script: """
                            tar -cf - . | docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} -t ${IMAGE_NAME}:latest -
                        """,
                        returnStatus: true
                    )
                    if (buildStatus != 0) {
                        error("Docker 镜像构建失败")
                    }
                    echo "✅ Docker 镜像构建完成: ${IMAGE_NAME}:${BUILD_NUMBER}"
                }
            }
        }

        stage('Deploy to Dev') {
            steps {
                echo '===== ⑥ 部署开发测试环境 ====='
                script {
                    def deployStatus = sh(
                        script: """
                            docker stop ${DEPLOY_CONTAINER} || true
                            docker rm ${DEPLOY_CONTAINER} || true
                            docker run -d --name ${DEPLOY_CONTAINER} \
                                --network ai_network \
                                -p ${DEPLOY_HOST_PORT}:${APP_PORT} \
                                --restart unless-stopped \
                                ${IMAGE_NAME}:latest
                        """,
                        returnStatus: true
                    )
                    if (deployStatus != 0) {
                        error("部署到开发测试环境失败")
                    }
                    echo "🚀 应用已部署到开发测试环境: http://host.docker.internal:${DEPLOY_HOST_PORT}"
                }
            }
        }
    }

    post {
        always {
            echo "===== 流水线结束: ${env.JOB_NAME} #${env.BUILD_NUMBER} ====="
        }
        success {
            echo "✅ 流水线执行成功！访问地址: http://host.docker.internal:${DEPLOY_HOST_PORT}"
        }
        failure {
            echo "❌ 流水线执行失败，请查看上方日志定位问题。"
        }
    }
}
