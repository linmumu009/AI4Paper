# 构建 Tauri 安装包并自动修复安装程序图标
$ROOT = "D:\Datas\Programming\Cursor\ArxivPaper4"
$RCEDIT = "$ROOT\rcedit.exe"
$ICO = "$ROOT\exe\src-tauri\icons\icon.ico"
$SRC_EXE = "$ROOT\exe\src-tauri\target\release\bundle\nsis\AI4Papers_0.1.0_x64-setup.exe"
$DEST_EXE = "$ROOT\exe_release\AI4Papers_0.1.0_x64-setup.exe"

# 1. 构建
Set-Location "$ROOT\exe"
npm run build

# 2. 注入图标
Write-Host "正在注入自定义图标..."
& $RCEDIT $SRC_EXE --set-icon $ICO

# 3. 复制到发布目录
Copy-Item $SRC_EXE $DEST_EXE -Force
Write-Host "完成！安装包已输出到 exe_release\"
