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

        stage('SonarQube Scan & Quality Gate') {
            steps {
                echo '===== ② SonarQube 代码扫描 + Quality Gate ====='
                script {
                    // 1. SonarQube 扫描
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

                    // 2. 轮询 Quality Gate 状态
                    echo '===== ③ Quality Gate 检查 ====='
                    def gateStatus = 'PENDING'
                    for (def i = 0; i < 30; i++) {
                        sleep(5)
                        def gateResp = sh(
                            script: """
                                curl -s -u admin:admin "${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=helloworld"
                            """,
                            returnStdout: true
                        ).trim()
                        try {
                            def gateJson = new groovy.json.JsonSlurper().parseText(gateResp)
                            gateStatus = gateJson?.projectStatus?.status ?: 'PENDING'
                            echo "Quality Gate 状态: ${gateStatus}"
                            if (gateStatus != 'PENDING' && gateStatus != 'IN_PROGRESS') {
                                break
                            }
                        } catch (Exception e) {
                            echo "解析 Quality Gate 响应失败: ${gateResp}"
                        }
                    }
                    if (gateStatus != 'OK') {
                        error("Quality Gate 未通过: ${gateStatus}")
                    }
                    echo '✅ Quality Gate 通过'
                }
            }
        }

        stage('AI Pytest - SonarQube Trigger') {
            steps {
                echo '===== ④ SonarQube Trigger → AI Pytest ====='
                script {
                    def portalUser = 'admin'
                    def portalPass = 'Admin@123456'

                    // 1. 从 SonarQube 获取 issues
                    def issuesResp = sh(
                        script: """
                            curl -s -u admin:admin "${SONAR_HOST_URL}/api/issues/search?componentKeys=helloworld&ps=100&statuses=OPEN,CONFIRMED,REOPENED"
                        """,
                        returnStdout: true
                    ).trim()
                    def issuesJson = new groovy.json.JsonSlurper().parseText(issuesResp)
                    def issues = issuesJson?.issues ?: []
                    echo "SonarQube issues 数量: ${issues.size()}"

                    // 2. 获取本次变更的文件列表
                    def changedFiles = []
                    try {
                        def filesStr = sh(
                            script: "git diff --name-only HEAD~1 2>/dev/null || echo ''",
                            returnStdout: true
                        ).trim()
                        changedFiles = filesStr ? filesStr.split('\n').findAll { it } : []
                    } catch (Exception e) {
                        echo "获取变更文件失败（首次提交?）: ${e.message}"
                    }
                    echo "变更文件: ${changedFiles}"

                    // 3. 构建 trigger payload 并写入文件（避免 shell 引号问题）
                    def triggerPayload = groovy.json.JsonOutput.toJson([
                        repo_path    : WORKSPACE,
                        project_key  : 'helloworld',
                        changed_files: changedFiles,
                        issues       : issues,
                        coverage_gap : null
                    ])
                    writeFile file: 'sonarqube-trigger-payload.json', text: triggerPayload

                    // 4. 调用 SonarQube Trigger API
                    def triggerResp = sh(
                        script: """
                            curl -s -X POST ${AI_PLATFORM_URL}/api/sonarqube/trigger \
                                -H 'Content-Type: application/json' \
                                -H 'X-API-Key: jenkins-sonarqube-2026' \
                                --data-binary @sonarqube-trigger-payload.json
                        """,
                        returnStdout: true
                    ).trim()
                    echo "SonarQube Trigger 响应: ${triggerResp}"

                    def triggerJson = new groovy.json.JsonSlurper().parseText(triggerResp)
                    if (triggerJson?.success != true || !triggerJson?.task_id) {
                        error("SonarQube Trigger 失败: ${triggerJson?.error ?: triggerResp}")
                    }
                    def taskId = triggerJson.task_id
                    echo "任务 ID: ${taskId}"

                    // 5. 轮询任务完成
                    def taskStatus = 'running'
                    for (def i = 0; i < 60; i++) {
                        sleep(10)
                        def statusResp = sh(
                            script: """
                                curl -s "${AI_PLATFORM_URL}/api/sonarqube/status/${taskId}" \
                                    -H 'X-API-Key: jenkins-sonarqube-2026'
                            """,
                            returnStdout: true
                        ).trim()
                        def statusJson = new groovy.json.JsonSlurper().parseText(statusResp)
                        taskStatus = statusJson?.data?.status ?: statusJson?.status ?: 'unknown'
                        echo "任务状态: ${taskStatus}"
                        if (taskStatus in ['completed', 'failed', 'error']) {
                            break
                        }
                    }
                    if (taskStatus != 'completed') {
                        error("SonarQube Trigger 任务未完成: ${taskStatus}")
                    }
                    echo '✅ SonarQube Trigger 任务完成'

                    // 6. 获取结果中的 script_ids
                    def resultResp = sh(
                        script: """
                            curl -s "${AI_PLATFORM_URL}/api/sonarqube/result/${taskId}" \
                                -H 'X-API-Key: jenkins-sonarqube-2026'
                        """,
                        returnStdout: true
                    ).trim()
                    def resultJson = new groovy.json.JsonSlurper().parseText(resultResp)
                    def generated = resultJson?.data?.generated_scripts ?: resultJson?.generated_scripts ?: []
                    def scriptIds = generated.collect { it.script_id }.findAll { it }
                    echo "生成脚本数量: ${scriptIds.size()}"

                    // 7. Portal 登录
                    def loginResp = sh(
                        script: """
                            curl -s -X POST ${PORTAL_URL}/api/login \
                                -H 'Content-Type: application/json' \
                                -d '{"username":"${portalUser}","password":"${portalPass}"}'
                        """,
                        returnStdout: true
                    ).trim()
                    def loginJson = new groovy.json.JsonSlurper().parseText(loginResp)
                    if (loginJson?.success != true || !loginJson?.data?.token) {
                        error("Portal 登录失败: ${loginJson?.message ?: loginResp}")
                    }
                    def jwtToken = loginJson.data.token

                    // 8. 复制代码到后端容器
                    sh "docker exec ai_playwright_backend sh -c 'rm -rf ${UNDER_TEST_DIR} && mkdir -p ${UNDER_TEST_DIR}'"
                    def copyStatus = sh(
                        script: "tar -cf - . | docker exec -i ai_playwright_backend tar -xf - -C ${UNDER_TEST_DIR}",
                        returnStatus: true
                    )
                    if (copyStatus != 0) {
                        error("复制代码到 ai_playwright_backend 容器失败")
                    }

                    // 9. 执行每个生成的测试脚本
                    if (scriptIds) {
                        echo "执行 ${scriptIds.size()} 个 SonarQube 生成的测试脚本..."
                        scriptIds.each { sid ->
                            def execResp = sh(
                                script: """
                                    curl -s -X POST ${AI_PLATFORM_URL}/api/pytest/jenkins/execute \
                                        -H 'Content-Type: application/json' \
                                        -H "Authorization: Bearer ${jwtToken}" \
                                        -d '{"script_id":"${sid}","code_dir":"${UNDER_TEST_DIR}","pytest_args":"-v --tb=short --color=no"}'
                                """,
                                returnStdout: true
                            ).trim()
                            def execJson = new groovy.json.JsonSlurper().parseText(execResp)
                            if (execJson?.success != true) {
                                echo "⚠️ 脚本 ${sid} 执行异常: ${execJson?.error ?: execResp}"
                            } else {
                                echo "✅ 脚本 ${sid} 执行完成"
                            }
                        }
                    }

                    // 10. 通用白盒测试覆盖
                    echo "运行白盒测试（通用覆盖）..."
                    def whiteboxResp = sh(
                        script: """
                            curl -s -X POST ${AI_PLATFORM_URL}/api/pytest/whitebox-execute \
                                -H 'Content-Type: application/json' \
                                -H "Authorization: Bearer ${jwtToken}" \
                                -d '{"test_dir":"${UNDER_TEST_DIR}","name":"helloworld_${BUILD_NUMBER}","pytest_args":"-v --tb=short --color=no"}'
                        """,
                        returnStdout: true
                    ).trim()
                    def wbJson = new groovy.json.JsonSlurper().parseText(whiteboxResp)
                    if (wbJson?.success != true) {
                        error("白盒测试失败: ${wbJson?.error ?: whiteboxResp}")
                    }
                    if (wbJson?.status != 'completed') {
                        error("白盒测试未通过: status=${wbJson?.status}")
                    }
                    echo "✅ 全部 AI 测试通过: passed=${wbJson?.passed}"
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
