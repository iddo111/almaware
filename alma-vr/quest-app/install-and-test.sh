#!/usr/bin/env bash
set -e
export MSYS_NO_PATHCONV=1
ADB="adb -s <lan-ip>:5555"
APK="D:/CLAUDE/alma-vr/quest-app/app/build/outputs/apk/debug/app-debug.apk"

echo "== wake headset =="
$ADB shell input keyevent KEYCODE_WAKEUP
sleep 1

echo "== install =="
$ADB install -r "$APK"

echo "== grant all-files access (adb appops trick, avoids the Settings UI dance) =="
$ADB shell appops set com.alma.quest MANAGE_EXTERNAL_STORAGE allow || true
$ADB shell appops get com.alma.quest MANAGE_EXTERNAL_STORAGE || true

echo "== launch =="
$ADB shell am start -n com.alma.quest/.MainActivity
sleep 3

echo "== screenshot =="
$ADB exec-out screencap -p > D:/CLAUDE/alma-vr/quest-app/screen-after-launch.png

echo "done"
