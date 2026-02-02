#!/bin/bash

# 自动化部署脚本
# 支持从远程仓库部署股票应用

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认值
REPO_URL="https://github.com/KevinZjYang/stock"
BRANCH="main"
PROJECT_DIR="stock-app"
COMPOSE_FILE="docker-compose.yml"

# 打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查必要工具
check_prerequisites() {
    print_info "检查必要工具..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    # 检查 docker compose (新版本) 或 docker-compose (旧版本)
    DOCKER_COMPOSE_AVAILABLE=false

    # 检查经典 docker-compose 命令
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_AVAILABLE=true
    fi

    # 检查集成的 docker compose 命令
    if docker --help | grep -q "compose" 2>/dev/null; then
        DOCKER_COMPOSE_AVAILABLE=true
    fi

    if [ "$DOCKER_COMPOSE_AVAILABLE" = false ]; then
        print_error "Docker Compose 未安装，请先安装 Docker Compose"
        print_info "提示: 新版本的 Docker 已将 compose 集成到 docker 命令中"
        exit 1
    fi

    if [[ -n "$REPO_URL" ]] && ! command -v git &> /dev/null; then
        print_error "Git 未安装，无法从远程仓库克隆代码"
        exit 1
    fi

    print_success "所有必要工具都已安装"
}

