# PowerShell 自动化部署脚本
# 支持从远程仓库或本地目录部署股票应用

param(
    [string]$RepoUrl = "https://github.com/KevinZjYang/stock",
    [string]$Branch = "main",
    [string]$ProjectDir = "stock-app",
    [string]$ComposeFile = "docker-compose.yml",
    [switch]$Help
)

if ($Help) {
    Write-Host "用法: deploy.ps1 [参数]"
    Write-Host ""
    Write-Host "参数:"
    Write-Host "  -RepoUrl URL           指定远程Git仓库URL（可选，不指定则使用本地）"
    Write-Host "  -Branch BRANCH         指定Git分支（默认: main）"
    Write-Host "  -ProjectDir DIR        指定项目目录（默认: stock-app）"
    Write-Host "  -ComposeFile FILE      指定Docker Compose文件（默认: docker-compose.yml）"
    Write-Host "  -Help                  显示此帮助信息"
    Write-Host ""
    Write-Host "示例:"
    Write-Host "  deploy.ps1                                    # 从本地目录部署"
    Write-Host "  deploy.ps1 -RepoUrl https://github.com/user/repo   # 从远程仓库部署"
    Write-Host "  deploy.ps1 -RepoUrl https://github.com/user/repo -Branch develop  # 从develop分支部署"
    exit 0
}

# 颜色定义
$InfoColor = "Blue"
$SuccessColor = "Green"
$WarningColor = "Yellow"
$ErrorColor = "Red"

# 打印带颜色的信息
function Write-Info($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor $InfoColor
}

function Write-Success($Message) {
    Write-Host "[SUCCESS] $Message" -ForegroundColor $SuccessColor
}

function Write-Warning($Message) {
    Write-Host "[WARNING] $Message" -ForegroundColor $WarningColor
}

function Write-ErrorCustom($Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor $ErrorColor
}

# 检查必要工具
function Check-Prerequisites {
    Write-Info "检查必要工具..."
    
    $dockerInstalled = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerInstalled) {
        Write-ErrorCustom "Docker 未安装，请先安装 Docker Desktop"
        exit 1
    }
    
    $dockerComposeInstalled = Get-Command docker-compose -ErrorAction SilentlyContinue
    if (-not $dockerComposeInstalled) {
        Write-ErrorCustom "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    }
    
    if ($RepoUrl -and (-not (Get-Command git -ErrorAction SilentlyContinue))) {
        Write-ErrorCustom "Git 未安装，无法从远程仓库克隆代码"
        exit 1
    }
    
    Write-Success "所有必要工具都已安装"
}

