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

# 克隆远程仓库
function Clone-Repository {
    if (-not $RepoUrl) {
        Write-Info "跳过克隆步骤，使用本地目录"
        return
    }
    
    Write-Info "正在从 $RepoUrl 克隆仓库到 $ProjectDir..."
    
    if (Test-Path $ProjectDir) {
        Write-Warning "目标目录 $ProjectDir 已存在，正在备份..."
        $backupName = "${ProjectDir}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Move-Item $ProjectDir $backupName
    }
    
    git clone -b $Branch $RepoUrl $ProjectDir
    
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorCustom "克隆仓库失败"
        exit 1
    }
    
    Write-Success "仓库克隆成功"
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
    Clone-Repository
    Prepare-DeploymentDir
    Start-Services
    Show-PostDeploymentInfo
    
    Write-Success "部署流程完成！"
}

# 执行主函数
Main