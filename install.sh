#!/usr/bin/env bash
# install.sh — DIKW Memory Plugin 一键安装
# 用法: curl -fsSL <raw-url> | bash
# 或:   bash install.sh
set -euo pipefail

REPO="Zhao961215/dikw-memory-plugin"
PLUGIN_NAME="dikw"
BUNDLED_DIR="${HERMES_HOME:-$HOME/.hermes}/hermes-agent/plugins/memory/$PLUGIN_NAME"
HERMES_BIN="${HERMES_HOME:-$HOME/.hermes}/hermes-agent/venv/bin/hermes"
ENV_FILE="$HOME/.hermes/.env"

RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  DIKW Memory Plugin — 一键安装      ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 检查 hermes ──────────────────────────────────
echo -e "${YELLOW}[1/4]${NC} 检查 Hermes Agent..."
if command -v hermes &>/dev/null; then
    HERMES_CMD="hermes"
elif [ -x "$HERMES_BIN" ]; then
    HERMES_CMD="$HERMES_BIN"
else
    echo -e "${RED}✗ Hermes Agent 未安装${NC}"
    echo "  请先安装: https://github.com/nousresearch/hermes-agent"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} hermes: $($HERMES_CMD --version 2>/dev/null | head -1)"

# ── 处理 bundled DIKW 冲突 ────────────────────────
echo -e "${YELLOW}[2/4]${NC} 检查已有 DIKW 安装..."
if [ -d "$BUNDLED_DIR" ]; then
    BACKUP="/tmp/dikw_bundled_backup_$(date +%Y%m%d_%H%M%S)"
    echo -e "  ${YELLOW}⚠${NC} 发现 bundled DIKW，备份到 $BACKUP"
    cp -r "$BUNDLED_DIR" "$BACKUP"
    rm -rf "$BUNDLED_DIR"
    echo -e "  ${GREEN}✓${NC} bundled DIKW 已移除（备份: $BACKUP）"
else
    echo -e "  ${GREEN}✓${NC} 无 bundled DIKW 冲突"
fi

# 检查 user-installed 是否已存在
if $HERMES_CMD plugins list 2>/dev/null | grep -q "$PLUGIN_NAME"; then
    echo -e "  ${YELLOW}⚠${NC} 已安装，先移除旧版本..."
    $HERMES_CMD plugins remove "$PLUGIN_NAME" 2>/dev/null || true
fi

# ── 安装插件 ──────────────────────────────────────
echo -e "${YELLOW}[3/4]${NC} 从 GitHub 安装..."
$HERMES_CMD plugins install "$REPO" --enable
echo -e "  ${GREEN}✓${NC} 插件已安装"

# ── 配置 .env ─────────────────────────────────────
echo -e "${YELLOW}[4/4]${NC} 配置环境变量..."
if [ -f "$ENV_FILE" ]; then
    if grep -q "HERMES_MEMORY_PROVIDER=" "$ENV_FILE"; then
        sed -i.bak "s/^HERMES_MEMORY_PROVIDER=.*/HERMES_MEMORY_PROVIDER=dikw/" "$ENV_FILE"
    else
        echo "" >> "$ENV_FILE"
        echo "# DIKW Memory Plugin" >> "$ENV_FILE"
        echo "HERMES_MEMORY_PROVIDER=dikw" >> "$ENV_FILE"
    fi
else
    mkdir -p "$(dirname "$ENV_FILE")"
    echo "HERMES_MEMORY_PROVIDER=dikw" > "$ENV_FILE"
fi
echo -e "  ${GREEN}✓${NC} .env 已配置"

# ── 完成 ──────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}✅ 安装完成！${NC}"
echo ""
echo -e "  ${BOLD}重启 Gateway 使配置生效:${NC}"
echo -e "    hermes gateway restart"
echo ""
echo -e "  ${BOLD}验证安装:${NC}"
echo -e "    hermes plugins list | grep dikw"
echo -e "    hermes memory status"
echo ""
echo -e "  ${BOLD}回滚（如需要）:${NC}"
echo -e "    hermes plugins remove dikw"
if [ -d "${BACKUP:-}" ]; then
    echo -e "    cp -r $BACKUP $BUNDLED_DIR"
fi