# 克隆远程仓库或准备本地目录
prepare_source_code() {
    # 检查目标目录是否存在以及是否包含data目录
    DATA_BACKUP_PATH=""
    if [[ -d "$PROJECT_DIR" && -d "$PROJECT_DIR/data" ]]; then
        # 备份data目录
        DATA_BACKUP_PATH="$PROJECT_DIR/data_backup_$(date +%Y%m%d_%H%M%S)"
        cp -r "$PROJECT_DIR/data" "$DATA_BACKUP_PATH"
        print_info "已备份data目录到 $DATA_BACKUP_PATH"
    fi

    if [[ -z "$REPO_URL" ]]; then
        print_info "使用本地目录作为源代码"

        # 检查当前目录是否为项目根目录（包含docker-compose.yml等关键文件）
        local required_files=("docker-compose.yml" "Dockerfile" "app.py")
        local missing_files=()

        for file in "${required_files[@]}"; do
            if [[ ! -f "$file" ]]; then
                missing_files+=("$file")
            fi
        done

        if [[ ${#missing_files[@]} -gt 0 ]]; then
            print_warning "当前目录缺少以下关键文件: ${missing_files[*]}"
            print_info "将创建新的项目目录结构"

            # 如果ProjectDir已存在，备份它（除了data目录）
            if [[ -d "$PROJECT_DIR" ]]; then
                print_warning "目标目录 $PROJECT_DIR 已存在，正在备份（保留data目录）..."
                local backup_name="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"

                # 创建备份目录
                mkdir -p "$backup_name"

                # 移动除data目录外的所有内容到备份目录
                for item in "$PROJECT_DIR"/*; do
                    if [[ "$(basename "$item")" != "data" ]]; then
                        mv "$item" "$backup_name/"
                    fi
                done

                # 同时移动隐藏文件（除了.和..）
                for item in "$PROJECT_DIR"/.*; do
                    if [[ -e "$item" && "$(basename "$item")" != "." && "$(basename "$item")" != ".." && "$(basename "$item")" != "data" ]]; then
                        mv "$item" "$backup_name/"
                    fi
                done

                print_success "已备份到 $backup_name （data目录除外）"
            fi

            # 创建新目录
            mkdir -p "$PROJECT_DIR"

            # 复制当前目录的所有内容到新目录（除了data目录和目标项目目录）
            for item in *; do
                if [[ "$item" != "data" && "$item" != "$PROJECT_DIR" ]]; then
                    cp -r "$item" "$PROJECT_DIR/"
                fi
            done

            # 恢复data目录内容 - 只恢复数据库文件
            if [[ -n "$DATA_BACKUP_PATH" && -d "$DATA_BACKUP_PATH" ]]; then
                NEW_DATA_PATH="$PROJECT_DIR/data"
                # 确保新的data目录存在
                mkdir -p "$NEW_DATA_PATH"

                # 只恢复数据库文件，避免覆盖新版本的其他文件
                DB_BACKUP_PATH="$DATA_BACKUP_PATH/stock_fund.db"
                if [[ -f "$DB_BACKUP_PATH" ]]; then
                    cp "$DB_BACKUP_PATH" "$NEW_DATA_PATH/stock_fund.db"
                    print_info "已恢复数据库文件"
                fi

                # 删除备份的data目录
                rm -rf "$DATA_BACKUP_PATH"
                print_info "已恢复data目录内容"
            fi

            # 切换到项目目录
            cd "$PROJECT_DIR"
        else
            print_info "检测到当前目录包含项目文件，将使用当前目录作为部署源"
        fi

        return
    fi

    print_info "正在从 $REPO_URL 下载最新版本..."

    if [[ -d "$PROJECT_DIR" ]]; then
        print_warning "目标目录 $PROJECT_DIR 已存在，正在备份（保留data目录）..."
        local backup_name="${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"

        # 创建备份目录
        mkdir -p "$backup_name"

        # 移动除data目录外的所有内容到备份目录
        for item in "$PROJECT_DIR"/*; do
            if [[ "$(basename "$item")" != "data" ]]; then
                mv "$item" "$backup_name/"
            fi
        done

        # 同时移动隐藏文件（除了.和..）
        for item in "$PROJECT_DIR"/.*; do
            if [[ -e "$item" && "$(basename "$item")" != "." && "$(basename "$item")" != ".." && "$(basename "$item")" != "data" ]]; then
                mv "$item" "$backup_name/"
            fi
        done

        print_success "已备份到 $backup_name （data目录除外）"
    fi

    print_info "正在从 $REPO_URL 下载最新版本..."

    # 创建临时目录用于下载
    TEMP_DIR="/tmp/stock_temp_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$TEMP_DIR"

    # 构造下载URL（GitHub ZIP下载链接）
    # 使用镜像地址以提高在中国大陆的访问速度
    if [[ "$REPO_URL" =~ ^https?://github\.com/([^/]+)/([^/]+)(\.git)?$ ]]; then
        USER_NAME="${BASH_REMATCH[1]}"
        REPO_NAME="${BASH_REMATCH[2]}"
        # 使用镜像地址
        DOWNLOAD_URL="https://gh.yiun.cyou/https://github.com/$USER_NAME/$REPO_NAME/archive/refs/heads/main.zip"
    else
        # 如果URL格式不符合预期，使用原始方式
        DOWNLOAD_URL=$(echo "$REPO_URL" | sed 's/github.com/api.github.com\/repos/g')"/zipball/main"
        # 同样使用镜像地址
        DOWNLOAD_URL="https://gh.yiun.cyou/$DOWNLOAD_URL"
    fi

    # 下载ZIP文件
    ZIP_PATH="$TEMP_DIR/latest_version.zip"
    if command -v curl &> /dev/null; then
        curl -L -o "$ZIP_PATH" "$DOWNLOAD_URL"
    elif command -v wget &> /dev/null; then
        wget -O "$ZIP_PATH" "$DOWNLOAD_URL"
    else
        print_error "curl 或 wget 未安装，无法下载更新"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    if [[ $? -ne 0 ]]; then
        print_error "下载失败"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    # 解压ZIP文件
    unzip -q "$ZIP_PATH" -d "$TEMP_DIR"

    # 找到解压后的目录（GitHub ZIP通常包含一个带仓库名的根目录）
    EXTRACTED_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

    if [[ -z "$EXTRACTED_DIR" ]]; then
        print_error "未能找到解压后的项目目录"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    # 将解压的目录内容移动到目标目录
    if [[ -d "$PROJECT_DIR" ]]; then
        # 如果目标目录已存在（此时只包含data目录），将解压目录的内容复制进去
        for item in "$EXTRACTED_DIR"/*; do
            if [[ -n "$item" ]]; then
                item_name=$(basename "$item")
                destination_path="$PROJECT_DIR/$item_name"

                # 避免与已存在的data目录冲突
                if [[ "$item_name" != "data" ]]; then
                    if [[ -e "$destination_path" ]]; then
                        # 如果目标位置已存在，先删除再移动
                        if [[ -d "$destination_path" ]]; then
                            rm -rf "$destination_path"
                        else
                            rm -f "$destination_path"
                        fi
                    fi
                    mv "$item" "$destination_path"
                fi
            fi
        done
    else
        # 如果目标目录不存在，先创建目录，再移动解压目录内容
        mkdir -p "$PROJECT_DIR"

        # 检查源目录内容并移动
        for item in "$EXTRACTED_DIR"/*; do
            if [[ -e "$item" ]]; then
                mv "$item" "$PROJECT_DIR"/
            fi
        done

        # 同时处理隐藏文件（如 .env.example, .gitignore 等）
        for item in "$EXTRACTED_DIR"/.*; do
            if [[ -e "$item" && "$(basename "$item")" != "." && "$(basename "$item")" != ".." ]]; then
                mv "$item" "$PROJECT_DIR"/
            fi
        done
    fi

    # 恢复data目录内容 - 只恢复数据库文件
    if [[ -n "$DATA_BACKUP_PATH" && -d "$DATA_BACKUP_PATH" ]]; then
        NEW_DATA_PATH="$PROJECT_DIR/data"
        # 确保新的data目录存在
        mkdir -p "$NEW_DATA_PATH"

        # 只恢复数据库文件，避免覆盖新版本的其他文件
        DB_BACKUP_PATH="$DATA_BACKUP_PATH/stock_fund.db"
        if [[ -f "$DB_BACKUP_PATH" ]]; then
            cp "$DB_BACKUP_PATH" "$NEW_DATA_PATH/stock_fund.db"
            print_info "已恢复数据库文件"
        fi

        # 删除备份的data目录
        rm -rf "$DATA_BACKUP_PATH"
        print_info "已恢复data目录内容"
    fi

    # 清理临时目录
    rm -rf "$TEMP_DIR"

    print_success "代码下载和覆盖成功"
}

# 准备部署目录
prepare_deployment_dir() {
    if [[ -n "$REPO_URL" ]]; then
        cd "$PROJECT_DIR"
    fi

    print_info "正在准备部署目录..."

    # 确保必要的目录存在
    mkdir -p data logs templates

    # 如果存在自定义的 compose 文件，则复制到当前目录
    if [[ "$COMPOSE_FILE" != "docker-compose.yml" ]] && [[ -f "$COMPOSE_FILE" ]]; then
        cp "$COMPOSE_FILE" docker-compose.yml
    elif [[ ! -f "docker-compose.yml" ]]; then
        print_error "找不到 docker-compose.yml 文件"
        exit 1
    fi

    # 检查是否有 .env 文件，如果没有则创建示例
    if [[ ! -f ".env" ]] && [[ -f ".env.example" ]]; then
        print_info "创建 .env 文件..."
        cp .env.example .env
        print_warning "请检查 .env 文件并根据需要进行配置"
    fi

    print_success "部署目录准备完成"
}

# 检测并确定使用的 docker compose 命令
detect_docker_compose_cmd() {
    if command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    elif docker --help | grep -q "compose"; then
        echo "docker compose"
    else
        print_error "Docker Compose 未安装"
        exit 1
    fi
}

# 构建并启动服务
start_services() {
    # 检测 docker compose 命令
    DOCKER_COMPOSE_CMD=$(detect_docker_compose_cmd)
    print_info "使用命令: $DOCKER_COMPOSE_CMD"

    print_info "正在构建并启动服务..."

    # 停止现有服务（如果存在）
    if eval "$DOCKER_COMPOSE_CMD ps" &> /dev/null; then
        print_info "停止现有服务..."
        eval "$DOCKER_COMPOSE_CMD down"
    fi

    # 构建并启动服务
    eval "$DOCKER_COMPOSE_CMD up -d --build"

    if [[ $? -eq 0 ]]; then
        print_success "服务启动成功！"
        echo ""
        echo -e "${GREEN}应用正在运行在 http://localhost:3333${NC}"
        echo ""
        print_info "服务状态："
        eval "$DOCKER_COMPOSE_CMD ps"
    else
        print_error "服务启动失败"
        exit 1
    fi
}

# 显示部署后信息
show_post_deployment_info() {
    # 检测 docker compose 命令
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker --help | grep -q "compose"; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"  # 默认值
    fi

    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}部署完成！${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo "应用访问地址: http://localhost:3333"
    echo "数据目录: $(pwd)/data"
    echo "日志目录: $(pwd)/logs"
    echo ""
    echo "常用命令："
    echo "  查看服务状态: $COMPOSE_CMD ps"
    echo "  查看服务日志: $COMPOSE_CMD logs -f"
    echo "  停止服务: $COMPOSE_CMD down"
    echo "  重启服务: $COMPOSE_CMD restart"
    echo ""
}

# 主函数
main() {
    print_info "开始自动化部署..."
    print_info "时间: $(date)"
    echo ""

    check_prerequisites
    prepare_source_code
    prepare_deployment_dir
    start_services
    show_post_deployment_info

    print_success "部署流程完成！"
}

# 执行主函数
main "$@"