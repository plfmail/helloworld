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

    stages {
        stage('Checkout') {
            steps {
                echo '===== ① 代码检出（GitHub 触发）====='
                checkout scm
                sh 'git log --oneline -3'
            }
        }

        stage('SonarQube Scan') {
            steps {
                echo '===== ③ SonarQube 代码扫描 ====='
                script {
                    def scannerStatus = sh(
                        script: """
                            docker run --rm \
                                --network ai_network \
                                --volumes-from cicd-jenkins \
                                -e SONAR_HOST_URL=${SONAR_HOST_URL} \
                                -w "${WORKSPACE}" \
                                sonarsource/sonar-scanner-cli
                        """,
                        returnStatus: true
                    )
                    if (scannerStatus != 0) {
                        error("SonarQube 扫描失败，退出码: ${scannerStatus}")
                    }
                    echo '✅ SonarQube 扫描完成'
                }
            }
        }

        stage('AI Pytest White-box Test') {
            steps {
                echo '===== ④ AI 测试平台 Pytest 白盒测试（3002 接口）====='
                script {
                    // 1. 解析 Portal 凭证
                    def aiCredsJson = credentials('ai-platform-credentials')
                    def aiCreds = new groovy.json.JsonSlurper().parseText(aiCredsJson)
                    def portalUser = aiCreds.username
                    def portalPass = aiCreds.password

                    // 2. 清理并准备 backend 容器中的被测代码目录
                    def prepareStatus = sh(
                        script: """
                            docker exec ai_playwright_backend sh -c 'rm -rf ${UNDER_TEST_DIR} && mkdir -p ${UNDER_TEST_DIR}'
                        """,
                        returnStatus: true
                    )
                    if (prepareStatus != 0) {
                        error("清理 ${UNDER_TEST_DIR} 失败")
                    }

                    // 3. 将当前工作区代码复制到 AI 测试平台 backend 容器
                    def copyStatus = sh(
                        script: """
                            tar -cf - . | docker exec -i ai_playwright_backend tar -xf - -C ${UNDER_TEST_DIR}
                        """,
                        returnStatus: true
                    )
                    if (copyStatus != 0) {
                        error("复制代码到 ai_playwright_backend 容器失败")
                    }

                    // 4. Portal 登录获取 JWT Token
                    def loginResp = sh(
                        script: """
                            curl -s -X POST ${PORTAL_URL}/api/login \
                                -H 'Content-Type: application/json' \
                                -d '{"username":"${portalUser}","password":"${portalPass}"}'
                        """,
                        returnStdout: true
                    ).trim()
                    echo "Portal 登录响应: ${loginResp}"

                    def loginJson
                    try {
                        loginJson = new groovy.json.JsonSlurper().parseText(loginResp)
                    } catch (Exception e) {
                        error("Portal 登录响应不是合法 JSON: ${loginResp}")
                    }
                    if (loginJson?.success != true || !loginJson?.data?.token) {
                        error("Portal 登录失败: ${loginJson?.message ?: loginResp}")
                    }
                    def jwtToken = loginJson.data.token

                    // 5. 调用白盒测试一键执行接口
                    //    Playwright 平台读取 /app/under-test 源码，由平台 AI 生成 pytest 白盒测试脚本并执行
                    def pytestResp = sh(
                        script: """
                            curl -s -X POST ${AI_PLATFORM_URL}/api/pytest/whitebox-execute \
                                -H 'Content-Type: application/json' \
                                -H "Authorization: Bearer ${jwtToken}" \
                                -d '{"test_dir":"${UNDER_TEST_DIR}","name":"helloworld_${BUILD_NUMBER}","pytest_args":"-v --tb=short --color=no"}'
                        """,
                        returnStdout: true
                    ).trim()
                    echo "Pytest 白盒测试响应: ${pytestResp}"

                    def pytestJson
                    try {
                        pytestJson = new groovy.json.JsonSlurper().parseText(pytestResp)
                    } catch (Exception e) {
                        error("Pytest 响应不是合法 JSON: ${pytestResp}")
                    }
                    if (pytestJson?.success != true) {
                        error("AI Pytest 白盒测试执行失败: ${pytestJson?.error ?: pytestResp}")
                    }
                    if (pytestJson?.status != 'completed') {
                        error("AI Pytest 白盒测试未通过: status=${pytestJson?.status}, passed=${pytestJson?.passed}, failed=${pytestJson?.failed}, errors=${pytestJson?.errors}")
                    }

                    echo "✅ AI Pytest 白盒测试通过: passed=${pytestJson?.passed}, failed=${pytestJson?.failed}, errors=${pytestJson?.errors}"
                }
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
