# 저장 시 Run on Save에서 호출: 변경이 있을 때만 커밋 후 push
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

if (-not (Test-Path -LiteralPath (Join-Path $Root '.git'))) {
    Write-Host '[git-auto-sync] 이 폴더는 Git 저장소가 아닙니다. git init 후 remote를 추가하세요.'
    exit 0
}

git add -A 2>&1 | Out-Null
$pending = git status --porcelain
if (-not $pending) {
    exit 0
}

$msg = 'chore: auto-save ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
git commit -m $msg 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[git-auto-sync] commit 실패(충돌·hook 등). 출력을 확인하세요.'
    exit $LASTEXITCODE
}

git push 2>&1
exit $LASTEXITCODE
