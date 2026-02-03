#!/bin/bash
set -euo pipefail
# Claude Code 通知スクリプト
# 使用法: notify.sh <タイトル> <メッセージ>

TITLE="${1:-通知}"
MESSAGE="${2:-通知}"

# macOS
if command -v osascript &> /dev/null; then
    osascript \
      -e 'on run argv' \
      -e 'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"' \
      -e 'end run' \
      -- "$TITLE" "$MESSAGE" || {
        echo "Error: macOS notification failed" >&2
        exit 1
      }
    exit 0
fi

# Linux
if command -v notify-send &> /dev/null; then
    notify-send -- "$TITLE" "$MESSAGE" --urgency=normal --icon=dialog-information || {
        echo "Error: Linux notification failed" >&2
        exit 1
      }

    # オプション: 音も鳴らす
    if [ -f /usr/share/sounds/freedesktop/stereo/complete.oga ] && command -v paplay &> /dev/null; then
        paplay /usr/share/sounds/freedesktop/stereo/complete.oga &
    fi
    exit 0
fi

# Windows
if command -v powershell.exe &> /dev/null; then
    # Escape single quotes for PowerShell
    TITLE_ESCAPED="${TITLE//\'/\'\'}"
    MESSAGE_ESCAPED="${MESSAGE//\'/\'\'}"

    powershell.exe -Command "
        Add-Type -AssemblyName System.Windows.Forms
        \$notification = New-Object System.Windows.Forms.NotifyIcon
        \$notification.Icon = [System.Drawing.SystemIcons]::Information
        \$notification.BalloonTipTitle = '$TITLE_ESCAPED'
        \$notification.BalloonTipText = '$MESSAGE_ESCAPED'
        \$notification.Visible = \$true
        \$notification.ShowBalloonTip(3000)
        Start-Sleep -Seconds 3
        \$notification.Dispose()
    " || {
        echo "Error: Windows notification failed" >&2
        exit 1
      }
    exit 0
fi

# フォールバック
echo "🔔 [$TITLE] $MESSAGE" >&2
