pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 2, unit: 'HOURS')
    }
    parameters {
        string(name: 'GIT_REPO_URL', defaultValue: '', description: 'Git仓库地址（Webhook触发自动填充）')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: '分支名（Webhook触发自动填充）')
        string(name: 'GIT_COMMIT_ID', defaultValue: '', description: 'Commit ID（Webhook触发自动填充）')
        booleanParam(name: 'SKIP_SONAR', defaultValue: false, description: '跳过SonarQube扫描')
        booleanParam(name: 'SKIP_AI_TEST', defaultValue: false, description: '跳过AI自动测试')
    }
    environment {
        PORTAL_URL      = "http://ai_portal:5003"
        PLAYWRIGHT_URL  = "http://ai_playwright_backend:5000"
        SONAR_HOST_URL  = "http://cicd-sonarqube:9000"
        SONAR_TOKEN     = credentials('sonarqube-token')
        REPORT_DIR      = "${WORKSPACE}/reports"
        UNDER_TEST_DIR  = "/app/under-test"
    }
    triggers {
        GenericTrigger(
            genericVariables: [
                [key: 'GIT_REPO_URL', value: '$.repository.clone_url'],
                [key: 'GIT_BRANCH', value: '$.ref', regexpFilter: 'refs/heads/', replacement: ''],
                [key: 'GIT_COMMIT_ID', value: '$.after']
            ],
            token: 'ai-ci-full-pipeline',
            printContributedVariables: true,
            printPostContent: true,
            causeString: 'Git Push触发: ${GIT_REPO_URL} @ ${GIT_COMMIT_ID}'
        )
    }
    stages {
        stage('0. 初始化') {
            steps {
                script {
                    sh "mkdir -p ${REPORT_DIR}"
                    echo "=== 构建信息 ==="
                    echo "Git仓库 : ${params.GIT_REPO_URL}"
                    echo "分支    : ${params.GIT_BRANCH}"
                    echo "Commit  : ${params.GIT_COMMIT_ID}"
                    echo "跳过Sonar : ${params.SKIP_SONAR}"
                    echo "跳过AI测试: ${params.SKIP_AI_TEST}"
                }
            }
        }

        stage('1. 拉取代码') {
            when { expression { return params.GIT_REPO_URL } }
            steps {
                script {
                    git(
                        url: params.GIT_REPO_URL,
                        branch: params.GIT_BRANCH,
                        credentialsId: ''
                    )
                    sh "mkdir -p ${REPORT_DIR}"
                    sh "git log --oneline -3"
                    sh "git diff HEAD^ HEAD > ${REPORT_DIR}/code_diff.txt 2>/dev/null || echo 'First commit, no diff' > ${REPORT_DIR}/code_diff.txt"
                    echo "代码拉取完成"
                }
            }
        }

        stage('2. SonarQube 扫描') {
            when { expression { return !params.SKIP_SONAR && params.GIT_REPO_URL } }
            steps {
                withSonarQubeEnv('SonarQube') {
                    sh "${tool('sonar-scanner')}/bin/sonar-scanner -Dsonar.projectKey=${JOB_NAME} -Dsonar.sources=."
                }
            }
        }

        stage('3. Quality Gate') {
            when { expression { return !params.SKIP_SONAR && params.GIT_REPO_URL } }
            steps {
                timeout(time: 1, unit: 'HOURS') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('4. AI 白盒测试') {
            when { expression { return !params.SKIP_AI_TEST && params.GIT_REPO_URL } }
            steps {
                script {
                    // 1. 登录 Portal
                    echo "[1/5] 登录 AI 平台..."
                    def loginResp = sh(returnStdout: true, script: """
                        curl -s -X POST ${PORTAL_URL}/api/login \
                        -H 'Content-Type: application/json' \
                        -d '{"username":"admin","password":"Admin@123456"}'
                    """).trim()
                    env.JWT_TOKEN = sh(returnStdout: true, script: """
                        echo '${loginResp}' | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4
                    """).trim()
                    if (!env.JWT_TOKEN) {
                        error "AI平台登录失败: ${loginResp}"
                    }

                    // 2. 复制代码到 Playwright 后端容器
                    echo "[2/5] 复制代码到后端容器..."
                    sh """
                        docker exec ai_playwright_backend sh -c "rm -rf ${UNDER_TEST_DIR} && mkdir -p ${UNDER_TEST_DIR}" || true
                        tar -cf - . | docker exec -i ai_playwright_backend tar -xf - -C ${UNDER_TEST_DIR}
                    """

                    // 3. 调用 generate 生成测试脚本（入库）
                    echo "[3/5] AI 生成 pytest 脚本..."
                    def genPayload = groovy.json.JsonOutput.toJson([
                        code_dir: UNDER_TEST_DIR,
                        name: "helloworld_${BUILD_NUMBER}"
                    ])
                    def genResp = sh(returnStdout: true, script: """
                        curl -s -X POST ${PLAYWRIGHT_URL}/api/pytest/jenkins/generate \
                        -H 'Content-Type: application/json' \
                        -H "Authorization: Bearer ${JWT_TOKEN}" \
                        --max-time 300 \
                        -d '${genPayload}'
                    """).trim()
                    echo "  generate: ${genResp}"

                    def genJson = readJSON text: genResp
                    def scriptId = genJson.script_id ?: ''
                    if (!scriptId) {
                        error "AI 生成测试脚本失败: ${genResp}"
                    }
                    echo "  script_id: ${scriptId}"

                    // 4. 调用 execute 执行测试（入库）
                    echo "[4/5] 执行 pytest..."
                    def execPayload = groovy.json.JsonOutput.toJson([
                        script_id: scriptId,
                        code_dir: UNDER_TEST_DIR,
                        pytest_args: "-v --tb=short --color=no"
                    ])
                    def execResp = sh(returnStdout: true, script: """
                        curl -s -X POST ${PLAYWRIGHT_URL}/api/pytest/jenkins/execute \
                        -H 'Content-Type: application/json' \
                        -H "Authorization: Bearer ${JWT_TOKEN}" \
                        --max-time 900 \
                        -d '${execPayload}'
                    """).trim()
                    echo "  execute: ${execResp}"

                    // 5. 解析结果 + 构建报告
                    def result = readJSON text: execResp
                    def passed  = result.passed  ?: 0
                    def failed  = result.failed  ?: 0
                    def errors  = result.errors  ?: 0
                    def status  = result.status  ?: 'error'
                    def elapsed = result.elapsed ?: 0

                    env.AI_TEST_SUCCESS = (status == 'completed') ? 'true' : 'false'
                    env.AI_TOTAL_PASSED = passed
                    env.AI_TOTAL_FAILED = failed

                    def statusIcon = (status == 'completed') ? 'PASS' : 'FAIL'
                    def reportHtml = """
<html><head><meta charset='utf-8'><title>CI 白盒测试报告</title>
<style>body{font-family:monospace;margin:20px}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:8px;text-align:left}th{background:#eee}
.pass{color:#2e7d32}.fail{color:#c62828}</style></head><body>
<h1>AI CI 白盒测试报告</h1>
<p>项目: helloworld | 构建: #${BUILD_NUMBER} | script_id: ${scriptId}</p>
<p>状态: ${statusIcon} | 通过: ${passed} | 失败: ${failed} | 错误: ${errors} | 耗时: ${elapsed}s</p>
<pre>${result.summary ?: result.stdout ?: ''}</pre>
<hr><p>脚本已入库，可在 Playwright 前端查看 | SonarQube + AI + Pytest</p></body></html>"""
                    writeFile file: "${REPORT_DIR}/pytest_report.html", text: reportHtml
                    writeFile file: "${REPORT_DIR}/pytest_result.json", text: execResp

                    echo "=== AI测试完成: 通过${passed} 失败${failed} 错误${errors} ==="
                    if (status != 'completed') {
                        error "AI白盒测试未通过: ${status}"
                    }
                }
            }
        }
    }
    post {
        always {
            publishHTML(
                target: [
                    allowMissing: true,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: 'reports',
                    reportFiles: 'pytest_report.html, code_diff.txt',
                    reportName: 'CI 构建报告'
                ]
            )
            deleteDir()
        }
        success {
            echo "=== 全链路CI流程执行成功 ==="
            echo "Sonar报告: ${SONAR_HOST_URL}/dashboard?id=${JOB_NAME}"
        }
        failure {
            echo "=== 全链路CI流程执行失败 ==="
        }
    }
}
