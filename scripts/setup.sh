#!/bin/bash
# Setup script for BrowserUse skill
# Устанавливает зависимости и браузеры для Playwright

set -e

echo "🔧 Installing BrowserUse skill dependencies..."
echo "================================================"

# Определяем цветной вывод
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка Python
echo -n "Checking Python... "
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}OK${NC} ($PYTHON_VERSION)"
else
    echo -e "${RED}FAILED${NC}"
    echo "Python 3 is required but not installed."
    exit 1
fi

# Проверка pip
echo -n "Checking pip... "
if command -v pip3 &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "pip3 is required but not installed."
    exit 1
fi

# Установка Python пакетов
echo ""
echo "📦 Installing Python packages..."
pip3 install --upgrade pip
pip3 install -r "$(dirname "$0")/requirements.txt"

# Установка браузеров Playwright
echo ""
echo "🌐 Installing Playwright browsers..."
python3 -m playwright install chromium
python3 -m playwright install-deps  # Системные зависимости для Linux

# Проверка установки
echo ""
echo -n "✅ Verifying installation... "
if python3 -c "import playwright" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Playwright installation verification failed."
    exit 1
fi

# Создание временной директории для скриншотов
mkdir -p /tmp/browser-use-screenshots
echo "📁 Created screenshot directory: /tmp/browser-use-screenshots"

echo ""
echo "================================================"
echo -e "${GREEN}✅ BrowserUse skill successfully installed!${NC}"
echo ""
echo "📖 Quick test:"
echo "   python3 $(dirname "$0")/browser_automation.py '{\"action\":\"goto\",\"url\":\"https://example.com\"}'"
echo ""
echo "📚 For more examples, see SKILL.md"
echo "================================================"