# 克隆远程仓库或准备本地目录
function Prepare-SourceCode {
    # 检查目标目录是否存在以及是否包含data目录
    $dataBackupPath = $null
    if (Test-Path $ProjectDir) {
        $dataPath = Join-Path $ProjectDir "data"
        if (Test-Path $dataPath) {
            # 备份data目录
            $dataBackupPath = Join-Path $ProjectDir "data_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Copy-Item $dataPath $dataBackupPath -Recurse -Force
            Write-Info "已备份data目录到 $dataBackupPath"
        }
    }

    if (-not $RepoUrl) {
        Write-Info "使用本地目录作为源代码"

        # 检查当前目录是否为项目根目录（包含docker-compose.yml等关键文件）
        $requiredFiles = @("docker-compose.yml", "Dockerfile", "app.py")
        $missingFiles = @()
        foreach ($file in $requiredFiles) {
            if (-not (Test-Path $file)) {
                $missingFiles += $file
            }
        }

        if ($missingFiles.Count -gt 0) {
            Write-Warning "当前目录缺少以下关键文件: $($missingFiles -join ', ')"
            Write-Info "将创建新的项目目录结构"

            # 如果ProjectDir已存在，备份它（除了data目录）
            if (Test-Path $ProjectDir) {
                Write-Warning "目标目录 $ProjectDir 已存在，正在备份（保留data目录）..."
                $backupName = "${ProjectDir}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

                # 移动除data目录外的所有内容到备份目录
                $backupDir = New-Item -ItemType Directory -Path $backupName -Force
                Get-ChildItem -Path $ProjectDir | Where-Object { $_.Name -ne "data" } | ForEach-Object {
                    Move-Item $_.FullName (Join-Path $backupDir $_.Name) -Force
                }
                Write-Success "已备份到 $backupName （data目录除外）"
            }

            # 创建新目录
            New-Item -ItemType Directory -Path $ProjectDir -Force | Out-Null

            # 复制当前目录的所有内容到新目录（除了data目录）
            Get-ChildItem -Path "." | Where-Object { $_.Name -ne "data" -and $_.Name -ne $ProjectDir } | ForEach-Object {
                Copy-Item $_.FullName -Destination $ProjectDir -Recurse -Force
            }

            # 恢复data目录内容 - 只恢复数据库文件
            if ($dataBackupPath -and (Test-Path $dataBackupPath)) {
                $newDataPath = Join-Path $ProjectDir "data"
                # 确保新的data目录存在
                if (!(Test-Path $newDataPath)) {
                    New-Item -ItemType Directory -Path $newDataPath -Force | Out-Null
                }

                # 只恢复数据库文件，避免覆盖新版本的其他文件
                $dbBackupPath = Join-Path $dataBackupPath "stock_fund.db"
                if (Test-Path $dbBackupPath) {
                    Copy-Item $dbBackupPath (Join-Path $newDataPath "stock_fund.db") -Force
                    Write-Info "已恢复数据库文件"
                }

                # 删除备份的data目录
                Remove-Item $dataBackupPath -Force -Recurse
                Write-Info "已恢复data目录内容"
            }

            # 切换到项目目录
            Set-Location $ProjectDir
        } else {
            Write-Info "检测到当前目录包含项目文件，将使用当前目录作为部署源"
        }

        return
    }

    # 从远程下载ZIP包而非使用Git
    Write-Info "正在从 $RepoUrl 下载最新版本..."

    # 创建临时目录用于下载
    $tempDir = Join-Path $env:TEMP "stock_temp_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    try {
        # 构造下载URL（GitHub ZIP下载链接）
        # 使用镜像地址以提高在中国大陆的访问速度
        if ($RepoUrl -match "^https?://github\.com/([^/]+)/([^/]+)(\.git)?$") {
            $userName = $matches[1]
            $repoName = $matches[2]
            # 使用镜像地址
            $downloadUrl = "https://gh.yiun.cyou/https://github.com/$userName/$repoName/archive/refs/heads/main.zip"
        } else {
            # 如果URL格式不符合预期，使用原始方式
            $downloadUrl = $RepoUrl.Replace("github.com", "api.github.com/repos") + "/zipball/main"
            # 同样使用镜像地址
            $downloadUrl = "https://gh.yiun.cyou/$downloadUrl"
        }

        # 下载ZIP文件
        $zipPath = Join-Path $tempDir "latest_version.zip"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing

        # 解压ZIP文件
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $tempDir)

        # 找到解压后的目录（GitHub ZIP通常包含一个带仓库名的根目录）
        $extractedDir = Get-ChildItem -Path $tempDir | Where-Object { $_.PSIsContainer } | Select-Object -First 1

        if ($null -eq $extractedDir) {
            Write-ErrorCustom "未能找到解压后的项目目录"
            return
        }

        # 如果目标目录存在，备份它（除了data目录）
        if (Test-Path $ProjectDir) {
            Write-Warning "目标目录 $ProjectDir 已存在，正在备份（保留data目录）..."
            $backupName = "${ProjectDir}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

            # 创建备份目录
            $backupDir = New-Item -ItemType Directory -Path $backupName -Force

            # 移动除data目录外的所有内容到备份目录
            Get-ChildItem -Path $ProjectDir | Where-Object { $_.Name -ne "data" } | ForEach-Object {
                Move-Item $_.FullName (Join-Path $backupDir $_.Name) -Force
            }

            Write-Success "已备份到 $backupName （data目录除外）"
        }

        # 将解压的目录内容移动到目标目录
        if (Test-Path $ProjectDir) {
            # 如果目标目录已存在（此时只包含data目录），将解压目录的内容复制进去
            Get-ChildItem -Path $extractedDir.FullName | ForEach-Object {
                $destinationPath = Join-Path $ProjectDir $_.Name
                if ($_.Name -ne "data") {  # 避免与已存在的data目录冲突
                    if (Test-Path $destinationPath) {
                        # 如果目标位置已存在，先删除再移动
                        if ($_.PSIsContainer) {
                            Remove-Item $destinationPath -Recurse -Force
                        } else {
                            Remove-Item $destinationPath -Force
                        }
                    }
                    Move-Item $_.FullName $destinationPath -Force
                }
            }
        } else {
            # 如果目标目录不存在，重命名解压目录
            Move-Item $extractedDir.FullName $ProjectDir -Force
        }

        # 恢复data目录内容 - 只恢复数据库文件
        if ($dataBackupPath -and (Test-Path $dataBackupPath)) {
            $newDataPath = Join-Path $ProjectDir "data"
            # 确保新的data目录存在
            if (!(Test-Path $newDataPath)) {
                New-Item -ItemType Directory -Path $newDataPath -Force | Out-Null
            }

            # 只恢复数据库文件，避免覆盖新版本的其他文件
            $dbBackupPath = Join-Path $dataBackupPath "stock_fund.db"
            if (Test-Path $dbBackupPath) {
                Copy-Item $dbBackupPath (Join-Path $newDataPath "stock_fund.db") -Force
                Write-Info "已恢复数据库文件"
            }

            # 删除备份的data目录
            Remove-Item $dataBackupPath -Force -Recurse
            Write-Info "已恢复data目录内容"
        }

        Write-Success "代码下载和覆盖成功"
    }
    catch {
        Write-ErrorCustom "下载或解压失败: $($_.Exception.Message)"
        throw
    }
    finally {
        # 清理临时目录
        if (Test-Path $tempDir) {
            Remove-Item $tempDir -Recurse -Force
        }
    }
}

