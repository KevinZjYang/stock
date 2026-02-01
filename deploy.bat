@echo off
setlocal enabledelayedexpansion

REM 自动化部署批处理脚本
REM 支持从远程仓库或本地目录部署股票应用

echo 开始自动化部署...
echo 时间: %date% %time%
echo.

REM 检查必要工具
echo 正在检查必要工具...

docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker 未安装，请先安装 Docker Desktop
    exit /b 1
)

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Compose 未安装，请先安装 Docker Compose
    exit /b 1
)

echo [SUCCESS] 所有必要工具都已安装
echo.

REM 设置默认值
set "REPO_URL=https://github.com/KevinZjYang/stock"
set "BRANCH=main"
set "PROJECT_DIR=stock-app"
set "COMPOSE_FILE=docker-compose.yml"

REM 解析命令行参数
:parse_args
if "%~1"=="" goto :continue_parse
if "%~1"=="--repo" (
    set "REPO_URL=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--branch" (
    set "BRANCH=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--dir" (
    set "PROJECT_DIR=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--compose" (
    set "COMPOSE_FILE=%~2"
    shift
    shift
    goto :parse_args
)
shift
goto :parse_args

:continue_parse

REM 克隆远程仓库（如果指定了仓库URL）
if "%REPO_URL%"=="" (
    echo [INFO] 跳过克隆步骤，使用本地目录
) else (
    echo [INFO] 正在从 %REPO_URL% 克隆仓库到 %PROJECT_DIR%...
    
    if exist "%PROJECT_DIR%" (
        echo [WARNING] 目标目录 %PROJECT_DIR% 已存在，正在备份...
        ren "%PROJECT_DIR%" "%PROJECT_DIR%_backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    )
    
    git clone -b %BRANCH% %REPO_URL% %PROJECT_DIR%
    if errorlevel 1 (
        echo [ERROR] 克隆仓库失败
        exit /b 1
    )
    
    echo [SUCCESS] 仓库克隆成功
    cd %PROJECT_DIR%
)

REM 准备部署目录
echo [INFO] 正在准备部署目录...

if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "templates" mkdir templates

REM 如果存在自定义的 compose 文件，则复制到当前目录
if not "%COMPOSE_FILE%"=="docker-compose.yml" (
    if exist "%COMPOSE_FILE%" (
        copy "%COMPOSE_FILE%" "docker-compose.yml"
    )
) else (
    if not exist "docker-compose.yml" (
        echo [ERROR] 找不到 docker-compose.yml 文件
        exit /b 1
    )
)

REM 检查是否有 .env 文件，如果没有则创建示例
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] 创建 .env 文件...
        copy ".env.example" ".env"
        echo [WARNING] 请检查 .env 文件并根据需要进行配置
    )
)

echo [SUCCESS] 部署目录准备完成
echo.

REM 构建并启动服务
echo [INFO] 正在构建并启动服务...

REM 停止现有服务（如果存在）
docker-compose ps >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 停止现有服务...
    docker-compose down
)

REM 构建并启动服务
docker-compose up -d --build

if errorlevel 0 (
    echo.
    echo [SUCCESS] 服务启动成功！
    echo.
    echo 应用正在运行在 http://localhost:3333
    echo.
    echo [INFO] 服务状态：
    docker-compose ps
) else (
    echo [ERROR] 服务启动失败
    exit /b 1
)

echo.
echo =================================
echo 部署完成！
echo =================================
echo.
echo 应用访问地址: http://localhost:3333
echo 数据目录: %cd%\data
echo 日志目录: %cd%\logs
echo.
echo 常用命令：
echo   查看服务状态: docker-compose ps
echo   查看服务日志: docker-compose logs -f
echo   停止服务: docker-compose down
echo   重启服务: docker-compose restart
echo.
echo [SUCCESS] 部署流程完成！