# 准备部署目录
function Prepare-DeploymentDir {
    if ($RepoUrl) {
        Set-Location $ProjectDir
    }
    
    Write-Info "正在准备部署目录..."
    
    # 确保必要的目录存在
    if (!(Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
    if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" | Out-Null }
    if (!(Test-Path "templates")) { New-Item -ItemType Directory -Path "templates" | Out-Null }
    
    # 如果存在自定义的 compose 文件，则复制到当前目录
    if (($ComposeFile -ne "docker-compose.yml") -and (Test-Path $ComposeFile)) {
        Copy-Item $ComposeFile "docker-compose.yml"
    }
    elseif (!(Test-Path "docker-compose.yml")) {
        Write-ErrorCustom "找不到 docker-compose.yml 文件"
        exit 1
    }
    
    # 检查是否有 .env 文件，如果没有则创建示例
    if ((!(Test-Path ".env")) -and (Test-Path ".env.example")) {
        Write-Info "创建 .env 文件..."
        Copy-Item ".env.example" ".env"
        Write-Warning "请检查 .env 文件并根据需要进行配置"
    }
    
    Write-Success "部署目录准备完成"
}

# 构建并启动服务
function Start-Services {
    Write-Info "正在构建并启动服务..."
    
    # 停止现有服务（如果存在）
    $existingServices = docker-compose ps --quiet
    if ($existingServices) {
        Write-Info "停止现有服务..."
        docker-compose down
    }
    
    # 构建并启动服务
    docker-compose up -d --build
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务启动成功！"
        Write-Host ""
        Write-Host "应用正在运行在 http://localhost:3333" -ForegroundColor $SuccessColor
        Write-Host ""
        Write-Info "服务状态："
        docker-compose ps
    }
    else {
        Write-ErrorCustom "服务启动失败"
        exit 1
    }
}

# 显示部署后信息
function Show-PostDeploymentInfo {
    Write-Host ""
    Write-Host "================================" -ForegroundColor $SuccessColor
    Write-Host "部署完成！" -ForegroundColor $SuccessColor
    Write-Host "================================" -ForegroundColor $SuccessColor
    Write-Host ""
    Write-Host "应用访问地址: http://localhost:3333"
    Write-Host "数据目录: $(Get-Location)\data"
    Write-Host "日志目录: $(Get-Location)\logs"
    Write-Host ""
    Write-Host "常用命令："
    Write-Host "  查看服务状态: docker-compose ps"
    Write-Host "  查看服务日志: docker-compose logs -f"
    Write-Host "  停止服务: docker-compose down"
    Write-Host "  重启服务: docker-compose restart"
    Write-Host ""
}

# 主函数
function Main {
    Write-Info "开始自动化部署..."
    Write-Info "时间: $(Get-Date)"
    Write-Host ""

    Check-Prerequisites
    Prepare-SourceCode
    Prepare-DeploymentDir
    Start-Services
    Show-PostDeploymentInfo

    Write-Success "部署流程完成！"
}

# 执行主函数
Main